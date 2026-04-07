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
  utils.py          — utilitários gerais
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
  TOKEN=$(gh auth token) && git -C /var/www/della-sistemas/projetos-claude remote set-url origin "https://dellainstore:${TOKEN}@github.com/dellainstore/projetos-claude.git"
  git -C /var/www/della-sistemas/projetos-claude add Liga-Scaff/ && git -C /var/www/della-sistemas/projetos-claude commit -m "msg" && git -C /var/www/della-sistemas/projetos-claude push
  ```
- `gh` CLI em `/tmp/gh_2.67.0_linux_amd64/bin/gh`

## O que NÃO fazer
- Não commitar `data/liga_scaff.db` com dados reais de jogadores
- Não instalar dependências globalmente — usar `pip install -r requirements.txt` no ambiente correto
- Não quebrar a navegação multi-page do Streamlit (não remover numeração dos arquivos em `pages/`)
