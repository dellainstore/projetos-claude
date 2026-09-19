/**
 * Aparência procedural de cada personagem (paleta de cores).
 *
 * IMPORTANTE: nenhuma foto real da Tina ou da Sara foi recebida nesta
 * conversa (só a imagem do cenário limpo chegou de fato). Estas paletas são
 * ORIGINAIS/genéricas, escolhidas para serem visualmente distintas e
 * combinarem com a cor de cada ambiente (Show Room em tons de vinho/rosa,
 * Anacã em verde) — não são uma tentativa de reproduzir a aparência real de
 * ninguém. Quando as fotos ou o spritesheet oficial chegarem, só este
 * arquivo muda.
 */

import type { PixelPalette } from "../actors/EmployeeCharacter";

export const EMPLOYEE_PALETTES: Record<string, PixelPalette> = {
  tina: {
    pele: 0xe8b48c,
    cabelo: 0x3a2417,
    roupa: 0x8b3a4a,
    roupaEscura: 0x241f1a,
    sapato: 0x2b2420,
  },
  sara: {
    pele: 0xf0c9a0,
    cabelo: 0x8a4a2c,
    roupa: 0x2e4a6b,
    roupaEscura: 0xd8c7a6,
    sapato: 0x3a3128,
  },
  michelle: {
    // "morena genérica", claramente distinta das outras duas (pedido
    // explícito: sem foto disponível para a Michelle).
    pele: 0x9a6b45,
    cabelo: 0x1c1712,
    roupa: 0x3f7d4a,
    roupaEscura: 0x1c1712,
    sapato: 0x241f1a,
  },
};

export const DEFAULT_PALETTE: PixelPalette = {
  pele: 0xe0b590, cabelo: 0x4a3527, roupa: 0x6b6b6b, roupaEscura: 0x3a3a3a, sapato: 0x2a2a2a,
};

export function paletaDoSlug(slug: string): PixelPalette {
  return EMPLOYEE_PALETTES[slug] ?? DEFAULT_PALETTE;
}
