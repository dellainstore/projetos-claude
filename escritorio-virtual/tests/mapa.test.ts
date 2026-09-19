/**
 * Testes da geometria do cenario. Modulo puro, roda sem Phaser e sem DOM.
 *
 * A planta usada aqui e' a que a migration de dados cria
 * (0002_salas_iniciais), para os numeros baterem com o que vai para a tela.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  caminho,
  centro,
  corredorY,
  distancia,
  limitesDoMundo,
  portaDaSala,
  vagaNaSala,
  vagasPorPersonagem,
} from "../src/cena/mapa";
import type { Sala } from "../src/types";

function sala(
  slug: string, pos_x: number, pos_y: number, largura: number, altura: number,
): Sala {
  return { slug, nome: slug, ordem: 0, pos_x, pos_y, largura, altura };
}

const ENTRADA = sala("store-entrance", 0, 240, 200, 140);
const SHOW1 = sala("showroom-1", 220, 0, 320, 220);
const SHOW2 = sala("showroom-2", 560, 0, 320, 220);
const REFEITORIO = sala("cafeteria", 220, 240, 320, 180);
const PLANTA = [ENTRADA, SHOW1, SHOW2, REFEITORIO];

test("limitesDoMundo cobre a sala mais distante", () => {
  assert.deepEqual(limitesDoMundo(PLANTA), { largura: 880, altura: 420 });
});

test("limitesDoMundo tem fallback para planta vazia", () => {
  const m = limitesDoMundo([]);
  assert.ok(m.largura > 0 && m.altura > 0);
});

test("corredorY encontra a faixa livre entre as fileiras de salas", () => {
  const y = corredorY(PLANTA);
  assert.ok(y !== null);
  // Showrooms terminam em 220; entrada e refeitorio comecam em 240.
  assert.ok(y! > 220 && y! < 240, `corredor fora da faixa livre: ${y}`);
});

test("corredorY e' null quando as salas cobrem tudo", () => {
  const coladas = [sala("a", 0, 0, 100, 200), sala("b", 100, 0, 100, 200)];
  assert.equal(corredorY(coladas), null);
});

test("corredorY e' null sem sala nenhuma", () => {
  assert.equal(corredorY([]), null);
});

test("corredorY acompanha uma planta diferente", () => {
  // Sala nova empurrando o corredor para outro lugar.
  const outra = [sala("a", 0, 0, 200, 100), sala("b", 0, 300, 200, 100)];
  const y = corredorY(outra);
  assert.ok(y !== null && y! > 100 && y! < 300);
});

test("centro fica no meio da sala", () => {
  assert.deepEqual(centro(SHOW1), { x: 380, y: 110 });
});

test("vagaNaSala centraliza uma personagem sozinha", () => {
  const v = vagaNaSala(SHOW1, 0, 1);
  assert.equal(v.x, 380);
  assert.ok(v.y > SHOW1.pos_y && v.y < SHOW1.pos_y + SHOW1.altura);
});

test("vagaNaSala distribui duas sem sobrepor e simetricamente", () => {
  const a = vagaNaSala(SHOW1, 0, 2);
  const b = vagaNaSala(SHOW1, 1, 2);
  assert.ok(a.x < b.x, "a primeira fica a esquerda");
  assert.ok(Math.abs(b.x - a.x) > 20, "precisa sobrar espaco entre elas");
  assert.equal((a.x + b.x) / 2, 380, "o grupo continua centralizado");
});

test("vagaNaSala nao estoura as paredes de uma sala estreita", () => {
  const estreita = sala("mini", 0, 0, 90, 100);
  for (let i = 0; i < 4; i += 1) {
    const v = vagaNaSala(estreita, i, 4);
    assert.ok(v.x >= -1 && v.x <= 91, `vaga fora da sala: ${v.x}`);
  }
});

test("portaDaSala prende o Y na borda voltada para o corredor", () => {
  const corredor = 230;
  const deCima = portaDaSala(SHOW1, corredor);
  assert.equal(deCima.y, 220, "showroom sai pela base");
  const deBaixo = portaDaSala(REFEITORIO, corredor);
  assert.equal(deBaixo.y, 240, "refeitorio sai pelo topo");
});

test("portaDaSala sem corredor devolve o centro", () => {
  assert.deepEqual(portaDaSala(SHOW1, null), centro(SHOW1));
});

test("caminho dentro da mesma sala vai direto", () => {
  const pontos = caminho({ x: 300, y: 130 }, { x: 400, y: 130 }, SHOW1, SHOW1, 230);
  assert.deepEqual(pontos, [{ x: 400, y: 130 }]);
});

test("caminho entre salas passa pelo corredor", () => {
  const corredor = corredorY(PLANTA)!;
  const origem = vagaNaSala(SHOW1, 0, 1);
  const destino = vagaNaSala(REFEITORIO, 0, 1);
  const pontos = caminho(origem, destino, SHOW1, REFEITORIO, corredor);

  assert.ok(pontos.length >= 3, "precisa de trechos intermediarios");
  assert.ok(
    pontos.some((p) => Math.abs(p.y - corredor) < 0.51),
    "nenhum waypoint no corredor",
  );
  assert.deepEqual(pontos[pontos.length - 1], destino);
});

test("caminho sem corredor vai em linha reta", () => {
  const destino = { x: 400, y: 300 };
  assert.deepEqual(caminho({ x: 0, y: 0 }, destino, SHOW1, REFEITORIO, null), [destino]);
});

test("caminho sem sala de origem ou destino vai em linha reta", () => {
  const destino = { x: 10, y: 10 };
  assert.deepEqual(caminho({ x: 0, y: 0 }, destino, null, REFEITORIO, 230), [destino]);
  assert.deepEqual(caminho({ x: 0, y: 0 }, destino, SHOW1, null, 230), [destino]);
});

test("caminho nao repete waypoints iguais", () => {
  const corredor = corredorY(PLANTA)!;
  const pontos = caminho(
    portaDaSala(SHOW1, corredor), centro(SHOW2), SHOW1, SHOW2, corredor,
  );
  for (let i = 1; i < pontos.length; i += 1) {
    const igual =
      Math.abs(pontos[i].x - pontos[i - 1].x) < 0.5 &&
      Math.abs(pontos[i].y - pontos[i - 1].y) < 0.5;
    assert.ok(!igual, `waypoint repetido na posicao ${i}`);
  }
});

test("distancia soma os trechos", () => {
  const d = distancia({ x: 0, y: 0 }, [{ x: 3, y: 4 }, { x: 3, y: 14 }]);
  assert.equal(d, 15);
});

test("distancia de caminho vazio e' zero", () => {
  assert.equal(distancia({ x: 5, y: 5 }, []), 0);
});

test("vagasPorPersonagem agrupa por sala", () => {
  const vagas = vagasPorPersonagem(PLANTA, [
    { id: 1, sala: "showroom-1" },
    { id: 2, sala: "showroom-1" },
    { id: 3, sala: "showroom-2" },
  ]);
  assert.equal(vagas.size, 3);
  assert.notEqual(vagas.get(1)!.x, vagas.get(2)!.x, "colegas de sala nao se sobrepoem");
  assert.ok(vagas.get(3)!.x > 560, "a terceira esta no outro showroom");
});

test("vagasPorPersonagem ignora quem esta fora de cena", () => {
  const vagas = vagasPorPersonagem(PLANTA, [
    { id: 1, sala: null },
    { id: 2, sala: "showroom-1" },
  ]);
  assert.equal(vagas.size, 1);
  assert.ok(!vagas.has(1));
});

test("vagasPorPersonagem ignora sala que nao existe na planta", () => {
  const vagas = vagasPorPersonagem(PLANTA, [{ id: 1, sala: "deposito-secreto" }]);
  assert.equal(vagas.size, 0);
});

test("sala nova na planta funciona sem mudar codigo", () => {
  const ampliada = [...PLANTA, sala("showroom-3", 900, 0, 300, 220)];
  assert.equal(limitesDoMundo(ampliada).largura, 1200);
  const vagas = vagasPorPersonagem(ampliada, [{ id: 9, sala: "showroom-3" }]);
  assert.ok(vagas.get(9)!.x > 900);
  const corredor = corredorY(ampliada);
  assert.ok(corredor !== null && corredor > 220 && corredor < 240);
});
