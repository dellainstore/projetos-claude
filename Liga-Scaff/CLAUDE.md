# Liga Quarta Scaff — Contexto do Projeto

## O que é
Sistema web de gerenciamento de liga de Beach Tennis, chamada "Liga Quarta Scaff". Permite cadastro de jogadores, sorteio de partidas, registro de resultados, ranking, histórico e geração de PDF para finais.

## Stack
- **Framework:** Streamlit (>=1.37, <2.0) — multi-page app
- **Banco de dados:** SQLite local (`data/liga_scaff.db`)
- **PDF:** ReportLab
- **Autenticação:** bcrypt + session_state do Streamlit
- **Linguagem:** Python 3

## Estrutura de arquivos
```
app.py              — entry point (login + config inicial)
pages/
  1_Jogadores.py    — cadastro e gestão de jogadores
  2_Sorteio.py      — sorteio de partidas/chaves
  3_Resultados.py   — registro de resultados
  4_Ranking.py      — ranking atual da liga
  5_Historico.py    — histórico de edições/temporadas
  6_Final.py        — gestão da rodada final
src/
  auth.py           — autenticação (login/logout, bcrypt)
  database.py       — init e queries SQLite
  draw_engine.py    — lógica de sorteio
  sorteio_job.py    — execução do sorteio em segundo plano
  email_sender.py   — envio de e-mails
  pdf_generator.py  — geração de PDF com ReportLab
  ranking.py        — cálculo de ranking
  scoring.py        — cálculo de pontuação
  utils.py          — utilitários gerais (inclui fmt_data para datas)
assets/             — arquivos estáticos (imagens, CSS extra)
data/
  liga_scaff.db     — banco SQLite (não versionar dados reais)
start.sh            — script para iniciar o app
```

## Convenções
- Sidebar escondida antes do login (CSS inline no `app.py`)
- Navegação pelo menu lateral do Streamlit (pages numeradas para ordenação)
- Cores principais: `#f5a623` (laranja) e `#1a1a2e` (azul escuro)
- Toda lógica de negócio fica em `src/`, as pages só chamam funções de lá
- Banco inicializado via `db.init_db()` no startup
- **Datas sempre exibidas como DD/MM/AAAA** — usar `fmt_data()` de `src/utils.py`
- **Renomeação do menu lateral:** item "app" é renomeado para "Inicial" via JavaScript injetado em `auth.render_sidebar_user()` (usando `st.components.v1.html` com `window.parent.document`)

## Dashboard principal (app.py)
- Layout de 4 cards em **2 linhas × 2 colunas** (linha 1: Temporada Ativa + Próxima Rodada; linha 2: Rodadas Concluídas + Jogadores)
- Nome completo da temporada exibido sem truncamento

## Motor de Sorteio (src/draw_engine.py)
- **Regra obrigatória master:** no mesmo dia, nenhum jogador repete parceiro ou adversário e também não pode enfrentar alguém com quem já fez dupla naquela noite (backtracking com rejeição imediata).
- **Regra obrigatória secundária:** ninguém pode repetir parceiro da rodada oficial imediatamente anterior.
- **Exceção por ausência recente:** quando um jogador faltou na rodada imediatamente anterior, a referência de "última rodada" passa a ser a última rodada em que ele realmente jogou dentro da janela histórica usada pelo sorteio. Ex.: ao gerar a rodada 7 usando rodadas 6 e 5 como base, quem esteve na 5, faltou na 6 e voltou na 7 passa a usar a 5 como referência pessoal para parceiro proibido e adversários recentes.
- **Regra soft (histórico):** aceita parâmetro `historico_jogos` com jogos dos últimos N sorteios concluídos. A busca agora prioriza combinações que mantêm cada jogador com no máximo `2` adversários repetidos da rodada imediatamente anterior antes de refinar o restante do histórico.
- **Peso por recência:** a rodada imediatamente anterior continua sendo a principal referência para reduzir adversários repetidos (`40` pts por confronto repetido), enquanto a penúltima mantém parceiro repetido = `60` pts e adversário repetido = `10` pts como desempate histórico.
- **Heurística de performance:** o backtracking fixa o primeiro jogador restante de cada quadra para cortar simetrias e encerra a busca mais cedo quando já encontrou soluções válidas suficientes com a meta de repetição recente atendida.
- Função `db.get_historico_jogos_rodadas(rodada_id, n=2)` retorna jogos das últimas N rodadas concluídas da temporada para alimentar o histórico.
- **Resultado observado nos testes da rodada 7 comparada com a 6:** parceiros repetidos entre rodadas consecutivas continuam em `0`; adversários repetidos caíram de `50` incidências totais no sorteio oficial observado para `10` em teste do motor ajustado, com máximo de `2` por jogador.

## Geração em Segundo Plano (pages/2_Sorteio.py + src/sorteio_job.py)
- O sorteio oficial pode ser iniciado em segundo plano e continua rodando no servidor mesmo se o usuário trocar de página ou fechar a aba.
- O progresso é persistido em SQLite (`sorteio_jobs`) com status, tentativas, válidos, ETA e erro.
- Enquanto houver job em andamento, a rodada fica com status `gerando_sorteio`.
- Na página `2_Sorteio.py`, o progresso da rodada atual aparece logo abaixo do botão de gerar sorteio.
- Na navegação geral, a sidebar mostra um resumo do sorteio em andamento quando houver job ativo.
- Atualização manual com `F5` pode quebrar a sessão do Streamlit e pedir login novamente; o fluxo esperado é deixar a própria página de Sorteio se autoatualizar enquanto o job roda.

## Datas e Horários
- **Datas exibidas como DD/MM/AAAA** — usar `fmt_data()` de `src/utils.py`
- **Timestamps de criação de sorteio exibidos em horário de Brasília** — usar `fmt_datetime_brasilia()` de `src/utils.py` para converter `created_at` do SQLite (UTC) antes de mostrar na interface.

## Download de PDF (Sorteio)
- O botão "Baixar Planilha PDF" na aba Sorteio é um `st.download_button` com o PDF pré-gerado — um clique já baixa sem precisar rolar a página.

## Segurança (app.py + pages/4_Ranking.py)
- **Brute-force login:** bloqueio após 5 tentativas incorretas via `st.session_state["login_tentativas"]`; atualizando a página o contador é zerado
- **Senha padrão:** banner de aviso exibido no dashboard quando o usuário logado é `admin` com role `admin`
- **Validação de senha:** mínimo de 8 caracteres tanto na criação quanto na troca de senha (em `4_Ranking.py`)
- **Injeção ReportLab:** todos os nomes de jogadores passados para `Paragraph()` são escapados com `html.escape()` do módulo `html` para evitar interpretação de tags XML
- **SQL:** todas as queries usam parâmetros `?` (sem interpolação de strings) — sem risco de SQL injection

## Geração de PDFs (src/pdf_generator.py)

### PDF — Planilha de Resultados (landscape A4)
- Gerado em `gerar_planilha_pdf()`, baixado via `st.download_button` na aba Sorteio
- **Os 4 jogos SEMPRE na mesma folha:** `KeepTogether` + `splitByRow=0` na `Table` impedem separação entre páginas
- **Colunas de tamanho fixo em todas as páginas:** `col_q_fixo` calculado uma vez com base em `max_q_pag`; grupos com menos quadras ficam centralizados via `t.hAlign = "CENTER"`
- **5 quadras por página** (`MIN_COL_Q = 5.0 * cm`) — evita nomes cortados que ocorreriam com 6
- Grupos com menos quadras na última página mantêm o mesmo tamanho de coluna (não se expandem para preencher a folha)
- Título e subtítulo de cada folha centralizados e gerados dentro do `KeepTogether` junto com a tabela
- **Célula de jogo (`_celula_jogo`):** layout em 3 linhas — Nome1 / × / Nome2; o "×" fica centralizado na coluna de nomes (sem SPAN); caixa de placar afastada do nome via `RIGHTPADDING=8pt`
- Espessura das linhas: grade 0.5pt, separadores 1.5pt, borda externa 1.2pt
- Margens: 0.8 cm

### PDFs de E-mail (retrato A4) — 3 arquivos
Gerados em `gerar_email_rodada_pdf()`, `gerar_ranking_pdf()` e `gerar_ranking_sem_desconto_pdf()`.

- **Sempre 1 página:** margens mínimas (`_MARGEM_EMAIL = 0.4 * cm`); fonte e altura de linha calculadas dinamicamente para preencher a página inteira
- **Cálculo dinâmico de fonte:** `row_h_ideal = disponivel / n_linhas`; `fs = round(row_h_mm * 1.64)`, limitado entre 8pt e 14pt
- **Centralização vertical nas células:** `VALIGN MIDDLE` + `TOPPADDING`/`BOTTOMPADDING` proporcionais ao espaço sobrando em cada linha (`pad_v = (row_h - fs*1.2) / 2`); `ROWHEIGHT` no `TableStyle` define a altura mínima sem causar overflow de página
- **Ordem das colunas:** Pos | Nome | Total | R1 | R2 | … (Total logo após o nome, não no final)
- **Rodadas descartadas** aparecem entre parênteses com fundo vermelho claro (`COR_DESCARTE_BG`)
- Nome do jogador sempre alinhado à esquerda; demais colunas centralizadas

## Ranking (pages/4_Ranking.py + src/ranking.py)
- Tabela na tela: coluna "Total" logo após "Jogador" (antes das colunas de rodadas)
- Rodadas descartadas exibidas entre parênteses `(valor)` com célula destacada
- Seção "Gerenciar Usuários" visível apenas para `admin` (no mesmo arquivo, ao final da página)

## Placar especial 7x7 (src/scoring.py + pages/3_Resultados.py)
- **7x7 é permitido** quando o jogo é interrompido (ex.: chuva).
- **Ninguém vence nem perde** no `7x7`; cada jogador recebe **7 pontos** naquela partida.
- O `7x7` **não conta como derrota** para a regra da cerveja.
- A regra da cerveja continua valendo normalmente para quem **levou 6x0**, mesmo que também tenha algum `7x7` na rodada.

## Como rodar
```bash
cd /var/www/della-sistemas/projetos-claude/Liga-Scaff
bash start.sh
# ou
streamlit run app.py
```

## Git / Deploy
- Repositório: `dellainstore/projetos-claude` (pasta `Liga-Scaff/`)
- Push via HTTPS com token do gh CLI:
  ```bash
  TOKEN=$(/tmp/gh_2.67.0_linux_amd64/bin/gh auth token)
  git -C /var/www/della-sistemas/projetos-claude remote set-url origin "https://dellainstore:${TOKEN}@github.com/dellainstore/projetos-claude.git"
  git -C /var/www/della-sistemas/projetos-claude add Liga-Scaff/ && git -C /var/www/della-sistemas/projetos-claude commit -m "msg" && git -C /var/www/della-sistemas/projetos-claude push
  ```
- `gh` CLI em `/tmp/gh_2.67.0_linux_amd64/bin/gh`

## O que NÃO fazer
- Não commitar `data/liga_scaff.db` com dados reais de jogadores
- Não instalar dependências globalmente — usar `pip install -r requirements.txt` no ambiente correto
- Não quebrar a navegação multi-page do Streamlit (não remover numeração dos arquivos em `pages/`)
- Não usar `rowHeights` no construtor de `Table` nos PDFs de e-mail — causa overflow para 2 páginas; usar `ROWHEIGHT` no `TableStyle`
- Não adicionar `elements.append(tabela)` após `elements.append(KeepTogether([..., tabela]))` — duplica a tabela no PDF
