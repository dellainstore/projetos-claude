/**
 * Teste de fumaça da nova cena (imagem de fundo real + zonas + personagens
 * pixel art). Sobe o Phaser em HEADLESS e aplica payloads reais da API.
 *
 * Não verifica pixel: verifica COMPORTAMENTO (personagens aparecem/somem,
 * luz por ambiente reage à ocupação, caminhada acontece pela rota certa) e,
 * acima de tudo, que o código Phaser roda de verdade.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { prepararDOM } from "./ambiente-dom";

prepararDOM();

// Ver cena.test.ts (versão anterior) para o porquê deste require tardio e
// do uso da árvore de fontes do Phaser em vez do bundle `dist`.
const Phaser = require("phaser") as typeof import("phaser");
const { OfficeScene } = require("../src/scenes/OfficeScene") as typeof import("../src/scenes/OfficeScene");

import type { Cena, Personagem, Sala } from "../src/types";

function sala(slug: string, nome: string): Sala {
  // A geometria (pos_x/pos_y/largura/altura) não importa mais para a
  // renderização: a posição na tela vem de `config/officeZones.ts`, não do
  // backend. Só o `slug` precisa bater com o que a API manda de verdade.
  return { slug, nome, ordem: 0, pos_x: 0, pos_y: 0, largura: 100, altura: 100 };
}

const PLANTA: Sala[] = [
  sala("store-entrance", "Entrada"),
  sala("showroom", "Show Room"),
  sala("corredor", "Corredor"),
  sala("anaca", "Anacã"),
  sala("cafeteria", "Refeitório"),
];

function personagem(p: Partial<Personagem> = {}): Personagem {
  return {
    id: 1, personagem: "tina", nome: "Tina", tipoAtor: "HUMAN_EMPLOYEE",
    estado: "WORKING", estadoEstavel: "WORKING",
    desde: "2026-09-14T09:00:00-03:00",
    sala: "showroom", salaTrabalho: "showroom", salaOrigem: "loja",
    posX: 0, posY: 0, evento: null, inconsistencia: null,
    ...p,
  };
}

function cena(
  personagens: Personagem[], loja: Partial<Cena["loja"]> = {}, salas: Sala[] = PLANTA,
): Cena {
  return {
    preview: { ativo: false },
    versao: 1,
    data: "2026-09-14",
    geradoEm: "2026-09-14T09:00:00-03:00",
    pollSegundos: 10,
    loja: { estado: "OPEN", luzesAcesas: true, portaAberta: true, pendencias: 0, ...loja },
    salas,
    personagens,
    avisos: [],
  };
}

const espera = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function aguardarAte(condicao: () => boolean, descricao: string, limiteMs = 8000): Promise<void> {
  const fim = Date.now() + limiteMs;
  while (Date.now() < fim) {
    if (condicao()) return;
    await espera(40);
  }
  assert.fail(`tempo esgotado esperando: ${descricao}`);
}

async function abrirCena(): Promise<{ cena: InstanceType<typeof OfficeScene>; jogo: Phaser.Game }> {
  const jogo = new Phaser.Game({
    type: Phaser.HEADLESS,
    parent: document.getElementById("palco") as HTMLElement,
    width: 1440,
    height: 900,
    banner: false,
    audio: { noAudio: true },
    scene: [OfficeScene],
  });

  await new Promise<void>((resolve) => jogo.events.once("ready", () => resolve()));
  // `ready` é emitido ANTES de `Game.start()`; espera o boot fechar.
  await espera(30);

  // O jsdom nunca dá foco à janela, então o VisibilityHandler do Phaser
  // dispara BLUR e o jogo entra em `isPaused` — nesse estado o `headlessStep`
  // retorna cedo e NENHUM tween avança. NÃO chamar `loop.stop()` aqui: o
  // loop headless (via requestAnimationFrame do jsdom) é o que mantém os
  // tweens andando pelo relógio real; pará-lo congelaria tudo.
  (jogo as unknown as { isPaused: boolean }).isPaused = false;

  const alvo = jogo.scene.getScene("escritorio") as InstanceType<typeof OfficeScene>;
  assert.ok(alvo, "a cena precisa existir depois do boot");
  return { cena: alvo, jogo };
}

test("a cena boota sem imagem de fundo carregada e não quebra", async () => {
  const { jogo } = await abrirCena();
  jogo.destroy(true);
});

test("cria uma personagem por item do payload e destrói quem sai do elenco", async () => {
  const { cena: palco, jogo } = await abrirCena();

  palco.aplicar(cena([
    personagem({ id: 1, personagem: "tina", nome: "Tina", sala: "showroom" }),
    personagem({ id: 2, personagem: "sara", nome: "Sara", sala: "showroom" }),
    personagem({ id: 3, personagem: "michelle", nome: "Michelle", sala: "anaca", salaTrabalho: "anaca" }),
  ]));
  await espera(60);
  assert.equal(palco.elenco().size, 3);

  palco.aplicar(cena([
    personagem({ id: 1, personagem: "tina", nome: "Tina", sala: "showroom" }),
  ]));
  await espera(60);
  assert.equal(palco.elenco().size, 1);
  assert.ok(!palco.elenco().has(3));
  jogo.destroy(true);
});

test("colegas do mesmo ambiente não ficam na mesma posição", async () => {
  const { cena: palco, jogo } = await abrirCena();
  palco.aplicar(cena([
    personagem({ id: 1, nome: "Tina", sala: "showroom" }),
    personagem({ id: 2, personagem: "sara", nome: "Sara", sala: "showroom" }),
  ]));
  await espera(60);
  const [a, b] = [...palco.elenco().values()];
  assert.notEqual(a.x, b.x, "duas pessoas no mesmo ambiente não podem se sobrepor");
  jogo.destroy(true);
});

test("quem está fora de cena (sala=null) fica invisível", async () => {
  const { cena: palco, jogo } = await abrirCena();
  palco.aplicar(cena([
    personagem({ id: 1, estado: "DAY_OFF", sala: null }),
    personagem({ id: 2, personagem: "sara", nome: "Sara", estado: "WORKING", sala: "showroom" }),
  ]));
  await espera(60);
  assert.equal(palco.elenco().get(1)!.estaVisivel, false);
  assert.equal(palco.elenco().get(2)!.estaVisivel, true);
  jogo.destroy(true);
});

test("ir para o almoço muda a sala para cafeteria e a personagem caminha", async () => {
  const { cena: palco, jogo } = await abrirCena();
  palco.aplicar(cena([personagem({ estado: "WORKING", sala: "showroom" })]));
  await espera(60);
  const ator = palco.elenco().get(1)!;
  const antes = { x: ator.x, y: ator.y };

  palco.aplicar(cena([personagem({ estado: "LUNCH", sala: "cafeteria" })]));
  await aguardarAte(() => ator.x !== antes.x || ator.y !== antes.y, "a personagem sair do lugar");
  await aguardarAte(() => ator.salaAtual === "cafeteria", "a personagem chegar à cafeteria");
  jogo.destroy(true);
});

test("o estado do servidor cancela uma caminhada em andamento", async () => {
  const { cena: palco, jogo } = await abrirCena();
  palco.aplicar(cena([personagem({ estado: "WORKING", sala: "showroom" })]));
  await espera(60);
  const ator = palco.elenco().get(1)!;

  palco.aplicar(cena([personagem({ estado: "LUNCH", sala: "cafeteria" })]));
  await espera(120); // no meio do caminho...
  palco.aplicar(cena([personagem({ estado: "WORKING", sala: "anaca", salaTrabalho: "anaca" })]));

  await aguardarAte(() => ator.salaAtual === "anaca", "obedecer ao servidor e ir para a Anacã");
  jogo.destroy(true);
});

test("sair do expediente esconde a personagem depois de ela caminhar até a porta", async () => {
  const { cena: palco, jogo } = await abrirCena();
  palco.aplicar(cena([personagem({ estado: "WORKING", sala: "showroom" })]));
  await espera(60);
  const ator = palco.elenco().get(1)!;
  assert.equal(ator.estaVisivel, true);

  palco.aplicar(cena([personagem({ estado: "OFF_SHIFT", sala: null })]));
  await aguardarAte(() => !ator.estaVisivel, "a personagem sumir de cena");
  jogo.destroy(true);
});

test("a luz é por ambiente: acende onde tem gente, apaga o resto", async () => {
  const { cena: palco, jogo } = await abrirCena();
  palco.aplicar(cena(
    [personagem({ estado: "WORKING", sala: "showroom" })], { estado: "OPEN", luzesAcesas: true },
  ));
  await espera(60);
  assert.ok(palco.opacidadeDaLuz("showroom")! < 0.05, "showroom ocupado deveria acender");
  assert.ok(palco.opacidadeDaLuz("anaca")! > 0.2, "anacã vazia deveria ficar na penumbra");
  assert.ok(palco.opacidadeDaLuz("corredor")! < 0.05, "circulação fica acesa com a loja aberta");
  jogo.destroy(true);
});

test("almoço de todas mantém o refeitório aceso e não é tratado como loja fechada", async () => {
  const { cena: palco, jogo } = await abrirCena();
  palco.aplicar(cena(
    [personagem({ estado: "LUNCH", sala: "cafeteria" })], { estado: "OPEN_LUNCH_ONLY", luzesAcesas: true },
  ));
  await espera(60);
  assert.ok(palco.opacidadeDaLuz("cafeteria")! < 0.05);
  jogo.destroy(true);
});

test("loja fechada apaga todos os ambientes", async () => {
  const { cena: palco, jogo } = await abrirCena();
  palco.aplicar(cena([personagem({ estado: "WORKING", sala: "showroom" })]));
  await espera(60);
  palco.aplicar(cena(
    [personagem({ estado: "OFF_SHIFT", sala: null })], { estado: "CLOSED", luzesAcesas: false, portaAberta: false },
  ));
  await aguardarAte(() => palco.opacidadeDaLuz("showroom")! > 0.5, "o showroom apagar");
  jogo.destroy(true);
});

test("payload sem personagem nenhuma não quebra a cena", async () => {
  const { cena: palco, jogo } = await abrirCena();
  palco.aplicar(cena([], { estado: "CLOSED", luzesAcesas: false, portaAberta: false }));
  await espera(60);
  assert.equal(palco.elenco().size, 0);
  jogo.destroy(true);
});

test("aplicar a mesma cena várias vezes é inofensivo", async () => {
  const { cena: palco, jogo } = await abrirCena();
  const payload = cena([personagem()]);
  for (let i = 0; i < 8; i += 1) palco.aplicar(payload);
  await espera(150);
  assert.equal(palco.elenco().size, 1);
  jogo.destroy(true);
});
