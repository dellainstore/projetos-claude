/** Testes do grafo de rotas sobre a imagem (coordenadas normalizadas). */
import assert from "node:assert/strict";
import test from "node:test";

import { OFFICE_POINTS, OFFICE_PATHS, buildWalkPath } from "../src/config/officePaths";

test("caminho dentro do mesmo ambiente vai direto ao ponto", () => {
  const destino = { x: 0.3, y: 0.5 };
  const rota = buildWalkPath("showroom", { x: 0.1, y: 0.5 }, "showroom", destino);
  assert.deepEqual(rota, [destino]);
});

test("da entrada ao showroom passa pelo corredor e pela porta", () => {
  const rota = buildWalkPath(
    "store-entrance", OFFICE_POINTS.entrance_inside, "showroom", OFFICE_POINTS.showroom_door,
  );
  assert.ok(rota.some((p) => p === OFFICE_POINTS.hall_bottom || (p.x === OFFICE_POINTS.hall_bottom.x && p.y === OFFICE_POINTS.hall_bottom.y)));
  assert.ok(rota[rota.length - 1] === OFFICE_POINTS.showroom_door || (rota[rota.length - 1].x === OFFICE_POINTS.showroom_door.x));
});

test("showroom para anaca passa pelo corredor central", () => {
  const rota = buildWalkPath("showroom", OFFICE_POINTS.showroom_door, "anaca", OFFICE_POINTS.anaca_door);
  const passaPeloCentro = rota.some((p) => p.x === OFFICE_POINTS.hall_center.x && p.y === OFFICE_POINTS.hall_center.y);
  assert.ok(passaPeloCentro, "deveria passar por hall_center");
});

test("showroom ate o refeitorio passa pelo hall_top", () => {
  const rota = buildWalkPath("showroom", OFFICE_POINTS.showroom_door, "cafeteria", OFFICE_POINTS.cafeteria_door);
  assert.ok(rota.some((p) => p.x === OFFICE_POINTS.hall_top.x && p.y === OFFICE_POINTS.hall_top.y));
});

test("sair da loja (room=null) usa o ponto fora do predio", () => {
  const rota = buildWalkPath("anaca", OFFICE_POINTS.anaca_door, null, OFFICE_POINTS.entrance_outside);
  assert.deepEqual(rota[rota.length - 1], OFFICE_POINTS.entrance_outside);
});

test("nao repete o ponto de partida quando ja coincide com a porta", () => {
  const rota = buildWalkPath("showroom", OFFICE_POINTS.showroom_door, "anaca", OFFICE_POINTS.anaca_door);
  assert.notDeepEqual(rota[0], OFFICE_POINTS.showroom_door, "não deveria repetir o ponto de origem");
});

test("as rotas nomeadas de alto nivel existem e nao sao vazias", () => {
  for (const nome of Object.keys(OFFICE_PATHS) as Array<keyof typeof OFFICE_PATHS>) {
    assert.ok(OFFICE_PATHS[nome].length > 0, `rota ${nome} vazia`);
  }
});
