/**
 * Teste de fumaca da cena 2D: boota o Phaser em HEADLESS e aplica payloads
 * reais da API, conferindo que a cena reage sem explodir.
 *
 * Nao verifica pixel: verifica COMPORTAMENTO (quantas personagens existem,
 * quem esta visivel, se as luzes apagaram, se a caminhada acontece) e, acima
 * de tudo, que o codigo Phaser de fato roda.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { prepararDOM } from "./ambiente-dom";

prepararDOM();

// Phaser so pode ser importado DEPOIS do DOM existir.
//
// Em Node o `phaser` resolve para a arvore de fontes, que faz `require` de
// `phaser3spectorjs` (ferramenta de debug de WebGL). No navegador o Vite
// resolve isso sozinho; aqui ele entra como devDependency so para o teste
// conseguir carregar. Carregamos um unico Phaser (nao o bundle `dist`) para
// a cena e o teste compartilharem a mesma instancia.
const Phaser = require("phaser") as typeof import("phaser");
const { CenaEscritorio } = require("../src/cena/escritorio") as typeof import("../src/cena/escritorio");

import type { Cena, Personagem, Sala } from "../src/types";

function sala(
  slug: string, nome: string, pos_x: number, pos_y: number, largura: number, altura: number,
): Sala {
  return { slug, nome, ordem: 0, pos_x, pos_y, largura, altura };
}

const PLANTA: Sala[] = [
  sala("store-entrance", "Entrada", 0, 240, 200, 140),
  sala("showroom-1", "Showroom 1", 220, 0, 320, 220),
  sala("showroom-2", "Showroom 2", 560, 0, 320, 220),
  sala("cafeteria", "Refeitório", 220, 240, 320, 180),
];

function personagem(p: Partial<Personagem> = {}): Personagem {
  return {
    id: 1,
    personagem: "tina",
    nome: "Tina",
    tipoAtor: "HUMAN_EMPLOYEE",
    estado: "WORKING",
    estadoEstavel: "WORKING",
    desde: "2026-09-14T09:00:00-03:00",
    sala: "showroom-1",
    salaTrabalho: "showroom-1",
    salaOrigem: "loja",
    posX: 0,
    posY: 0,
    evento: null,
    inconsistencia: null,
    ...p,
  };
}

function cena(
  personagens: Personagem[],
  loja: Partial<Cena["loja"]> = {},
  salas: Sala[] = PLANTA,
): Cena {
  return {
    versao: 1,
    data: "2026-09-14",
    geradoEm: "2026-09-14T09:00:00-03:00",
    pollSegundos: 10,
    loja: {
      estado: "OPEN", luzesAcesas: true, portaAberta: true, pendencias: 0, ...loja,
    },
    salas,
    personagens,
    avisos: [],
  };
}

const espera = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Espera uma condicao virar verdadeira, conferindo de tempos em tempos.
 *
 * Os tweens do Phaser andam pelo relogio real (o TweenManager usa
 * `Date.now()`), entao cravar um `espera(N)` fixo deixa o teste refem da
 * carga da maquina. Aqui o teste so espera o necessario e falha com uma
 * mensagem util se a condicao nunca acontecer.
 */
async function aguardarAte(
  condicao: () => boolean, descricao: string, limiteMs = 8000,
): Promise<void> {
  const fim = Date.now() + limiteMs;
  while (Date.now() < fim) {
    if (condicao()) return;
    await espera(40);
  }
  assert.fail(`tempo esgotado esperando: ${descricao}`);
}


/** Boota o jogo e devolve a cena pronta para receber payloads. */
async function abrirCena(): Promise<{
  cena: InstanceType<typeof CenaEscritorio>;
  jogo: Phaser.Game;
  atores: Map<number, any>;
}> {
  const jogo = new Phaser.Game({
    type: Phaser.HEADLESS,
    parent: document.getElementById("palco") as HTMLElement,
    width: 928,
    height: 496,
    banner: false,
    audio: { noAudio: true },
    scene: [CenaEscritorio],
  });

  await new Promise<void>((resolve) => jogo.events.once("ready", () => resolve()));
  // `ready` e' emitido ANTES de `Game.start()`; espera o boot fechar.
  await espera(30);

  // O jsdom nunca da foco a janela, entao o VisibilityHandler do Phaser
  // dispara BLUR e o jogo entra em `isPaused` — nesse estado o `headlessStep`
  // retorna cedo e NENHUM tween avanca. Sem isto, todo teste de movimento
  // estaria conferindo uma cena congelada e passaria por engano.
  (jogo as unknown as { isPaused: boolean }).isPaused = false;

  const alvo = jogo.scene.getScene("escritorio") as InstanceType<typeof CenaEscritorio>;
  assert.ok(alvo, "a cena precisa existir depois do boot");
  // `personagens` e' privado em TS, mas o teste precisa inspecionar o elenco.
  const atores = (alvo as unknown as { personagens: Map<number, any> }).personagens;
  return { cena: alvo, jogo, atores };
}

test("a cena boota e desenha a planta vinda da API", async () => {
  const { cena: palco, jogo } = await abrirCena();
  palco.aplicar(cena([personagem()]));
  await espera(40);

  // A planta tem 880x420 mais margens; o canvas precisa ter sido redimensionado.
  assert.ok(jogo.scale.width >= 880, `canvas estreito demais: ${jogo.scale.width}`);
  assert.ok(jogo.scale.height >= 420, `canvas baixo demais: ${jogo.scale.height}`);
  jogo.destroy(true);
});

test("cria uma personagem por item do payload e some com quem saiu", async () => {
  const { cena: palco, jogo, atores } = await abrirCena();

  palco.aplicar(cena([
    personagem({ id: 1, personagem: "tina", nome: "Tina" }),
    personagem({ id: 2, personagem: "sara", nome: "Sara" }),
    personagem({ id: 3, personagem: "michelle", nome: "Michelle", sala: "showroom-2" }),
  ]));
  await espera(40);
  assert.equal(atores.size, 3);

  // Michelle sai do cadastro: o ator tem que ser destruido.
  palco.aplicar(cena([
    personagem({ id: 1, personagem: "tina", nome: "Tina" }),
    personagem({ id: 2, personagem: "sara", nome: "Sara" }),
  ]));
  await espera(40);
  assert.equal(atores.size, 2);
  assert.ok(!atores.has(3));
  jogo.destroy(true);
});

test("colegas de sala nao ficam na mesma posicao", async () => {
  const { cena: palco, jogo, atores } = await abrirCena();
  palco.aplicar(cena([
    personagem({ id: 1, personagem: "tina", nome: "Tina", sala: "showroom-1" }),
    personagem({ id: 2, personagem: "sara", nome: "Sara", sala: "showroom-1" }),
  ]));
  await espera(40);

  assert.notEqual(atores.get(1).x, atores.get(2).x);
  jogo.destroy(true);
});

test("quem esta fora de cena nao fica visivel", async () => {
  const { cena: palco, jogo, atores } = await abrirCena();
  palco.aplicar(cena([
    personagem({ id: 1, estado: "DAY_OFF", sala: null }),
    personagem({ id: 2, personagem: "sara", nome: "Sara", estado: "WORKING" }),
  ]));
  await espera(40);

  assert.equal(atores.get(1).estaVisivel, false, "folga nao renderiza personagem");
  assert.equal(atores.get(2).estaVisivel, true);
  jogo.destroy(true);
});

test("ir para o almoco faz a personagem caminhar ate o refeitorio", async () => {
  const { cena: palco, jogo, atores } = await abrirCena();

  palco.aplicar(cena([personagem({ estado: "WORKING", sala: "showroom-1" })]));
  await espera(60);
  const ator = atores.get(1);
  const noShowroom = { x: ator.x, y: ator.y };

  palco.aplicar(cena([personagem({ estado: "LUNCH", sala: "cafeteria" })]));
  await espera(40);
  assert.equal(ator.salaAtual, "cafeteria");

  await aguardarAte(() => ator.y > 240, "a personagem chegar ao refeitório");
  const noRefeitorio = { x: ator.x, y: ator.y };
  assert.notDeepEqual(noRefeitorio, noShowroom, "a personagem nao saiu do lugar");
  assert.ok(
    noRefeitorio.x > 220 && noRefeitorio.x < 540,
    `fora do refeitorio no eixo x: ${noRefeitorio.x}`,
  );
  jogo.destroy(true);
});

test("o estado do servidor cancela uma caminhada em andamento", async () => {
  const { cena: palco, jogo, atores } = await abrirCena();

  palco.aplicar(cena([personagem({ estado: "WORKING", sala: "showroom-1" })]));
  await espera(60);
  const ator = atores.get(1);

  // Comeca a ir para o refeitorio...
  palco.aplicar(cena([personagem({ estado: "LUNCH", sala: "cafeteria" })]));
  await espera(150);
  // ...e no meio do caminho o servidor diz que ela esta no showroom 2.
  palco.aplicar(cena([personagem({ estado: "WORKING", sala: "showroom-2" })]));

  assert.equal(ator.salaAtual, "showroom-2");
  await aguardarAte(
    () => ator.x > 560 && ator.y < 220,
    "a personagem obedecer ao servidor e ir para o showroom 2",
  );
  // Nunca chegou ao refeitorio: o destino antigo foi descartado no meio.
  assert.ok(ator.y < 220, `deveria estar no showroom: y=${ator.y}`);
  jogo.destroy(true);
});

test("sair do expediente esconde a personagem", async () => {
  const { cena: palco, jogo, atores } = await abrirCena();

  palco.aplicar(cena([personagem({ estado: "WORKING", sala: "showroom-1" })]));
  await espera(60);
  assert.equal(atores.get(1).estaVisivel, true);

  palco.aplicar(cena([personagem({ estado: "LEAVING", sala: "store-entrance" })]));
  await espera(40);
  assert.equal(atores.get(1).salaAtual, "store-entrance");

  palco.aplicar(cena([personagem({ estado: "OFF_SHIFT", sala: null })]));
  await aguardarAte(() => !atores.get(1).estaVisivel, "a personagem sumir de cena");
  jogo.destroy(true);
});

test("luzes apagam quando a loja fecha e acendem quando abre", async () => {
  const { cena: palco, jogo } = await abrirCena();
  const escuridao = (palco as unknown as { escuridao: Phaser.GameObjects.Rectangle }).escuridao;

  palco.aplicar(cena([personagem()], { estado: "OPEN", luzesAcesas: true }));
  await aguardarAte(() => escuridao.alpha < 0.05, "as luzes acenderem");

  palco.aplicar(cena(
    [personagem({ estado: "OFF_SHIFT", sala: null })],
    { estado: "CLOSED", luzesAcesas: false, portaAberta: false },
  ));
  await aguardarAte(() => escuridao.alpha > 0.4, "as luzes apagarem");
  jogo.destroy(true);
});

test("almoco de todas mantem a loja acesa", async () => {
  const { cena: palco, jogo } = await abrirCena();
  const escuridao = (palco as unknown as { escuridao: Phaser.GameObjects.Rectangle }).escuridao;

  palco.aplicar(cena(
    [personagem({ estado: "LUNCH", sala: "cafeteria" })],
    { estado: "OPEN_LUNCH_ONLY", luzesAcesas: true, portaAberta: true },
  ));
  await aguardarAte(() => escuridao.alpha < 0.05, "as luzes continuarem acesas no almoço");
  jogo.destroy(true);
});

test("pendencia de ponto aparece na faixa sem expor a pessoa", async () => {
  const { cena: palco, jogo } = await abrirCena();
  const faixa = (palco as unknown as { faixa: Phaser.GameObjects.Text }).faixa;

  palco.aplicar(cena(
    [personagem({ estado: "MISSING_PUNCH", sala: null, inconsistencia: "MISSING_PUNCH" })],
    { estado: "CLOSED_WITH_PENDING", luzesAcesas: false, portaAberta: false, pendencias: 1 },
  ));
  await espera(60);

  assert.match(faixa.text, /conferir/i);
  assert.ok(!faixa.text.includes("Tina"), "a faixa nao nomeia ninguem");
  jogo.destroy(true);
});

test("planta nova redesenha o mapa sem perder as personagens", async () => {
  const { cena: palco, jogo, atores } = await abrirCena();

  palco.aplicar(cena([personagem()]));
  await espera(60);
  assert.equal(atores.size, 1);

  const ampliada = [...PLANTA, sala("showroom-3", "Showroom 3", 900, 0, 300, 220)];
  palco.aplicar(cena([personagem({ sala: "showroom-3" })], {}, ampliada));
  await espera(60);

  assert.equal(atores.size, 1, "a personagem nao pode ser destruida ao redesenhar");
  assert.ok(jogo.scale.width >= 1200, `canvas nao acompanhou a planta: ${jogo.scale.width}`);
  jogo.destroy(true);
});

test("aplicar a mesma cena varias vezes e' inofensivo", async () => {
  const { cena: palco, jogo, atores } = await abrirCena();
  const payload = cena([personagem()]);

  for (let i = 0; i < 12; i += 1) palco.aplicar(payload);
  await espera(200);

  assert.equal(atores.size, 1);
  assert.equal(atores.get(1).estaVisivel, true);
  jogo.destroy(true);
});

test("payload sem personagem nenhuma nao quebra a cena", async () => {
  const { cena: palco, jogo, atores } = await abrirCena();
  palco.aplicar(cena([], { estado: "CLOSED", luzesAcesas: false, portaAberta: false }));
  await espera(60);
  assert.equal(atores.size, 0);
  jogo.destroy(true);
});

test("personagem com sala desconhecida na planta nao quebra", async () => {
  const { cena: palco, jogo, atores } = await abrirCena();
  palco.aplicar(cena([personagem({ sala: "sala-que-nao-existe" })]));
  await espera(60);
  assert.equal(atores.size, 1);
  assert.equal(atores.get(1).estaVisivel, false, "sem vaga, fica fora de cena");
  jogo.destroy(true);
});
