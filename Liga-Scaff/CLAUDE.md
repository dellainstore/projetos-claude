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
- **Regra obrigatória:** no mesmo dia, nenhum jogador repete parceiro ou adversário (backtracking com rejeição imediata)
- **Regra soft (histórico):** aceita parâmetro `historico_jogos` com jogos dos últimos N sorteios concluídos. Avalia até 150 soluções válidas, pontua cada uma (parceiro repetido = 2 pts, adversário repetido = 1 pt) e retorna a de menor penalidade. Sai imediatamente se encontrar score 0.
- Função `db.get_historico_jogos_rodadas(rodada_id, n=2)` retorna jogos das últimas N rodadas concluídas da temporada para alimentar o histórico.

## Download de PDF (Sorteio)
- O botão "Baixar Planilha PDF" na aba Sorteio é um `st.download_button` com o PDF pré-gerado — um clique já baixa sem precisar rolar a página.

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
