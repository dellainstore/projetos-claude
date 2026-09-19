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

```
src/
├── main.ts                       liga a API à cena, ao painel e à simulação
├── types.ts                      contrato da API (espelha serializacao.py)
├── config/
│   ├── rooms.ts                  paleta, mobiliário e silhueta (PURO)
│   ├── paths.ts                  waypoints nomeados e rotas (PURO)
│   └── characters.ts             cor por slug de personagem (PURO)
├── scenes/
│   ├── BootScene.ts              carga (hoje instantânea: arte é procedural)
│   └── OfficeScene.ts            a cena, em camadas
├── actors/
│   └── Character.ts              a personagem 2D desenhada por código
├── environment/
│   ├── geometry.ts               planta, portas, vagas, luz (PURO)
│   ├── DoorController.ts         porta de rua com 4 estados
│   ├── LightingController.ts     luz por cômodo
│   └── StoreController.ts        estado da loja -> decisões visuais (PURO)
├── state/
│   ├── poller.ts                 polling 10s, ETag/304, backoff, aba oculta
│   ├── diff.ts                   quais eventId já foram animados
│   └── officeStore.ts            guarda-cena: API x simulação (PURO)
└── ui/
    ├── painel.ts                 tabela de conferência
    ├── NameTag.ts                etiqueta de nome, acima dos móveis
    └── DebugPanel.ts             simulação (não escreve em lugar nenhum)
```

Os módulos marcados como PURO não importam Phaser nem tocam no DOM: é o que
permite testar planta, rota, luz e transição de loja sem subir um navegador.

## Comandos

```bash
npm ci          # instala as dependências de build
npm run build   # typecheck + bundle em ../della_sistemas/static/escritorio/
npm test        # 110 testes: geometria, rotas, paleta, poller, animações,
                # guarda-cena, painel de simulação e a cena headless
node scripts/capturar.mjs   # capturas reais do bundle (Chromium headless)
npm run dev     # rebuild em watch, para desenvolvimento
```

Depois do build, para o navegador receber o arquivo novo em produção:

```bash
cd ../della_sistemas
.venv/bin/python manage.py collectstatic --noinput
```

## Decisões

**Phaser 3, carregado local.** Nada de CDN. O bundle fica em torno de 1,2 MB
(cerca de 340 KB comprimido), quase tudo Phaser. É o preço de poder crescer
com salas, objetos clicáveis e balões; para um painel interno é aceitável.

**A planta vem do banco, não do código.** `environment/geometry.ts` recebe as salas da API
(`SalaEscritorio`: slug, posição, tamanho) e calcula tudo a partir delas,
inclusive as PORTAS, deduzidas de onde cada cômodo encosta no corredor (que
também é uma sala de verdade). Mover ou acrescentar um cômodo no banco muda o
trajeto das personagens sem tocar em uma linha de TypeScript.

**Personagens desenhadas por código.** Não há arte de terceiros: cabeça,
cabelo, corpo, braços e pernas são formas do Phaser, coloridas por uma paleta
derivada do slug da personagem (com ajuste manual opcional por slug, nunca por
nome de pessoa). Cadastrar alguém novo já aparece com cor própria.
**Para trocar por sprites de verdade depois, só `actors/Character.ts` muda**: a cena
conversa com ela por `posicionar`, `caminharPor`, `aplicar`, `mostrar` e
`esconder`, e nenhum desses contratos depende de como ela é desenhada.

**O servidor sempre manda.** O cliente nunca deriva estado a partir de evento:
ele renderiza o que veio em `GET /escritorio/api/estado/`. Se uma personagem
está no meio de uma caminhada e chega uma resposta dizendo outra coisa, a
caminhada é cancelada na hora. Por isso abrir a página depois de uma batida
mostra a cena correta, e os eventos só decidem se uma transição é *animada*.

**Sem armazenamento no navegador.** O conjunto de `eventId` já animados vive
em memória, enquanto a aba está aberta (`src/diff.ts`). Recarregar a página
pode, no máximo, repetir uma animação por personagem, e só se a batida tiver
menos de 120 segundos. Nada é gravado em `localStorage`, `sessionStorage` ou
IndexedDB.

**Polling, não WebSocket nem SSE.** O Gunicorn do painel roda com 2 workers
`sync`. Uma conexão persistente ocuparia um worker inteiro; duas abas
travariam o painel, inclusive a tela de bater ponto. O poller consulta a cada
10 segundos (configurável em `ParametrosEscritorio`), com `If-None-Match` e
resposta 304 quando nada mudou.

## A cena roda nos testes, não só compila

`tests/cena.test.ts` sobe o Phaser em modo `HEADLESS` dentro do Node (jsdom em
`tests/ambiente-dom.ts`) e aplica payloads reais da API. Isso existe porque a
cena e a personagem somam centenas de linhas que o `tsc` valida mas **não
executa**, e já pagou por si: pegou um bug em que o retângulo de escuridão
nascia com `fillAlpha: 0` enquanto o tween animava o `alpha` do objeto. As
luzes nunca apagariam no navegador, e nenhum teste de tipo acusaria isso.

Três armadilhas do ambiente, todas documentadas no código:

- o jsdom nunca dá foco à janela, então o Phaser marca o jogo como `isPaused`
  e o loop não processa nada. Sem corrigir, os testes de movimento estariam
  conferindo uma cena congelada e passariam por engano;
- o `performance` global **não** pode apontar para o do jsdom (recursão
  infinita). O `TweenManager` do Phaser mede tempo com `Date.now()` de
  qualquer forma;
- o jsdom não carrega data-URI, então o `onload` das texturas padrão nunca
  dispara e o evento `ready` do jogo nunca chega. Por isso há uma `Image`
  falsa que resolve na hora.

Como os tweens andam pelo relógio real, os testes de movimento esperam uma
**condição** (`aguardarAte`) em vez de um tempo fixo, e não ficam reféns da
carga da máquina.

## Capturas

`node scripts/capturar.mjs` abre o **bundle de produção** num Chromium
headless, com uma API falsa interceptada no navegador, e fotografa cada
situação (loja fechada, todas trabalhando, alguém no corredor, almoço,
pendência, mobile). Não é mockup: é o mesmo `escritorio.js` que vai para a
loja. As imagens saem em `capturas/`.

O `puppeteer` entra como devDependency só para isso. Ele arrasta um aviso de
`npm audit` (`extract-zip`, alta): a falha está na EXTRAÇÃO do arquivo do
navegador na hora de instalar, vindo do endpoint oficial do Chrome for
Testing, e nada disso entra no bundle. Se preferir não conviver com o aviso,
remova o pacote e reinstale só quando for gerar captura.

## Limitações visuais conhecidas

- **Não é isométrico de verdade.** É uma planta em corte vista de cima, com
  as paredes de fundo aparecendo dentro de cada cômodo. A referência é
  desenhada à mão em perspectiva; aqui tudo é geometria procedural.
- **As personagens são formas, não pixel art.** Trocar por sprites mexe só
  em `src/actors/Character.ts`: a cena conversa com ela por `posicionar`,
  `caminharPor`, `aplicar`, `mostrar` e `esconder`.
- **O mobiliário é estilizado.** Cafeteira, pia e prateleiras existem como
  volumes, não como desenhos detalhados.

## Próxima fase

Sprites de verdade, objetos clicáveis, balões e replay. Tudo continua
consumindo o mesmo endpoint e o mesmo contrato de `src/types.ts`.
