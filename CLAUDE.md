# Projetos Claude — Della Sistemas

Este repositório contém projetos desenvolvidos com auxílio do Claude Code.

## Estrutura de pastas

Cada projeto deve ter sua própria subpasta dentro de `projetos-claude/`:

```
projetos-claude/
├── Bot-Telegram/        # Bot do Telegram integrado com Claude AI
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

### Bot-Telegram
Bot do Telegram que integra com a API do Claude (Anthropic) para responder mensagens.
- Arquivo principal: `Bot-Telegram/bot.py`
- Serviço systemd: `Bot-Telegram/telegram-claude-bot.service`
