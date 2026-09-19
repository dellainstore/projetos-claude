/** Testes do controle de animacoes (nao repetir o mesmo eventId). */

import assert from "node:assert/strict";
import test from "node:test";

import { ControleDeAnimacoes, estadosQueMudaram } from "../src/state/diff";
import type { Cena, Personagem } from "../src/types";

function personagem(parcial: Partial<Personagem> = {}): Personagem {
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
    ...parcial,
  };
}

function cena(personagens: Personagem[]): Cena {
  return {
    preview: { ativo: false },
    versao: 1,
    data: "2026-09-14",
    geradoEm: "2026-09-14T09:00:00-03:00",
    pollSegundos: 10,
    loja: { estado: "OPEN", luzesAcesas: true, portaAberta: true, pendencias: 0 },
    salas: [],
    personagens,
    avisos: [],
  };
}

test("mesmo eventId so anima uma vez, mesmo repetido em varios polls", () => {
  const controle = new ControleDeAnimacoes();
  const comEvento = cena([
    personagem({
      estado: "ARRIVING",
      evento: { eventId: "ponto_42", event: "CLOCK_IN", occurredAt: "2026-09-14T09:00:00-03:00" },
    }),
  ]);

  assert.equal(controle.novasTransicoes(comEvento).length, 1);
  assert.equal(controle.novasTransicoes(comEvento).length, 0);
  assert.equal(controle.novasTransicoes(comEvento).length, 0);
  assert.ok(controle.jaViu("ponto_42"));
});

test("eventId diferente anima de novo", () => {
  const controle = new ControleDeAnimacoes();
  const chegada = cena([
    personagem({
      evento: { eventId: "ponto_1", event: "CLOCK_IN", occurredAt: "x" },
    }),
  ]);
  const saida = cena([
    personagem({
      evento: { eventId: "ponto_2", event: "CLOCK_OUT", occurredAt: "x" },
    }),
  ]);

  assert.equal(controle.novasTransicoes(chegada).length, 1);
  const novas = controle.novasTransicoes(saida);
  assert.equal(novas.length, 1);
  assert.equal(novas[0].evento, "CLOCK_OUT");
});

test("cena sem evento nao gera transicao", () => {
  const controle = new ControleDeAnimacoes();
  assert.equal(controle.novasTransicoes(cena([personagem()])).length, 0);
});

test("varias personagens animam independentemente", () => {
  const controle = new ControleDeAnimacoes();
  const duas = cena([
    personagem({
      id: 1,
      evento: { eventId: "ponto_1", event: "CLOCK_IN", occurredAt: "x" },
    }),
    personagem({
      id: 2,
      personagem: "sara",
      nome: "Sara",
      evento: { eventId: "ponto_2", event: "CLOCK_IN", occurredAt: "x" },
    }),
  ]);
  assert.equal(controle.novasTransicoes(duas).length, 2);
  assert.equal(controle.novasTransicoes(duas).length, 0);
});

test("o limite descarta os mais antigos sem quebrar", () => {
  const controle = new ControleDeAnimacoes(3);
  for (let i = 1; i <= 4; i += 1) {
    controle.novasTransicoes(
      cena([
        personagem({
          evento: { eventId: `ponto_${i}`, event: "CLOCK_IN", occurredAt: "x" },
        }),
      ]),
    );
  }
  assert.ok(!controle.jaViu("ponto_1"), "o mais antigo saiu");
  assert.ok(controle.jaViu("ponto_4"));
});

test("limpar zera o historico", () => {
  const controle = new ControleDeAnimacoes();
  const c = cena([
    personagem({ evento: { eventId: "ponto_9", event: "CLOCK_IN", occurredAt: "x" } }),
  ]);
  controle.novasTransicoes(c);
  controle.limpar();
  assert.equal(controle.novasTransicoes(c).length, 1);
});

test("estadosQueMudaram compara com a cena anterior", () => {
  const antes = cena([personagem({ id: 1, estado: "WORKING" })]);
  const depois = cena([personagem({ id: 1, estado: "LUNCH" })]);
  assert.deepEqual([...estadosQueMudaram(antes, depois)], [1]);
  assert.deepEqual([...estadosQueMudaram(antes, antes)], []);
  assert.deepEqual([...estadosQueMudaram(null, depois)], [], "primeira carga nao destaca nada");
});
