/**
 * Testes da geometria do cenario. Modulo puro: roda sem Phaser e sem DOM.
 *
 * O ponto central: a planta e as PORTAS vem do banco, nao de constante no
 * codigo. Mover um comodo muda parede e trajeto juntos.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  SLUG_CORREDOR,
  centro,
  comodosAcesos,
  corredorDe,
  corredorY,
  distancia,
  eixoDoCorredor,
  limitesDoMundo,
  portaDe,
  portaEntre,
  portas,
  salaPorSlug,
  vagaNaSala,
  vagasPorPersonagem,
} from "../src/environment/geometry";
import { postoDoComodo, silhueta } from "../src/config/rooms";
import { ANACA, CORREDOR, PLANTA, REFEITORIO, SHOWROOM, sala } from "./planta";

test("limitesDoMundo cobre o comodo mais distante", () => {
  assert.deepEqual(limitesDoMundo(PLANTA), { largura: 1440, altura: 900 });
});

test("a proporcao da planta e' a da imagem de referencia", () => {
  const { largura, altura } = limitesDoMundo(PLANTA);
  const proporcao = largura / altura;
  // A referencia tem 1462x907 (1,612). Tolerancia de 5%.
  assert.ok(Math.abs(proporcao - 1.612) < 0.08, `proporção fora: ${proporcao}`);
});

test("limitesDoMundo tem fallback para planta vazia", () => {
  const m = limitesDoMundo([]);
  assert.ok(m.largura > 0 && m.altura > 0);
});

test("o corredor e' uma sala de verdade, nao uma constante", () => {
  assert.equal(corredorDe(PLANTA)?.slug, SLUG_CORREDOR);
  assert.equal(corredorDe([SHOWROOM, ANACA]), null);
  assert.equal(salaPorSlug(PLANTA, "anaca")?.nome, "Anacã");
  assert.equal(salaPorSlug(PLANTA, null), null);
});

test("centro fica no meio do comodo", () => {
  assert.deepEqual(centro(SHOWROOM), { x: 280, y: 505 });
});

test("o corredor desta planta corre na vertical", () => {
  const eixo = eixoDoCorredor(CORREDOR);
  assert.equal(eixo.horizontal, false);
  assert.equal(eixo.centro, 720, "linha central do corredor");
});

// ── portas ─────────────────────────────────────────────────────────────────

test("cada comodo ganha uma porta para o corredor", () => {
  const slugs = portas(PLANTA).map((p) => p.slug).sort();
  assert.deepEqual(slugs, ["anaca", "cafeteria", "showroom", "store-entrance"]);
  assert.ok(!slugs.includes(SLUG_CORREDOR), "o corredor nao tem porta para si");
});

test("as portas ficam na parede compartilhada, no meio da fachada", () => {
  const showroom = portaDe(PLANTA, "showroom")!;
  assert.equal(showroom.x, 560, "parede entre Show Room e corredor");
  assert.equal(showroom.y, 505);
  assert.equal(showroom.horizontal, false, "parede vertical");

  const anaca = portaDe(PLANTA, "anaca")!;
  assert.equal(anaca.x, 880);
  assert.equal(anaca.y, 505);

  const refeitorio = portaDe(PLANTA, "cafeteria")!;
  assert.equal(refeitorio.y, 250, "comodo acima do corredor sai pela base");
  assert.equal(refeitorio.x, 720, "centrada no trecho em que encosta");
  assert.equal(refeitorio.horizontal, true);

  const entrada = portaDe(PLANTA, "store-entrance")!;
  assert.equal(entrada.y, 760, "comodo abaixo do corredor sai pelo topo");
  assert.equal(entrada.x, 720);
});

test("o vao da porta cabe na parede e tem tamanho razoavel", () => {
  for (const porta of portas(PLANTA)) {
    const comodo = salaPorSlug(PLANTA, porta.slug)!;
    assert.ok(porta.vao >= 34, `porta estreita demais em ${porta.slug}`);
    const eixo = porta.horizontal ? comodo.largura : comodo.altura;
    assert.ok(porta.vao <= eixo, `porta maior que a parede em ${porta.slug}`);
  }
});

test("comodo que nao encosta no corredor nao ganha porta", () => {
  const ilhado = sala("deposito", "Depósito", 2000, 2000, 100, 100);
  assert.equal(portaEntre(ilhado, CORREDOR), null);
  assert.equal(portaDe([...PLANTA, ilhado], "deposito"), null);
});

test("planta sem corredor nao tem porta nenhuma", () => {
  assert.deepEqual(portas([SHOWROOM, ANACA]), []);
});

test("distancia soma os trechos", () => {
  assert.equal(distancia({ x: 0, y: 0 }, [{ x: 3, y: 4 }, { x: 3, y: 14 }]), 15);
  assert.equal(distancia({ x: 5, y: 5 }, []), 0);
});

// ── vagas e postos ─────────────────────────────────────────────────────────

test("vagaNaSala centraliza uma personagem sozinha", () => {
  const v = vagaNaSala(SHOWROOM, 0, 1);
  assert.equal(v.x, 280);
  assert.ok(v.y > SHOWROOM.pos_y && v.y < SHOWROOM.pos_y + SHOWROOM.altura);
});

test("vagaNaSala distribui duas sem sobrepor e simetricamente", () => {
  const a = vagaNaSala(SHOWROOM, 0, 2);
  const b = vagaNaSala(SHOWROOM, 1, 2);
  assert.ok(a.x < b.x);
  assert.ok(b.x - a.x > 20, "precisa sobrar espaco entre elas");
  assert.equal((a.x + b.x) / 2, 280, "o grupo continua centralizado");
});

test("vagaNaSala nao estoura as paredes de um comodo estreito", () => {
  const estreito = sala("mini", "Mini", 0, 0, 90, 100);
  for (let i = 0; i < 4; i += 1) {
    const v = vagaNaSala(estreito, i, 4);
    assert.ok(v.x >= -1 && v.x <= 91, `vaga fora do comodo: ${v.x}`);
  }
});

test("os postos sao vagas por ordem de chegada, nao lugar de pessoa", () => {
  const primeiro = postoDoComodo(SHOWROOM, 0)!;
  const segundo = postoDoComodo(SHOWROOM, 1)!;
  assert.ok(primeiro, "o comodo precisa ter ao menos uma vaga");
  assert.notDeepEqual(primeiro, segundo, "duas pessoas nao ocupam a mesma vaga");
  // Todas dentro do comodo.
  for (const p of [primeiro, segundo]) {
    assert.ok(p.x > SHOWROOM.pos_x && p.x < SHOWROOM.pos_x + SHOWROOM.largura);
    assert.ok(p.y > SHOWROOM.pos_y && p.y < SHOWROOM.pos_y + SHOWROOM.altura);
  }
});

test("acabando as vagas configuradas, o posto vira null e o chamador espalha", () => {
  assert.equal(postoDoComodo(SHOWROOM, 99), null);
});

test("vagasPorPersonagem agrupa por comodo e ignora quem esta fora de cena", () => {
  const vagas = vagasPorPersonagem(PLANTA, [
    { id: 1, sala: "showroom" },
    { id: 2, sala: "showroom" },
    { id: 3, sala: "anaca" },
    { id: 4, sala: null },
    { id: 5, sala: "deposito-secreto" },
  ]);
  assert.equal(vagas.size, 3);
  assert.notEqual(vagas.get(1)!.x, vagas.get(2)!.x, "colegas de sala nao se sobrepoem");
  assert.ok(vagas.get(3)!.x > 880, "a terceira esta na Anacã");
  assert.ok(!vagas.has(4));
  assert.ok(!vagas.has(5));
});

// ── luz por comodo ─────────────────────────────────────────────────────────

test("com a loja fechada, nenhum comodo fica aceso", () => {
  assert.equal(comodosAcesos(PLANTA, false, [{ sala: "showroom" }]).size, 0);
});

test("com a loja aberta, acende onde tem gente mais a circulacao", () => {
  const acesos = comodosAcesos(PLANTA, true, [{ sala: "showroom" }]);
  assert.ok(acesos.has("showroom"), "o comodo ocupado acende");
  assert.ok(acesos.has("corredor"), "o corredor fica aceso");
  assert.ok(acesos.has("store-entrance"), "a entrada fica acesa");
  assert.ok(!acesos.has("anaca"), "comodo vazio fica apagado");
  assert.ok(!acesos.has("cafeteria"), "refeitório vazio fica apagado");
});

test("no almoco, acende o refeitorio e apaga o showroom vazio", () => {
  const acesos = comodosAcesos(PLANTA, true, [{ sala: "cafeteria" }]);
  assert.ok(acesos.has("cafeteria"));
  assert.ok(!acesos.has("showroom"));
});

test("quem esta fora de cena nao acende nada", () => {
  const acesos = comodosAcesos(PLANTA, true, [{ sala: null }]);
  assert.deepEqual([...acesos].sort(), ["corredor", "store-entrance"]);
});

// ── silhueta do predio ─────────────────────────────────────────────────────

test("a silhueta acompanha os degraus da planta", () => {
  const contorno = silhueta(PLANTA);
  assert.ok(contorno.length >= 8, "precisa de degraus, nao um retangulo");

  const xs = contorno.map((p) => p.x);
  const ys = contorno.map((p) => p.y);
  assert.equal(Math.min(...xs), 0);
  assert.equal(Math.max(...xs), 1440);
  assert.equal(Math.min(...ys), 0);
  assert.equal(Math.max(...ys), 900);

  // O bloco do refeitorio e' mais estreito que o corpo da loja: a silhueta
  // tem de mostrar isso, senao o predio vira uma caixa.
  const noTopo = contorno.filter((p) => p.y < 120);
  assert.ok(noTopo.length > 0, "sem pontos na faixa do refeitório");
  assert.ok(
    Math.min(...noTopo.map((p) => p.x)) > 300,
    "o topo deveria ser mais estreito que a base",
  );
});

test("a silhueta de uma planta retangular nao quebra", () => {
  const contorno = silhueta([sala("unica", "Única", 0, 0, 400, 300)]);
  assert.ok(contorno.length >= 4);
});

test("silhueta de planta vazia e' vazia", () => {
  assert.deepEqual(silhueta([]), []);
});

// ── fallback para plantas antigas ──────────────────────────────────────────

test("corredorY continua servindo de fallback para planta sem corredor", () => {
  const antiga = [
    sala("a", "A", 0, 0, 200, 100),
    sala("b", "B", 0, 300, 200, 100),
  ];
  const y = corredorY(antiga);
  assert.ok(y !== null && y > 100 && y < 300);
  assert.equal(corredorY([sala("cheio", "Cheio", 0, 0, 100, 100)]), null);
  assert.equal(corredorY([]), null);
});

test("comodo novo no banco ganha porta sozinho, sem tocar em codigo", () => {
  // Um provador colado na parede esquerda do corredor, abaixo do Show Room.
  const ampliada = [
    REFEITORIO,
    sala("showroom", "Show Room", 0, 250, 560, 330),
    sala("provador", "Provador", 0, 580, 560, 180),
    CORREDOR,
    ANACA,
    sala("store-entrance", "Entrada", 560, 760, 320, 140),
  ];
  const porta = portaDe(ampliada, "provador")!;
  assert.ok(porta, "o comodo novo ganhou porta sozinho");
  assert.equal(porta.x, 560, "na parede compartilhada com o corredor");
  assert.equal(porta.y, 670, "no meio da fachada do provador");
});
