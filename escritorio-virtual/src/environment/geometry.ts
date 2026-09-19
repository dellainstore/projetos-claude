/**
 * Geometria do cenario. Modulo PURO: nao importa Phaser, nao toca no DOM.
 *
 * Toda a planta vem da API (`salas`, com pos_x/pos_y/largura/altura vindos de
 * `SalaEscritorio`), entao acrescentar ou mover um comodo no banco muda o mapa
 * sem tocar em codigo.
 *
 * A planta e' INTEGRADA: os comodos dividem parede e um corredor (a sala de
 * slug `corredor`) liga tudo. As PORTAS nao sao configuradas em lugar nenhum:
 * sao deduzidas de onde cada comodo encosta no corredor. Assim a parede
 * desenhada e o caminho percorrido usam exatamente a mesma conta, e nunca
 * saem de sincronia.
 */

import type { Sala } from "../types";

export interface Ponto {
  x: number;
  y: number;
}

export interface Mundo {
  largura: number;
  altura: number;
}

/** Vao de passagem entre um comodo e o corredor. */
export interface Porta {
  slug: string;
  /** Centro do vao. */
  x: number;
  y: number;
  /** Largura do vao, ao longo da parede. */
  vao: number;
  /** true quando o vao corre no eixo X (parede horizontal). */
  horizontal: boolean;
}

/** Slug reservado: a sala que liga os comodos. */
export const SLUG_CORREDOR = "corredor";
/** Slug reservado: por onde as personagens entram e saem da loja. */
export const SLUG_ENTRADA = "store-entrance";
/** Slug reservado: para onde vai quem esta no almoco. */
export const SLUG_REFEITORIO = "cafeteria";

const PADDING = 18;
const CORREDOR_MINIMO = 8;
const ESPACO_MAXIMO = 58;
const VAO_MAXIMO = 64;
const VAO_MINIMO = 34;
/** Tolerancia para considerar duas paredes encostadas. */
const COLADO = 1.5;

export function limitesDoMundo(salas: Sala[]): Mundo {
  if (salas.length === 0) return { largura: 640, altura: 360 };
  let largura = 0;
  let altura = 0;
  for (const s of salas) {
    largura = Math.max(largura, s.pos_x + s.largura);
    altura = Math.max(altura, s.pos_y + s.altura);
  }
  return { largura, altura };
}

export function salaPorSlug(salas: Sala[], slug: string | null): Sala | null {
  if (!slug) return null;
  return salas.find((s) => s.slug === slug) ?? null;
}

export function corredorDe(salas: Sala[]): Sala | null {
  return salaPorSlug(salas, SLUG_CORREDOR);
}

export function centro(sala: Sala): Ponto {
  return { x: sala.pos_x + sala.largura / 2, y: sala.pos_y + sala.altura / 2 };
}

/**
 * Onde a i-esima de `total` personagens fica dentro do comodo, sem sobrepor.
 * Ficam um pouco abaixo do meio, para o nome caber acima da cabeca.
 */
export function vagaNaSala(sala: Sala, indice: number, total: number): Ponto {
  const util = Math.max(sala.largura - PADDING * 2, 1);
  const espaco = Math.min(ESPACO_MAXIMO, util / Math.max(total, 1));
  const deslocamento = (indice - (total - 1) / 2) * espaco;
  return {
    x: sala.pos_x + sala.largura / 2 + deslocamento,
    y: sala.pos_y + sala.altura * 0.62,
  };
}

// ── Portas ─────────────────────────────────────────────────────────────────

function sobreposicao(a1: number, a2: number, b1: number, b2: number): [number, number] | null {
  const inicio = Math.max(a1, b1);
  const fim = Math.min(a2, b2);
  return fim - inicio > VAO_MINIMO ? [inicio, fim] : null;
}

/** Porta entre `sala` e o `corredor`, se as duas encostarem. */
export function portaEntre(sala: Sala, corredor: Sala): Porta | null {
  if (sala.slug === corredor.slug) return null;

  const salaDir = sala.pos_x + sala.largura;
  const salaBase = sala.pos_y + sala.altura;
  const corrDir = corredor.pos_x + corredor.largura;
  const corrBase = corredor.pos_y + corredor.altura;

  // Parede horizontal: o comodo esta acima ou abaixo do corredor.
  const encostaAcima = Math.abs(salaBase - corredor.pos_y) <= COLADO;
  const encostaAbaixo = Math.abs(sala.pos_y - corrBase) <= COLADO;
  if (encostaAcima || encostaAbaixo) {
    const faixa = sobreposicao(sala.pos_x, salaDir, corredor.pos_x, corrDir);
    if (faixa) {
      const [ini, fim] = faixa;
      return {
        slug: sala.slug,
        x: (ini + fim) / 2,
        y: encostaAcima ? corredor.pos_y : corrBase,
        vao: Math.min(VAO_MAXIMO, Math.max(VAO_MINIMO, (fim - ini) * 0.4)),
        horizontal: true,
      };
    }
  }

  // Parede vertical: o comodo esta a esquerda ou a direita do corredor.
  const encostaEsquerda = Math.abs(salaDir - corredor.pos_x) <= COLADO;
  const encostaDireita = Math.abs(sala.pos_x - corrDir) <= COLADO;
  if (encostaEsquerda || encostaDireita) {
    const faixa = sobreposicao(sala.pos_y, salaBase, corredor.pos_y, corrBase);
    if (faixa) {
      const [ini, fim] = faixa;
      return {
        slug: sala.slug,
        x: encostaEsquerda ? corredor.pos_x : corrDir,
        y: (ini + fim) / 2,
        vao: Math.min(VAO_MAXIMO, Math.max(VAO_MINIMO, (fim - ini) * 0.4)),
        horizontal: false,
      };
    }
  }

  return null;
}

/** Todas as portas do corredor para os demais comodos. */
export function portas(salas: Sala[]): Porta[] {
  const corredor = corredorDe(salas);
  if (!corredor) return [];
  const lista: Porta[] = [];
  for (const sala of salas) {
    const porta = portaEntre(sala, corredor);
    if (porta) lista.push(porta);
  }
  return lista;
}

export function portaDe(salas: Sala[], slug: string): Porta | null {
  const corredor = corredorDe(salas);
  const sala = salaPorSlug(salas, slug);
  if (!corredor || !sala) return null;
  return portaEntre(sala, corredor);
}

/** Linha central do corredor: as personagens andam por ela. */
export function eixoDoCorredor(corredor: Sala): { horizontal: boolean; centro: number } {
  const horizontal = corredor.largura >= corredor.altura;
  return {
    horizontal,
    centro: horizontal
      ? corredor.pos_y + corredor.altura / 2
      : corredor.pos_x + corredor.largura / 2,
  };
}

// O ROTEAMENTO mora em `config/paths.ts` (grafo de waypoints nomeados).
// Aqui ficam so as primitivas de geometria, que ele usa.

/** Comprimento total de um caminho, para calcular a duracao da caminhada. */
export function distancia(origem: Ponto, pontos: Ponto[]): number {
  let total = 0;
  let anterior = origem;
  for (const p of pontos) {
    total += Math.hypot(p.x - anterior.x, p.y - anterior.y);
    anterior = p;
  }
  return total;
}

/**
 * Agrupa as personagens por comodo, na ordem em que a API devolveu, e diz a
 * vaga de cada uma. Quem esta sem sala (fora de cena) nao entra.
 */
export function vagasPorPersonagem(
  salas: Sala[],
  ocupacao: Array<{ id: number; sala: string | null }>,
): Map<number, Ponto> {
  const porSlug = new Map(salas.map((s) => [s.slug, s]));
  const agrupado = new Map<string, number[]>();
  for (const o of ocupacao) {
    if (!o.sala || !porSlug.has(o.sala)) continue;
    const lista = agrupado.get(o.sala) ?? [];
    lista.push(o.id);
    agrupado.set(o.sala, lista);
  }

  const vagas = new Map<number, Ponto>();
  for (const [slug, ids] of agrupado) {
    const sala = porSlug.get(slug)!;
    ids.forEach((id, i) => vagas.set(id, vagaNaSala(sala, i, ids.length)));
  }
  return vagas;
}

/**
 * Quais comodos estao acesos.
 *
 * Luz por comodo, nao um apagao geral: com a loja aberta, acende onde tem
 * gente, mais as areas de circulacao (corredor e entrada). Com a loja
 * fechada, tudo apagado.
 */
export function comodosAcesos(
  salas: Sala[],
  lojaAberta: boolean,
  ocupacao: Array<{ sala: string | null }>,
): Set<string> {
  const acesos = new Set<string>();
  if (!lojaAberta) return acesos;

  for (const o of ocupacao) {
    if (o.sala) acesos.add(o.sala);
  }
  // Circulacao fica acesa enquanto a loja estiver aberta, mesmo vazia: e' por
  // onde as pessoas passam e por onde os clientes entram.
  for (const slug of [SLUG_CORREDOR, SLUG_ENTRADA]) {
    if (salas.some((s) => s.slug === slug)) acesos.add(slug);
  }
  return acesos;
}

// ── Fallback para plantas sem corredor ─────────────────────────────────────

/**
 * Y da faixa horizontal mais larga que NENHUMA sala ocupa.
 *
 * So e' usado em planta SEM a sala `corredor` (compatibilidade). `null`
 * quando as salas cobrem tudo.
 */
export function corredorY(salas: Sala[]): number | null {
  if (salas.length === 0) return null;
  const { altura } = limitesDoMundo(salas);
  const ocupado = new Array<boolean>(altura + 1).fill(false);
  for (const s of salas) {
    const fim = Math.min(s.pos_y + s.altura, altura);
    for (let y = Math.max(s.pos_y, 0); y <= fim; y += 1) ocupado[y] = true;
  }

  let melhorInicio = -1;
  let melhorTamanho = 0;
  let inicio = -1;
  for (let y = 0; y <= altura; y += 1) {
    if (!ocupado[y]) {
      if (inicio === -1) inicio = y;
      const tamanho = y - inicio + 1;
      if (tamanho > melhorTamanho) {
        melhorTamanho = tamanho;
        melhorInicio = inicio;
      }
    } else {
      inicio = -1;
    }
  }

  if (melhorTamanho < CORREDOR_MINIMO) return null;
  return melhorInicio + melhorTamanho / 2;
}
