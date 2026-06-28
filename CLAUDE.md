# Projetos Claude — Della Sistemas

Este repositório contém projetos desenvolvidos com auxílio do Claude Code.

## Estrutura de pastas

Cada projeto deve ter sua própria subpasta dentro de `projetos-claude/`:

```
projetos-claude/
├── della_sistemas/      # Painel web unificado (Django) — produção
├── site_della/          # E-commerce (Django) — produção
├── Liga-Scaff/          # Streamlit
├── Relatorio_de_Metas/  # Relatório de metas (PDF)
├── Outro-Projeto/       # ...
└── CLAUDE.md            # Este arquivo
```

## Regras para novos projetos

- **Sempre** crie uma subpasta com o nome do projeto dentro de `projetos-claude/`
- Use nomes descritivos em PascalCase ou Kebab-Case (ex: `Bot-Telegram`, `Dashboard-Financeiro`)
- Cada projeto deve conter seus próprios arquivos (`requirements.txt`, `.env.example`, `README`, etc.)
- Nunca commitar arquivos `.env` com credenciais reais — use `.env.example`

## Git e GitHub

- O repositório no GitHub é: `dellainstore/projetos-claude`
- **A cada atualização**, commitar e fazer push para o GitHub
- Manter o `.gitignore` atualizado (ignorar `venv/`, `.env`, `__pycache__/`, etc.)

## Segurança — arquivos .env

- **NUNCA** subir arquivos `.env` para o GitHub — eles ficam apenas na VPS
- O `.env` contém credenciais reais (tokens, API keys, senhas) e não deve ser versionado
- Sempre criar um `.env.example` com as variáveis necessárias mas **sem os valores reais**
- Verificar antes de qualquer commit se não há `.env` sendo rastreado (`git status`)

## Projetos

> O projeto **Bot-Telegram** foi removido em 2026-06-28 (sem uso).
