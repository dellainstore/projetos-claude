# escritorio-virtual (frontend)

Workspace de **build** do frontend do Escritório Virtual da D'ELLA.

Não existe processo Node em produção. O Node é usado só aqui, para compilar o
bundle; quem serve a página é o Django (`apps.escritorio_virtual`) e o Nginx.

## Onde está cada parte

| Parte | Onde |
|---|---|
| Backend, projeção do ponto, API | `../della_sistemas/apps/escritorio_virtual/` |
| Página que carrega o bundle | `../della_sistemas/templates/escritorio/diagnostico.html` |
| Saída do build | `../della_sistemas/static/escritorio/escritorio.js` |

## Comandos

```bash
npm ci          # instala as dependências de build
npm run build   # typecheck + bundle em ../della_sistemas/static/escritorio/
npm test        # testes do poller e do controle de animações (node:test)
npm run dev     # rebuild em watch, para desenvolvimento
```

Depois do build, para o navegador receber o arquivo novo em produção:

```bash
cd ../della_sistemas
.venv/bin/python manage.py collectstatic --noinput
```

O `collectstatic` **não** foi executado ainda: enquanto não rodar, a página
diagnóstica em produção carrega o HTML mas não encontra o JS.

## Decisões

**Nomes de arquivo fixos, sem hash.** O cache-busting do painel é feito pela
tag `{% estatico %}`, que anexa `?v=<mtime>` (ver
`apps/core/templatetags/core_extras.py`). Nome com hash só criaria arquivo
órfão a cada build.

**Sem armazenamento no navegador.** O conjunto de `eventId` já animados vive
em memória, enquanto a aba está aberta (`src/diff.ts`). Recarregar a página
pode, no máximo, repetir uma animação por personagem, e só se a batida tiver
menos de 120 segundos. Nada é gravado em `localStorage`, `sessionStorage` ou
IndexedDB.

**O servidor sempre manda.** O cliente nunca deriva estado a partir de evento:
ele renderiza o que veio em `GET /escritorio/api/estado/`. Os eventos só
decidem se uma transição é *animada*, nunca qual estado a personagem tem. Por
isso abrir a página depois de uma batida mostra a cena correta.

**Polling, não WebSocket nem SSE.** O Gunicorn do painel roda com 2 workers
`sync`. Uma conexão persistente ocuparia um worker inteiro; duas abas
travariam o painel, inclusive a tela de bater ponto. O poller consulta a cada
10 segundos (configurável em `ParametrosEscritorio`), com `If-None-Match` e
resposta 304 quando nada mudou.

## Próxima fase

O cenário 2D em Phaser 3 entra depois, consumindo exatamente o mesmo endpoint
e o mesmo contrato de `src/types.ts`. A página atual é diagnóstica: serve para
validar poller, contrato e projeção antes de existir mapa e sprite.
