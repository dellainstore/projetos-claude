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
├── main.ts            liga o poller à cena e ao painel
├── poller.ts          polling 10s, ETag/304, backoff, pausa em aba oculta
├── diff.ts            controla quais eventId já foram animados
├── render.ts          painel de conferência (tabela, indicadores)
├── types.ts           contrato da API (espelha serializacao.py)
└── cena/
    ├── mapa.ts        geometria: corredor, vagas, caminhos (PURO, sem Phaser)
    ├── paleta.ts      cores por slug de personagem (PURO, sem Phaser)
    ├── personagem.ts  a personagem 2D desenhada por código
    └── escritorio.ts  a cena Phaser
```

## Comandos

```bash
npm ci          # instala as dependências de build
npm run build   # typecheck + bundle em ../della_sistemas/static/escritorio/
npm test        # 65 testes: mapa, paleta, poller, animações e a cena headless
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

**A planta vem do banco, não do código.** `mapa.ts` recebe as salas da API
(`SalaEscritorio`: slug, posição, tamanho) e calcula tudo a partir delas,
inclusive **onde fica o corredor**: ele é a faixa horizontal mais larga que
nenhuma sala ocupa. Mover ou acrescentar uma sala no banco muda o mapa e o
trajeto das personagens sem tocar em uma linha de TypeScript.

**Personagens desenhadas por código.** Não há arte de terceiros: cabeça,
cabelo, corpo, braços e pernas são formas do Phaser, coloridas por uma paleta
derivada do slug da personagem (com ajuste manual opcional por slug, nunca por
nome de pessoa). Cadastrar alguém novo já aparece com cor própria.
**Para trocar por sprites de verdade depois, só `personagem.ts` muda**: a cena
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

## Próxima fase

Sprites de verdade, objetos clicáveis, balões e replay. Tudo continua
consumindo o mesmo endpoint e o mesmo contrato de `src/types.ts`.
