/**
 * Testes da transicao da loja e do guarda-cena.
 *
 * Duas regras que so existem porque alguem decidiu: almoco NAO e' fim de
 * expediente, e uma simulacao nao pode ser apagada pelo proximo poll.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  lojaAberta,
  proximoEstadoDaPorta,
  repousoDaPorta,
  visualDaLoja,
  type EstadoPorta,
} from "../src/environment/StoreController";
import { OfficeStore } from "../src/state/officeStore";
import { assinaturaDaCena, resumoDaCena } from "../src/ui/painel";
import type { Cena, EstadoLoja, Personagem } from "../src/types";
import { PLANTA } from "./planta";

function pessoa(p: Partial<Personagem> = {}): Personagem {
  return {
    id: 1, personagem: "tina", nome: "Tina", tipoAtor: "HUMAN_EMPLOYEE",
    estado: "WORKING", estadoEstavel: "WORKING",
    desde: null, sala: "showroom", salaTrabalho: "showroom", salaOrigem: "loja",
    posX: 0, posY: 0, evento: null, inconsistencia: null,
    ...p,
  };
}

function cena(
  estado: EstadoLoja, personagens: Personagem[] = [], extra: Partial<Cena["loja"]> = {},
): Cena {
  const aberta = ["OPENING", "OPEN", "OPEN_LUNCH_ONLY"].includes(estado);
  return {
    preview: { ativo: false },
    versao: 1,
    data: "2026-09-18",
    geradoEm: "2026-09-18T10:00:00-03:00",
    pollSegundos: 10,
    loja: {
      estado, luzesAcesas: aberta, portaAberta: aberta, pendencias: 0, ...extra,
    },
    salas: PLANTA,
    personagens,
    avisos: [],
  };
}

// ── estado da loja ─────────────────────────────────────────────────────────

test("almoco de todas mantem a loja aberta", () => {
  assert.ok(lojaAberta("OPEN_LUNCH_ONLY"), "almoço não é fim de expediente");
  assert.ok(lojaAberta("OPEN"));
  assert.ok(lojaAberta("OPENING"));
  assert.ok(!lojaAberta("CLOSED"));
  assert.ok(!lojaAberta("CLOSED_WITH_PENDING"));
});

test("no almoco acende o refeitorio e apaga o comodo vazio", () => {
  const visual = visualDaLoja(
    cena("OPEN_LUNCH_ONLY", [pessoa({ estado: "LUNCH", sala: "cafeteria" })]),
    "OPEN",
  );
  assert.ok(visual.acesos.has("cafeteria"));
  assert.ok(!visual.acesos.has("showroom"));
  assert.ok(visual.acesos.has("corredor"), "circulação segue acesa");
  assert.match(visual.rotulo, /almoço/i);
});

test("loja fechada apaga tudo", () => {
  const visual = visualDaLoja(cena("CLOSED"), "OPEN");
  assert.equal(visual.acesos.size, 0);
  assert.equal(visual.porta, "CLOSING");
});

test("pendencia vira alerta, mas nao muda a cena", () => {
  const visual = visualDaLoja(
    cena("CLOSED_WITH_PENDING", [], { pendencias: 2 }), "CLOSED",
  );
  assert.ok(visual.alerta);
  assert.equal(visual.pendencias, 2);
  assert.equal(visual.acesos.size, 0, "ninguém trabalhando de madrugada");
  assert.ok(!visual.rotulo.includes("Tina"), "a faixa não nomeia ninguém");
});

// ── porta ──────────────────────────────────────────────────────────────────

test("a porta percorre CLOSED -> OPENING -> OPEN -> CLOSING -> CLOSED", () => {
  const aberta = cena("OPEN");
  const fechada = cena("CLOSED");

  let estado: EstadoPorta = "CLOSED";
  estado = proximoEstadoDaPorta(estado, aberta);
  assert.equal(estado, "OPENING");

  estado = repousoDaPorta(estado);
  assert.equal(estado, "OPEN");
  assert.equal(proximoEstadoDaPorta(estado, aberta), "OPEN", "aberta continua aberta");

  estado = proximoEstadoDaPorta(estado, fechada);
  assert.equal(estado, "CLOSING");

  estado = repousoDaPorta(estado);
  assert.equal(estado, "CLOSED");
  assert.equal(proximoEstadoDaPorta(estado, fechada), "CLOSED");
});

test("OPENING abre a porta mesmo antes de portaAberta virar true", () => {
  const abrindo = cena("OPENING", [], { portaAberta: false });
  assert.equal(proximoEstadoDaPorta("CLOSED", abrindo), "OPENING");
});

// ── guarda-cena ────────────────────────────────────────────────────────────

test("o store entrega a cena da API para quem assina", () => {
  const store = new OfficeStore();
  const recebidas: string[] = [];
  store.assinar((c, origem) => recebidas.push(`${c.loja.estado}:${origem}`));

  store.receberDaApi(cena("OPEN"));
  assert.deepEqual(recebidas, ["OPEN:api"]);
});

test("quem assina depois recebe a cena que ja esta valendo", () => {
  const store = new OfficeStore();
  store.receberDaApi(cena("OPEN"));
  let vista: string | null = null;
  store.assinar((c) => { vista = c.loja.estado; });
  assert.equal(vista, "OPEN");
});

test("a simulacao sobrepoe a API ate alguem voltar ao vivo", () => {
  const store = new OfficeStore();
  store.receberDaApi(cena("OPEN", [pessoa()]));

  store.simular((c) => ({ ...c, loja: { ...c.loja, estado: "CLOSED" } }));
  assert.equal(store.atual!.loja.estado, "CLOSED");
  assert.equal(store.origem, "simulado");
  assert.ok(store.simulando);

  // O poll seguinte chega, mas NAO apaga a simulacao no meio da animacao.
  store.receberDaApi(cena("OPEN_LUNCH_ONLY"));
  assert.equal(store.atual!.loja.estado, "CLOSED", "a simulação continua valendo");
  assert.equal(store.daApi!.loja.estado, "OPEN_LUNCH_ONLY", "mas a API foi guardada");

  store.voltarAoVivo();
  assert.equal(store.atual!.loja.estado, "OPEN_LUNCH_ONLY");
  assert.equal(store.origem, "api");
});

test("simular nao altera a cena guardada da API", () => {
  const store = new OfficeStore();
  store.receberDaApi(cena("OPEN", [pessoa({ estado: "WORKING" })]));
  store.simular((c) => ({
    ...c,
    personagens: c.personagens.map((p) => ({ ...p, estado: "LUNCH" as const })),
  }));
  assert.equal(store.daApi!.personagens[0].estado, "WORKING", "a original ficou intacta");
  assert.equal(store.atual!.personagens[0].estado, "LUNCH");
});

test("simular sem cena nenhuma nao quebra", () => {
  const store = new OfficeStore();
  store.simular((c) => c);
  assert.equal(store.atual, null);
});

test("voltar ao vivo sem simulacao ativa e' inofensivo", () => {
  const store = new OfficeStore();
  store.receberDaApi(cena("OPEN"));
  let avisos = 0;
  store.assinar(() => { avisos += 1; });
  const antes = avisos;
  store.voltarAoVivo();
  assert.equal(avisos, antes, "não deveria reemitir à toa");
});

test("cancelar a assinatura para de receber", () => {
  const store = new OfficeStore();
  let recebidas = 0;
  const cancelar = store.assinar(() => { recebidas += 1; });
  store.receberDaApi(cena("OPEN"));
  cancelar();
  store.receberDaApi(cena("CLOSED"));
  assert.equal(recebidas, 1);
});


// ── aviso da pre-visualizacao ──────────────────────────────────────────────
//
// Existe porque o bug relatado NAO era a requisicao: era a falta de retorno.
// A pessoa escolhia data e hora, a cena ficava parecida e parecia quebrado.

test("o resumo diz o que cada uma esta fazendo", () => {
  const c = cena("OPEN", [
    pessoa({ id: 1, nome: "Tina", estado: "WORKING" }),
    pessoa({ id: 2, nome: "Sara", estado: "LUNCH", sala: "cafeteria" }),
  ]);
  const texto = resumoDaCena(c);
  assert.match(texto, /Tina trabalhando/);
  assert.match(texto, /Sara no almoço/);
});

test("a assinatura muda quando a cena muda, e so quando muda", () => {
  const base = cena("OPEN", [pessoa({ estado: "WORKING" })]);
  const igual = cena("OPEN", [pessoa({ estado: "WORKING" })]);
  const outra = cena("OPEN", [pessoa({ estado: "LUNCH", sala: "cafeteria" })]);

  assert.equal(assinaturaDaCena(base), assinaturaDaCena(igual));
  assert.notEqual(assinaturaDaCena(base), assinaturaDaCena(outra));

  // Trocar so a hora do preview NAO conta como cena diferente: e' exatamente
  // o caso em que a tela precisa avisar "mesma situacao".
  const mesmaComOutraHora: Cena = {
    ...base, preview: { ativo: true, data: "2026-09-18", hora: "15:00" },
  };
  assert.equal(assinaturaDaCena(base), assinaturaDaCena(mesmaComOutraHora));
});
