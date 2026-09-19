/**
 * Conversao entre coordenadas NORMALIZADAS (0..1, usadas em officeZones.ts e
 * officePaths.ts) e pixels de tela do jogo Phaser.
 *
 * Existe UM lugar so para essa conta. Nada mais no projeto multiplica x*width
 * na mao — isso e' o que evita coordenada magica espalhada por varios
 * arquivos, como pedido.
 *
 * A imagem de fundo e' exibida em modo "contain": mantém a proporção
 * original (pixel art nunca é esticada de forma desigual), centralizada
 * dentro do canvas do jogo.
 */

import type { NormalizedPoint, NormalizedRect } from "../config/officeZones";

export interface ImageFrame {
  /** Posição do canto superior-esquerdo da imagem dentro do canvas. */
  offsetX: number;
  offsetY: number;
  /** Escala aplicada à imagem original para caber no canvas (contain). */
  scale: number;
  /** Tamanho final da imagem desenhada, em pixels de tela. */
  displayWidth: number;
  displayHeight: number;
}

export function computeImageFrame(
  canvasWidth: number,
  canvasHeight: number,
  imageWidth: number,
  imageHeight: number,
): ImageFrame {
  const scale = Math.min(canvasWidth / imageWidth, canvasHeight / imageHeight);
  const displayWidth = imageWidth * scale;
  const displayHeight = imageHeight * scale;
  return {
    offsetX: (canvasWidth - displayWidth) / 2,
    offsetY: (canvasHeight - displayHeight) / 2,
    scale,
    displayWidth,
    displayHeight,
  };
}

export function pointToScreen(frame: ImageFrame, p: NormalizedPoint): { x: number; y: number } {
  return {
    x: frame.offsetX + p.x * frame.displayWidth,
    y: frame.offsetY + p.y * frame.displayHeight,
  };
}

export function rectToScreen(
  frame: ImageFrame, r: NormalizedRect,
): { x: number; y: number; width: number; height: number } {
  return {
    x: frame.offsetX + r.x * frame.displayWidth,
    y: frame.offsetY + r.y * frame.displayHeight,
    width: r.width * frame.displayWidth,
    height: r.height * frame.displayHeight,
  };
}
