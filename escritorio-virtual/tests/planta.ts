/**
 * Planta usada pelos testes: a MESMA que a migration de dados cria
 * (`0002_salas_iniciais`), para os numeros baterem com o que vai para a tela.
 *
 * Trocar o layout no banco = trocar so este arquivo nos testes.
 */

import type { Sala } from "../src/types";

export function sala(
  slug: string, nome: string, pos_x: number, pos_y: number, largura: number, altura: number,
): Sala {
  return { slug, nome, ordem: 0, pos_x, pos_y, largura, altura };
}

export const SHOWROOM = sala("showroom", "Show Room", 0, 250, 560, 510);
export const ANACA = sala("anaca", "Anacã", 880, 250, 560, 510);
export const CORREDOR = sala("corredor", "Corredor", 560, 250, 320, 510);
export const REFEITORIO = sala("cafeteria", "Refeitório", 520, 0, 400, 250);
export const ENTRADA = sala("store-entrance", "Entrada", 560, 760, 320, 140);

export const PLANTA: Sala[] = [REFEITORIO, SHOWROOM, CORREDOR, ANACA, ENTRADA];
