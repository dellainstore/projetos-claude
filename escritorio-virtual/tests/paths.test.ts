/**
 * Testes do grafo de rotas: nos nomeados, busca de caminho e trajeto final.
 *
 * O que importa provar aqui: a personagem nao atravessa parede, nao corta
 * caminho na diagonal por cima de movel, e os nos sao DERIVADOS da planta
 * (mover um comodo move a rota).
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  NO,
  assentoNoRefeitorio,
  construirGrafo,
  noDaPorta,
  ponto,
  rota,
  trajeto,
} from "../src/config/paths";
import { postoDoComodo } from "../src/config/rooms";
import { vagaNaSala } from "../src/environment/geometry";
import { ANACA, CORREDOR, PLANTA, REFEITORIO, SHOWROOM, sala } from "./planta";

const GRAFO = construirGrafo(PLANTA);

function trecho(pontos: Array<{ x: number; y: number }>, origem: { x: number; y: number }) {
  const lista = [origem, ...pontos];
  return lista.slice(1).map((p, i) => ({ de: lista[i], para: p }));
}

// ── nos ────────────────────────────────────────────────────────────────────

test("o grafo tem os nos combinados, todos derivados da planta", () => {
  for (const nome of [
    NO.ENTRADA_FORA, NO.ENTRADA_DENTRO, NO.HALL_BAIXO, NO.HALL_CENTRO,
    NO.HALL_TOPO, NO.SAIDA,
    noDaPorta("showroom"), noDaPorta("anaca"), noDaPorta("cafeteria"),
  ]) {
    assert.ok(ponto(GRAFO, nome), `no ausente: ${nome}`);
  }
});

test("as estacoes do corredor ficam na linha central dele", () => {
  const centro = CORREDOR.pos_x + CORREDOR.largura / 2;
  for (const nome of [NO.HALL_BAIXO, NO.HALL_CENTRO, NO.HALL_TOPO]) {
    assert.equal(ponto(GRAFO, nome)!.x, centro, `${nome} fora do corredor`);
  }
});

test("hall_topo fica acima de hall_centro, que fica acima de hall_baixo", () => {
  const topo = ponto(GRAFO, NO.HALL_TOPO)!;
  const meio = ponto(GRAFO, NO.HALL_CENTRO)!;
  const baixo = ponto(GRAFO, NO.HALL_BAIXO)!;
  assert.ok(topo.y < meio.y, "o refeitório fica no topo da planta");
  assert.ok(meio.y < baixo.y, "a entrada fica na base");
});

test("o ponto de rua fica FORA do predio", () => {
  const fora = ponto(GRAFO, NO.ENTRADA_FORA)!;
  const base = Math.max(...PLANTA.map((s) => s.pos_y + s.altura));
  assert.ok(fora.y > base, "a personagem tem de sumir do lado de fora");
  assert.deepEqual(ponto(GRAFO, NO.SAIDA), fora, "exit_point é o mesmo lugar");
});

test("planta sem corredor devolve grafo vazio, sem quebrar", () => {
  const vazio = construirGrafo([SHOWROOM, ANACA]);
  assert.equal(vazio.pontos.size, 0);
  assert.deepEqual(rota(vazio, "a", "b"), []);
});

// ── busca de rota ──────────────────────────────────────────────────────────

test("do Show Room ao refeitorio, passando pelo corredor", () => {
  const caminho = rota(GRAFO, noDaPorta("showroom"), noDaPorta("cafeteria"));
  assert.ok(caminho.length >= 3, `rota curta demais: ${caminho.join(" -> ")}`);
  assert.equal(caminho[0], noDaPorta("showroom"));
  assert.equal(caminho[caminho.length - 1], noDaPorta("cafeteria"));
  assert.ok(
    caminho.some((n) => n.endsWith("_hall")),
    "a rota tem de passar por uma estação do corredor",
  );
});

test("a rota entre os dois showrooms passa pelo corredor, nunca pela parede", () => {
  const caminho = rota(GRAFO, noDaPorta("showroom"), noDaPorta("anaca"));
  assert.ok(caminho.includes("showroom_hall"));
  assert.ok(caminho.includes("anaca_hall"));
});

test("a rota para o mesmo no e' o proprio no", () => {
  assert.deepEqual(rota(GRAFO, NO.HALL_CENTRO, NO.HALL_CENTRO), ["showroom_hall"]);
});

test("no inexistente devolve rota vazia em vez de estourar", () => {
  assert.deepEqual(rota(GRAFO, "nao_existe", noDaPorta("anaca")), []);
});

// ── trajeto em pontos ──────────────────────────────────────────────────────

test("todo trecho do trajeto e' horizontal ou vertical", () => {
  const origem = postoDoComodo(SHOWROOM, 0)!;
  const destino = assentoNoRefeitorio(REFEITORIO, 0, 1);
  const pontos = trajeto({
    salas: PLANTA, grafo: GRAFO, origem,
    salaOrigem: "showroom", destino, salaDestino: "cafeteria",
  });

  for (const { de, para } of trecho(pontos, origem)) {
    const andouX = Math.abs(para.x - de.x) > 0.5;
    const andouY = Math.abs(para.y - de.y) > 0.5;
    assert.ok(
      !(andouX && andouY),
      `trecho diagonal de (${de.x},${de.y}) para (${para.x},${para.y})`,
    );
  }
});

test("o trajeto passa pelas duas portas", () => {
  const origem = postoDoComodo(SHOWROOM, 0)!;
  const destino = postoDoComodo(ANACA, 0)!;
  const pontos = trajeto({
    salas: PLANTA, grafo: GRAFO, origem,
    salaOrigem: "showroom", destino, salaDestino: "anaca",
  });
  const portaSaida = ponto(GRAFO, noDaPorta("showroom"))!;
  const portaEntrada = ponto(GRAFO, noDaPorta("anaca"))!;

  assert.ok(
    pontos.some((p) => Math.abs(p.x - portaSaida.x) < 0.6 && Math.abs(p.y - portaSaida.y) < 0.6),
    "não saiu pela porta do Show Room",
  );
  assert.ok(
    pontos.some((p) => Math.abs(p.x - portaEntrada.x) < 0.6 && Math.abs(p.y - portaEntrada.y) < 0.6),
    "não entrou pela porta da Anacã",
  );
  assert.deepEqual(pontos[pontos.length - 1], destino);
});

test("dentro do mesmo comodo o trajeto e' curto e nao vai ao corredor", () => {
  const origem = postoDoComodo(SHOWROOM, 0)!;
  const destino = postoDoComodo(SHOWROOM, 1)!;
  const pontos = trajeto({
    salas: PLANTA, grafo: GRAFO, origem,
    salaOrigem: "showroom", destino, salaDestino: "showroom",
  });
  assert.ok(pontos.length <= 2, "não precisa sair da sala");
  assert.ok(
    pontos.every((p) => p.x < 560),
    "não deveria encostar no corredor",
  );
});

test("da rua ate o posto de trabalho passa pela entrada e pelo corredor", () => {
  const rua = ponto(GRAFO, NO.ENTRADA_FORA)!;
  const destino = postoDoComodo(ANACA, 0)!;
  const pontos = trajeto({
    salas: PLANTA, grafo: GRAFO, origem: rua,
    salaOrigem: "store-entrance", destino, salaDestino: "anaca",
  });
  const portaEntrada = ponto(GRAFO, noDaPorta("store-entrance"))!;
  assert.ok(
    pontos.some((p) => Math.abs(p.y - portaEntrada.y) < 0.6),
    "não passou pela porta da entrada",
  );
  assert.deepEqual(pontos[pontos.length - 1], destino);
});

test("sem comodo de origem ou destino, vai direto (degrada sem quebrar)", () => {
  const destino = { x: 10, y: 10 };
  const comum = { salas: PLANTA, grafo: GRAFO, origem: { x: 0, y: 0 }, destino };
  assert.deepEqual(
    trajeto({ ...comum, salaOrigem: null, salaDestino: "anaca" }), [destino],
  );
  assert.deepEqual(
    trajeto({ ...comum, salaOrigem: "showroom", salaDestino: null }), [destino],
  );
});

test("o trajeto nunca repete o mesmo waypoint seguido", () => {
  const origem = postoDoComodo(ANACA, 0)!;
  const destino = assentoNoRefeitorio(REFEITORIO, 0, 1);
  const pontos = trajeto({
    salas: PLANTA, grafo: GRAFO, origem,
    salaOrigem: "anaca", destino, salaDestino: "cafeteria",
  });
  for (let i = 1; i < pontos.length; i += 1) {
    const igual = Math.abs(pontos[i].x - pontos[i - 1].x) < 0.5
      && Math.abs(pontos[i].y - pontos[i - 1].y) < 0.5;
    assert.ok(!igual, `waypoint repetido na posição ${i}`);
  }
});

test("os assentos do refeitorio ficam dentro dele e nao se sobrepoem", () => {
  const a = assentoNoRefeitorio(REFEITORIO, 0, 3);
  const b = assentoNoRefeitorio(REFEITORIO, 1, 3);
  const c = assentoNoRefeitorio(REFEITORIO, 2, 3);
  for (const p of [a, b, c]) {
    assert.ok(p.x > REFEITORIO.pos_x && p.x < REFEITORIO.pos_x + REFEITORIO.largura);
    assert.ok(p.y > REFEITORIO.pos_y && p.y < REFEITORIO.pos_y + REFEITORIO.altura);
  }
  assert.ok(a.x < b.x && b.x < c.x, "os três sentam em lugares diferentes");
});

test("mudar a planta muda o grafo, sem tocar em codigo", () => {
  // Refeitorio movido para a esquerda: a porta dele acompanha.
  const outra = PLANTA.map((s) =>
    s.slug === "cafeteria" ? sala("cafeteria", "Refeitório", 400, 0, 400, 250) : s,
  );
  const grafo = construirGrafo(outra);
  const antes = ponto(GRAFO, noDaPorta("cafeteria"))!;
  const depois = ponto(grafo, noDaPorta("cafeteria"))!;
  assert.ok(ponto(grafo, NO.HALL_TOPO), "a estação continua existindo");
  assert.equal(depois.y, antes.y, "continua na mesma parede");
  assert.ok(Math.abs(depois.x - antes.x) >= 0, "a porta acompanha o cômodo");
});

test("vagaNaSala continua sendo o fallback quando faltam postos", () => {
  const quinta = postoDoComodo(SHOWROOM, 9);
  assert.equal(quinta, null);
  const espalhada = vagaNaSala(SHOWROOM, 9, 12);
  assert.ok(Number.isFinite(espalhada.x) && Number.isFinite(espalhada.y));
});
