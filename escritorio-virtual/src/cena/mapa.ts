/**
 * Geometria do cenario. Modulo PURO: nao importa Phaser, nao toca no DOM.
 *
 * Toda a planta vem da API (`salas`, com pos_x/pos_y/largura/altura vindos de
 * `SalaEscritorio`), entao acrescentar uma sala nova no banco muda o mapa sem
 * tocar em codigo. O corredor por onde as personagens andam tambem e'
 * DESCOBERTO a partir da planta, em vez de ser uma constante: se voce mover as
 * salas, o caminho acompanha.
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

/** Margem interna para a personagem nao encostar na parede. */
const PADDING = 18;
/** Faixa livre minima para valer como corredor. */
const CORREDOR_MINIMO = 8;
/** Espaco maximo entre personagens na mesma sala. */
const ESPACO_MAXIMO = 58;

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

/**
 * Y da faixa horizontal mais larga que NENHUMA sala ocupa: o corredor.
 *
 * `null` quando as salas cobrem tudo (planta sem corredor). Nesse caso quem
 * chama cai no deslocamento em linha reta.
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

export function centro(sala: Sala): Ponto {
  return { x: sala.pos_x + sala.largura / 2, y: sala.pos_y + sala.altura / 2 };
}

/**
 * Onde a i-esima de `total` personagens fica dentro da sala, sem sobrepor.
 * Elas ficam um pouco abaixo do meio, para o nome caber acima da cabeca.
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

/** Ponto da sala que da para o corredor (a "porta"). */
export function portaDaSala(sala: Sala, corredor: number | null): Ponto {
  const meioX = sala.pos_x + sala.largura / 2;
  if (corredor === null) return centro(sala);
  const topo = sala.pos_y;
  const base = sala.pos_y + sala.altura;
  return { x: meioX, y: Math.min(Math.max(corredor, topo), base) };
}

function mesmoPonto(a: Ponto, b: Ponto): boolean {
  return Math.abs(a.x - b.x) < 0.5 && Math.abs(a.y - b.y) < 0.5;
}

/**
 * Waypoints de `origem` (dentro de `salaOrigem`) ate `destino` (dentro de
 * `salaDestino`), saindo pela porta, andando pelo corredor e entrando pela
 * porta de destino.
 *
 * Dentro da mesma sala, ou sem corredor na planta, vai em linha reta.
 */
export function caminho(
  origem: Ponto,
  destino: Ponto,
  salaOrigem: Sala | null,
  salaDestino: Sala | null,
  corredor: number | null,
): Ponto[] {
  if (salaOrigem === null || salaDestino === null || corredor === null) {
    return [destino];
  }
  if (salaOrigem.slug === salaDestino.slug) return [destino];

  const portaSaida = portaDaSala(salaOrigem, corredor);
  const portaEntrada = portaDaSala(salaDestino, corredor);
  const bruto: Ponto[] = [
    { x: origem.x, y: portaSaida.y },
    { x: portaSaida.x, y: corredor },
    { x: portaEntrada.x, y: corredor },
    { x: portaEntrada.x, y: portaEntrada.y },
    destino,
  ];

  const limpo: Ponto[] = [];
  let anterior = origem;
  for (const p of bruto) {
    if (!mesmoPonto(p, anterior)) {
      limpo.push(p);
      anterior = p;
    }
  }
  return limpo.length > 0 ? limpo : [destino];
}

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
 * Agrupa as personagens por sala, na ordem em que a API devolveu, e diz a vaga
 * de cada uma. Quem esta sem sala (fora de cena) nao entra.
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
