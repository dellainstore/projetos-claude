/** Testes da paleta: cor por slug, nunca por pessoa. */

import assert from "node:assert/strict";
import test from "node:test";

import {
  CENARIO,
  clarear,
  escurecer,
  hex,
  hslParaHex,
  paletaDe,
} from "../src/config/characters";

test("a mesma personagem sempre recebe a mesma paleta", () => {
  assert.deepEqual(paletaDe("tina"), paletaDe("tina"));
  assert.deepEqual(paletaDe("qualquer-uma"), paletaDe("qualquer-uma"));
});

test("personagens diferentes recebem cores diferentes", () => {
  const a = paletaDe("sara");
  const b = paletaDe("michelle");
  assert.notEqual(a.roupa, b.roupa);
});

test("personagem sem ajuste manual ainda ganha paleta completa", () => {
  const p = paletaDe("personagem-que-ninguem-configurou");
  for (const chave of ["pele", "cabelo", "roupa", "detalhe"] as const) {
    assert.equal(typeof p[chave], "number");
    assert.ok(p[chave] >= 0 && p[chave] <= 0xffffff, `${chave} fora da faixa`);
  }
});

test("slug vazio nao quebra", () => {
  const p = paletaDe("");
  assert.equal(typeof p.roupa, "number");
});

test("ajuste manual prevalece sobre o hash", () => {
  assert.equal(paletaDe("tina").roupa, 0x8b1e3f);
  assert.equal(paletaDe("sara").roupa, 0x1f4e79);
  assert.equal(paletaDe("michelle").roupa, 0x2e6b4f);
});

test("o detalhe e' uma versao mais clara da roupa", () => {
  const p = paletaDe("tina");
  assert.notEqual(p.detalhe, p.roupa);
  assert.ok(luminancia(p.detalhe) > luminancia(p.roupa));
});

test("clarear e escurecer ficam dentro da faixa valida", () => {
  for (const cor of [0x000000, 0x8b1e3f, 0xffffff]) {
    for (const f of [0, 0.25, 1]) {
      for (const fn of [clarear, escurecer]) {
        const r = fn(cor, f);
        assert.ok(r >= 0 && r <= 0xffffff, `${fn.name}(${cor}, ${f}) = ${r}`);
      }
    }
  }
  assert.equal(clarear(0x000000, 1), 0xffffff);
  assert.equal(escurecer(0xffffff, 1), 0x000000);
  assert.equal(clarear(0x336699, 0), 0x336699);
});

test("hslParaHex cobre os seis setores sem estourar", () => {
  for (let h = 0; h < 360; h += 15) {
    const cor = hslParaHex(h, 0.5, 0.5);
    assert.ok(cor >= 0 && cor <= 0xffffff, `matiz ${h} gerou ${cor}`);
  }
  assert.equal(hslParaHex(0, 0, 0), 0x000000);
  assert.equal(hslParaHex(0, 0, 1), 0xffffff);
});

test("hslParaHex aceita matiz fora de 0..360", () => {
  assert.equal(hslParaHex(360, 0.5, 0.5), hslParaHex(0, 0.5, 0.5));
  assert.equal(hslParaHex(-60, 0.5, 0.5), hslParaHex(300, 0.5, 0.5));
});

test("hex sai no formato que o Phaser espera", () => {
  assert.equal(hex(0x000000), "#000000");
  assert.equal(hex(0xf4f1ea), "#f4f1ea");
  assert.match(hex(CENARIO.texto), /^#[0-9a-f]{6}$/);
});

function luminancia(cor: number): number {
  const r = (cor >> 16) & 0xff;
  const g = (cor >> 8) & 0xff;
  const b = cor & 0xff;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
