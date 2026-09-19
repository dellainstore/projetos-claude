/**
 * Testes do poller. Rodam no Node (sem navegador), com `fetch` e `document`
 * injetados. O objetivo e' provar as garantias do contrato: um timer, uma
 * requisicao em voo, 304 sem reconstruir, backoff, pausa na aba oculta.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { Poller } from "../src/state/poller";
import type { Cena } from "../src/types";

const URL_FAKE = "/escritorio/api/estado/";

function cenaFake(estadoLoja: Cena["loja"]["estado"] = "OPEN"): Cena {
  return {
    preview: { ativo: false },
    versao: 1,
    data: "2026-09-14",
    geradoEm: "2026-09-14T10:00:00-03:00",
    pollSegundos: 0, // 0 = nao sobrescreve o intervalo do teste
    loja: { estado: estadoLoja, luzesAcesas: true, portaAberta: true, pendencias: 0 },
    salas: [],
    personagens: [],
    avisos: [],
  };
}

/** `document` mínimo, com visibilidade controlável. */
function docFake() {
  const ouvintes = new Set<() => void>();
  return {
    hidden: false,
    addEventListener(_tipo: string, fn: any) {
      ouvintes.add(fn);
    },
    removeEventListener(_tipo: string, fn: any) {
      ouvintes.delete(fn);
    },
    disparar() {
      for (const fn of ouvintes) fn();
    },
    get qtdOuvintes() {
      return ouvintes.size;
    },
  };
}

function respostaOk(corpo: Cena, etag = '"abc"') {
  return new Response(JSON.stringify(corpo), {
    status: 200,
    headers: { "Content-Type": "application/json", ETag: etag },
  });
}

function resposta304(etag = '"abc"') {
  return new Response(null, { status: 304, headers: { ETag: etag } });
}

const espera = (ms: number) => new Promise((r) => setTimeout(r, ms));

test("primeira consulta nao manda If-None-Match; a segunda manda o ETag recebido", async () => {
  const chamadas: Array<Record<string, string>> = [];
  const poller = new Poller({
    url: URL_FAKE,
    intervaloMs: 20,
    doc: docFake() as any,
    fetchImpl: (async (_u: string, init: RequestInit) => {
      chamadas.push({ ...((init.headers ?? {}) as Record<string, string>) });
      return respostaOk(cenaFake(), '"etag-1"');
    }) as any,
    onCena: () => {},
    onSemMudanca: () => {},
    onErro: () => {},
  });

  poller.iniciar();
  await espera(60);
  poller.parar();

  assert.ok(chamadas.length >= 2, "deveria ter consultado mais de uma vez");
  assert.equal(chamadas[0]["If-None-Match"], undefined);
  assert.equal(chamadas[1]["If-None-Match"], '"etag-1"');
});

test("304 avisa sem-mudanca e nao entrega cena nova", async () => {
  let cenas = 0;
  let semMudanca = 0;
  let primeira = true;
  const poller = new Poller({
    url: URL_FAKE,
    intervaloMs: 15,
    doc: docFake() as any,
    fetchImpl: (async () => {
      if (primeira) {
        primeira = false;
        return respostaOk(cenaFake());
      }
      return resposta304();
    }) as any,
    onCena: () => {
      cenas += 1;
    },
    onSemMudanca: () => {
      semMudanca += 1;
    },
    onErro: () => {},
  });

  poller.iniciar();
  await espera(70);
  poller.parar();

  assert.equal(cenas, 1, "so a primeira resposta reconstroi a cena");
  assert.ok(semMudanca >= 2, "os 304 seguintes viram sem-mudanca");
});

test("nunca acumula timers: consultas nao se sobrepoem", async () => {
  let emVoo = 0;
  let maxSimultaneas = 0;
  let total = 0;
  const poller = new Poller({
    url: URL_FAKE,
    intervaloMs: 10,
    doc: docFake() as any,
    fetchImpl: (async () => {
      emVoo += 1;
      total += 1;
      maxSimultaneas = Math.max(maxSimultaneas, emVoo);
      await espera(25); // resposta mais lenta que o intervalo
      emVoo -= 1;
      return respostaOk(cenaFake());
    }) as any,
    onCena: () => {},
    onSemMudanca: () => {},
    onErro: () => {},
  });

  poller.iniciar();
  await espera(150);
  poller.parar();

  assert.equal(maxSimultaneas, 1, "so pode haver uma requisicao em voo");
  assert.ok(total <= 6, `consultas demais (${total}): timer duplicado`);
});

test("consultarAgora aborta a requisicao pendente", async () => {
  let abortadas = 0;
  const poller = new Poller({
    url: URL_FAKE,
    intervaloMs: 10_000,
    doc: docFake() as any,
    fetchImpl: (async (_u: string, init: RequestInit) => {
      const sinal = init.signal!;
      if (sinal.aborted) abortadas += 1;
      sinal.addEventListener("abort", () => {
        abortadas += 1;
      });
      await espera(40);
      return respostaOk(cenaFake());
    }) as any,
    onCena: () => {},
    onSemMudanca: () => {},
    onErro: () => {},
  });

  poller.iniciar();
  await espera(5);
  void poller.consultarAgora();
  await espera(60);
  poller.parar();

  assert.ok(abortadas >= 1, "a requisicao anterior deveria ter sido abortada");
});

test("falha aplica backoff exponencial com teto", async () => {
  const momentos: number[] = [];
  const poller = new Poller({
    url: URL_FAKE,
    intervaloMs: 20,
    backoffMaximoMs: 120,
    doc: docFake() as any,
    fetchImpl: (async () => {
      momentos.push(Date.now());
      throw new Error("rede caiu");
    }) as any,
    onCena: () => {},
    onSemMudanca: () => {},
    onErro: () => {},
  });

  poller.iniciar();
  await espera(200);
  poller.parar();

  assert.ok(momentos.length >= 3, "deveria ter tentado de novo");
  const primeiroIntervalo = momentos[1] - momentos[0];
  const segundoIntervalo = momentos[2] - momentos[1];
  assert.ok(
    segundoIntervalo > primeiroIntervalo,
    `backoff nao cresceu: ${primeiroIntervalo}ms -> ${segundoIntervalo}ms`,
  );
});

test("sucesso depois de falha volta ao intervalo normal", async () => {
  let falhar = true;
  let erros = 0;
  const poller = new Poller({
    url: URL_FAKE,
    intervaloMs: 15,
    doc: docFake() as any,
    fetchImpl: (async () => {
      if (falhar) throw new Error("offline");
      return respostaOk(cenaFake());
    }) as any,
    onCena: () => {},
    onSemMudanca: () => {},
    onErro: () => {
      erros += 1;
    },
  });

  poller.iniciar();
  await espera(40);
  falhar = false;
  await espera(120);
  const errosDepois = erros;
  await espera(60);
  poller.parar();

  assert.equal(erros, errosDepois, "nao deveria errar mais depois de voltar");
});

test("erro 403 avisa sem permissao e nao entrega cena", async () => {
  let mensagem = "";
  const poller = new Poller({
    url: URL_FAKE,
    intervaloMs: 10_000,
    doc: docFake() as any,
    fetchImpl: (async () =>
      new Response(JSON.stringify({ erro: "sem_permissao" }), { status: 403 })) as any,
    onCena: () => assert.fail("nao deveria entregar cena"),
    onSemMudanca: () => {},
    onErro: (m) => {
      mensagem = m;
    },
  });

  poller.iniciar();
  await espera(30);
  poller.parar();

  assert.match(mensagem, /permiss/i);
});

test("aba oculta pausa; voltar consulta na hora", async () => {
  const doc = docFake();
  let consultas = 0;
  const poller = new Poller({
    url: URL_FAKE,
    intervaloMs: 15,
    doc: doc as any,
    fetchImpl: (async () => {
      consultas += 1;
      return respostaOk(cenaFake());
    }) as any,
    onCena: () => {},
    onSemMudanca: () => {},
    onErro: () => {},
  });

  poller.iniciar();
  await espera(40);
  const antesDeEsconder = consultas;

  doc.hidden = true;
  doc.disparar();
  await espera(80);
  assert.equal(consultas, antesDeEsconder, "aba oculta nao pode continuar consultando");
  assert.equal(poller.msAteProximo(), 0, "sem agendamento pendente enquanto oculta");

  doc.hidden = false;
  doc.disparar();
  await espera(10);
  assert.ok(consultas > antesDeEsconder, "voltar para a aba deve consultar imediatamente");

  poller.parar();
});

test("parar limpa o ouvinte de visibilidade", async () => {
  const doc = docFake();
  const poller = new Poller({
    url: URL_FAKE,
    intervaloMs: 10_000,
    doc: doc as any,
    fetchImpl: (async () => respostaOk(cenaFake())) as any,
    onCena: () => {},
    onSemMudanca: () => {},
    onErro: () => {},
  });

  poller.iniciar();
  assert.equal(doc.qtdOuvintes, 1);
  await espera(10);
  poller.parar();
  assert.equal(doc.qtdOuvintes, 0);
});

test("iniciar duas vezes nao cria um segundo ciclo", async () => {
  const doc = docFake();
  let consultas = 0;
  const poller = new Poller({
    url: URL_FAKE,
    intervaloMs: 20,
    doc: doc as any,
    fetchImpl: (async () => {
      consultas += 1;
      return respostaOk(cenaFake());
    }) as any,
    onCena: () => {},
    onSemMudanca: () => {},
    onErro: () => {},
  });

  poller.iniciar();
  poller.iniciar();
  poller.iniciar();
  await espera(100);
  poller.parar();

  assert.equal(doc.qtdOuvintes, 0);
  assert.ok(consultas <= 7, `ciclos duplicados: ${consultas} consultas`);
});

test("servidor pode mudar o intervalo pelo payload", async () => {
  const momentos: number[] = [];
  const poller = new Poller({
    url: URL_FAKE,
    intervaloMs: 15,
    doc: docFake() as any,
    fetchImpl: (async () => {
      momentos.push(Date.now());
      return respostaOk({ ...cenaFake(), pollSegundos: 0.06 });
    }) as any,
    onCena: () => {},
    onSemMudanca: () => {},
    onErro: () => {},
  });

  poller.iniciar();
  await espera(200);
  poller.parar();

  const intervalo = momentos[2] - momentos[1];
  assert.ok(intervalo >= 50, `intervalo do servidor ignorado: ${intervalo}ms`);
});
