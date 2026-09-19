/** Testes da conversao normalizado -> pixel de tela (modo "contain"). */
import assert from "node:assert/strict";
import test from "node:test";

import { computeImageFrame, pointToScreen, rectToScreen } from "../src/environment/ImageLayout";

test("imagem mais larga que o canvas fica limitada pela largura", () => {
  const frame = computeImageFrame(1000, 1000, 2000, 1000); // imagem 2:1
  assert.equal(frame.displayWidth, 1000);
  assert.equal(frame.displayHeight, 500);
  assert.equal(frame.offsetX, 0);
  assert.equal(frame.offsetY, 250, "centralizada verticalmente");
});

test("imagem mais alta que o canvas fica limitada pela altura", () => {
  const frame = computeImageFrame(1000, 1000, 500, 1000); // imagem 1:2
  assert.equal(frame.displayHeight, 1000);
  assert.equal(frame.displayWidth, 500);
  assert.equal(frame.offsetX, 250, "centralizada horizontalmente");
  assert.equal(frame.offsetY, 0);
});

test("ponto normalizado (0,0) cai no canto da imagem exibida", () => {
  const frame = computeImageFrame(800, 600, 400, 300); // encaixe exato, escala 2
  const p = pointToScreen(frame, { x: 0, y: 0 });
  assert.equal(p.x, frame.offsetX);
  assert.equal(p.y, frame.offsetY);
});

test("ponto normalizado (1,1) cai no canto oposto", () => {
  const frame = computeImageFrame(800, 600, 400, 300);
  const p = pointToScreen(frame, { x: 1, y: 1 });
  assert.equal(p.x, frame.offsetX + frame.displayWidth);
  assert.equal(p.y, frame.offsetY + frame.displayHeight);
});

test("retangulo normalizado escala junto com a imagem", () => {
  const frame = computeImageFrame(800, 600, 400, 300); // escala 2x
  const r = rectToScreen(frame, { x: 0.25, y: 0.25, width: 0.5, height: 0.5 });
  assert.equal(r.width, 400);
  assert.equal(r.height, 300);
});
