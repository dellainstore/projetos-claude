/**
 * Testes do painel de simulacao.
 *
 * A afirmacao que este arquivo existe para provar: o painel NAO cria batida,
 * NAO chama endpoint de escrita e NAO toca no banco. Ele so transforma a cena
 * que ja esta na tela. Se alguem um dia acrescentar um `fetch` ali, um teste
 * quebra.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { prepararDOM } from "./ambiente-dom";

prepararDOM();

const { DebugPanel, podeSimular } =
  require("../src/ui/DebugPanel") as typeof import("../src/ui/DebugPanel");
const { OfficeStore } =
  require("../src/state/officeStore") as typeof import("../src/state/officeStore");

import type { Cena, Personagem } from "../src/types";
import { PLANTA } from "./planta";

function pessoa(id: number, nome: string, salaTrabalho: string): Personagem {
  return {
    id, personagem: nome.toLowerCase(), nome, tipoAtor: "HUMAN_EMPLOYEE",
    estado: "OFF_SHIFT", estadoEstavel: "OFF_SHIFT",
    desde: null, sala: null, salaTrabalho, salaOrigem: "loja",
    posX: 0, posY: 0, evento: null, inconsistencia: null,
  };
}

function cena(): Cena {
  return {
    preview: { ativo: false },
    versao: 1,
    data: "2026-09-18",
    geradoEm: "2026-09-18T10:00:00-03:00",
    pollSegundos: 10,
    loja: { estado: "CLOSED", luzesAcesas: false, portaAberta: false, pendencias: 0 },
    salas: PLANTA,
    personagens: [
      pessoa(1, "Tina", "showroom"),
      pessoa(2, "Sara", "showroom"),
      pessoa(3, "Michelle", "anaca"),
    ],
    avisos: [],
  };
}

function montar() {
  const destino = document.createElement("div");
  document.body.appendChild(destino);
  const store = new OfficeStore();
  store.receberDaApi(cena());
  const painel = new DebugPanel(destino, store);
  painel.montar();
  return { destino, store, painel };
}

function clicar(destino: HTMLElement, pessoa: string, rotulo: string): void {
  const linhas = [...destino.querySelectorAll(".ev-debug-linha")];
  const linha = linhas.find(
    (l) => l.querySelector(".ev-debug-nome")?.textContent === pessoa,
  );
  assert.ok(linha, `linha não encontrada para ${pessoa}`);
  const botao = [...linha!.querySelectorAll("button")].find(
    (b) => b.textContent === rotulo,
  );
  assert.ok(botao, `botão "${rotulo}" não encontrado em ${pessoa}`);
  (botao as HTMLButtonElement).click();
}

test("o painel só aparece quando o servidor autoriza", () => {
  const raiz = document.createElement("div");
  assert.equal(podeSimular(raiz), false, "sem atributo, não aparece");
  raiz.dataset.debug = "0";
  assert.equal(podeSimular(raiz), false);
  raiz.dataset.debug = "1";
  assert.equal(podeSimular(raiz), true);
});

test("monta um grupo de botões por personagem, mais os da loja", () => {
  const { destino } = montar();
  const nomes = [...destino.querySelectorAll(".ev-debug-nome")]
    .map((e) => e.textContent);
  assert.deepEqual(nomes, ["Tina", "Sara", "Michelle", "Loja"]);
});

test("entrar leva a personagem para a entrada e abre a loja", () => {
  const { destino, store } = montar();
  clicar(destino, "Tina", "entrar");

  const tina = store.atual!.personagens.find((p) => p.id === 1)!;
  assert.equal(tina.estado, "ARRIVING");
  assert.equal(tina.sala, "store-entrance");
  assert.equal(store.atual!.loja.estado, "OPEN", "chegou alguém, a loja abre");
  assert.ok(store.simulando);
});

test("trabalhar usa a sala do CADASTRO, não o nome da pessoa", () => {
  const { destino, store } = montar();
  clicar(destino, "Michelle", "trabalhar");
  const michelle = store.atual!.personagens.find((p) => p.id === 3)!;
  assert.equal(michelle.sala, "anaca", "veio de salaTrabalho, não de uma lista fixa");

  clicar(destino, "Tina", "trabalhar");
  assert.equal(store.atual!.personagens.find((p) => p.id === 1)!.sala, "showroom");
});

test("almoço manda ao refeitório e a loja NÃO fecha", () => {
  const { destino, store } = montar();
  clicar(destino, "Tina", "almoço");
  const tina = store.atual!.personagens.find((p) => p.id === 1)!;
  assert.equal(tina.estado, "LUNCH");
  assert.equal(tina.sala, "cafeteria");
  assert.equal(store.atual!.loja.estado, "OPEN_LUNCH_ONLY");
  assert.equal(store.atual!.loja.luzesAcesas, true);
});

test("fechar a loja tira todo mundo de cena", () => {
  const { destino, store } = montar();
  clicar(destino, "Tina", "trabalhar");
  clicar(destino, "Loja", "fechar");
  assert.equal(store.atual!.loja.estado, "CLOSED");
  assert.ok(store.atual!.personagens.every((p) => p.sala === null));
});

test("voltar ao vivo devolve o comando para a API", () => {
  const { destino, store } = montar();
  clicar(destino, "Tina", "entrar");
  assert.ok(store.simulando);
  clicar(destino, "Loja", "voltar ao vivo");
  assert.ok(!store.simulando);
  assert.equal(store.atual!.loja.estado, "CLOSED", "voltou a cena da API");
});

test("NENHUM botão faz requisição: o painel não escreve em lugar nenhum", () => {
  const original = globalThis.fetch;
  const chamadas: string[] = [];
  (globalThis as { fetch: unknown }).fetch = (...args: unknown[]) => {
    chamadas.push(String(args[0]));
    return Promise.reject(new Error("o painel de simulação não pode chamar a API"));
  };

  try {
    const { destino } = montar();
    const botoes = [...destino.querySelectorAll("button")];
    assert.ok(botoes.length >= 20, "poucos botões para um teste honesto");
    for (const b of botoes) (b as HTMLButtonElement).click();
    assert.deepEqual(chamadas, [], `o painel chamou a API: ${chamadas.join(", ")}`);
  } finally {
    (globalThis as { fetch: unknown }).fetch = original;
  }
});

test("destruir limpa os ouvintes e some da tela", () => {
  const { destino, painel, store } = montar();
  painel.destruir();
  assert.equal(destino.querySelector(".ev-debug"), null);
  // Nada quebra se a cena continuar chegando depois.
  store.receberDaApi(cena());
});
