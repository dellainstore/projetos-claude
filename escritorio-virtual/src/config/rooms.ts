/**
 * Configuracao visual dos comodos: silhueta do predio, paleta e mobiliario.
 *
 * Modulo PURO (sem Phaser, sem DOM): so descreve O QUE desenhar; a cena decide
 * COMO. Assim da para testar a planta sem subir um navegador.
 *
 * A PLANTA em si (posicao e tamanho de cada comodo) NAO esta aqui: vem do
 * banco (`SalaEscritorio`) pela API. Este arquivo cuida do acabamento, que e'
 * decisao de arte, nao de dado.
 *
 * Referencia de layout: `design/reference/escritorio-virtual-referencia.png`.
 */

import type { Sala } from "../types";

/** Slugs com papel fixo na encenacao. */
export const SLUG = {
  SHOWROOM: "showroom",
  ANACA: "anaca",
  CORREDOR: "corredor",
  REFEITORIO: "cafeteria",
  ENTRADA: "store-entrance",
} as const;

/** Espessura das paredes, em unidades de planta. */
export const PAREDE = 16;
/** Altura aparente das paredes do fundo (efeito de corte "casa de boneca"). */
export const ALTURA_PAREDE = 46;
/** Quanto o canto e' chanfrado na silhueta do predio. */
export const CHANFRO = 40;

// ── Paleta ─────────────────────────────────────────────────────────────────
// Tirada da imagem de referencia: carvao quase preto por fora, creme e bege
// nos pisos, dourado nos detalhes, rosa queimado na Anaca.

export const COR = {
  // Fora e estrutura.
  foraDoPredio: 0x232a36,
  fachada: 0x3a4152,
  fachadaTopo: 0x4a5265,
  parede: 0x272d3a,
  paredeTopo: 0x555d70,
  paredeInterna: 0xf5ece0,
  /** Contorno de TODO objeto. E' o que faz o desenho ser legivel. */
  contorno: 0x2f2822,

  // Pisos: cada ambiente com material proprio, nao tudo bege.
  pisoShowroom: 0xdcb98c,
  pisoShowroomListra: 0xcaa675,
  pisoAnaca: 0xdcb98c,
  pisoAnacaListra: 0xcaa675,
  pisoCorredor: 0xcfc2ad,
  pisoCorredorListra: 0xc0b19a,
  pisoRefeitorio: 0xe6e3da,
  pisoRefeitorioListra: 0xd2cec2,
  pisoEntrada: 0xd8cdbb,
  pisoEntradaListra: 0xc7bba6,

  // Tapetes com cor de verdade.
  tapeteShowroom: 0x9d5a66,
  tapeteShowroomBorda: 0x7d434e,
  tapeteAnaca: 0xb26a4e,
  tapeteAnacaBorda: 0x8d5039,
  tapeteCorredor: 0x8f6f8d,
  tapeteCorredorBorda: 0x6f5470,
  tapeteEntrada: 0x3b3a44,

  // Materiais.
  madeira: 0xa8743f,
  madeiraClara: 0xc8975d,
  madeiraEscura: 0x6d4726,
  movelPreto: 0x2f2b30,
  movelClaro: 0xf7f1e6,
  metalDourado: 0xd8a94e,
  aco: 0xb9c2cb,
  acoClaro: 0xd8dfe6,
  vidro: 0xa8cfdd,
  tela: 0x1d2430,
  telaLuz: 0x4fb0d8,

  // Verde das plantas e vasos.
  planta: 0x3f7d4a,
  plantaClara: 0x5aa85c,
  plantaEscura: 0x2d5c37,
  vaso: 0xb8724a,
  vasoEscuro: 0x8d5335,

  // Estofados.
  estofado: 0xc98a92,
  estofadoEscuro: 0xa2646d,

  // Acentos de marca.
  acentoAnaca: 0x9c5a46,
  acentoShowroom: 0x232021,

  // Roupas nas araras: paleta saturada, para a arara ser reconhecivel.
  roupas: [
    0xe8dccb, 0xc86b7a, 0x2f2b30, 0xf0e4d4,
    0xb2674e, 0x4a6b8a, 0xd9a05b, 0x7a4a63,
  ] as number[],

  texto: 0x33291f,
  textoPlaca: 0xf0d089,
  textoFraco: 0x8a8177,
  luzApagada: 0x141a28,
  alerta: 0xd2483c,
} as const;

/** Contorno padrao de objeto: escuro e fino, no estilo de jogo 2D. */
export const CONTORNO: { cor: number; largura: number; alpha: number } = {
  cor: 0x2f2822, largura: 2, alpha: 0.85,
};

/** Acabamento de cada comodo. Comodo desconhecido cai no padrao. */
export type PadraoDePiso = "tabua-horizontal" | "tabua-vertical" | "ladrilho";

export interface EstiloComodo {
  piso: number;
  /** Cor das tabuas/ladrilhos, sobre a cor do piso. */
  listra: number;
  padrao: PadraoDePiso;
  /** Cor da parede de fundo vista por dentro (a parede de acento). */
  fundo: number;
  /** Cor da placa de identificacao; `null` esconde a placa. */
  placa: number | null;
  fundoPlaca: number | null;
}

const PADRAO: EstiloComodo = {
  piso: COR.pisoShowroom,
  listra: COR.pisoShowroomListra,
  padrao: "tabua-horizontal",
  fundo: COR.paredeInterna,
  placa: COR.textoFraco,
  fundoPlaca: null,
};

const ESTILOS: Record<string, EstiloComodo> = {
  [SLUG.SHOWROOM]: {
    piso: COR.pisoShowroom, listra: COR.pisoShowroomListra,
    padrao: "tabua-horizontal", fundo: COR.acentoShowroom,
    placa: COR.textoPlaca, fundoPlaca: null,
  },
  [SLUG.ANACA]: {
    piso: COR.pisoAnaca, listra: COR.pisoAnacaListra,
    padrao: "tabua-horizontal", fundo: COR.acentoAnaca,
    placa: COR.textoPlaca, fundoPlaca: null,
  },
  [SLUG.CORREDOR]: {
    piso: COR.pisoCorredor, listra: COR.pisoCorredorListra,
    padrao: "tabua-vertical", fundo: COR.paredeInterna,
    placa: null, fundoPlaca: null,
  },
  [SLUG.REFEITORIO]: {
    piso: COR.pisoRefeitorio, listra: COR.pisoRefeitorioListra,
    padrao: "ladrilho", fundo: COR.paredeInterna,
    placa: COR.texto, fundoPlaca: null,
  },
  [SLUG.ENTRADA]: {
    piso: COR.pisoEntrada, listra: COR.pisoEntradaListra,
    padrao: "ladrilho", fundo: COR.paredeInterna,
    placa: null, fundoPlaca: null,
  },
};

export function estiloDe(slug: string): EstiloComodo {
  return ESTILOS[slug] ?? PADRAO;
}

// ── Mobiliario ─────────────────────────────────────────────────────────────

export type FormaMovel =
  | "caixa"        // movel com volume (balcao, mesa, geladeira)
  | "tapete"       // mancha no chao
  | "arara"        // barra com roupas penduradas
  | "prateleira"   // superficie rasa encostada na parede
  | "planta"
  | "espelho"
  | "manequim"
  | "monitor"
  | "pecas"
  | "luminaria"
  | "quadro";

export interface Movel {
  forma: FormaMovel;
  /** Posicao relativa ao comodo, de 0 a 1 (canto superior esquerdo do item). */
  x: number;
  y: number;
  /** Tamanho em unidades de planta. */
  largura: number;
  altura: number;
  cor?: number;
  corTopo?: number;
  /** Altura aparente do volume. 0 = rente ao chao. */
  volume?: number;
  /** Desenhado DEPOIS das personagens (ex.: frente do balcao). */
  naFrente?: boolean;
  /** Tapete redondo, como os da imagem de referencia. */
  redondo?: boolean;
  rotulo?: string;
}

/**
 * Mobiliario de um showroom. Show Room e Anaca compartilham a base e mudam a
 * cor de acento e do tapete, como na referencia (preto e dourado de um lado,
 * rosa queimado do outro).
 */
function showroom(tapete: number): Movel[] {
  return [
    // Tapetes redondos sob as areas de circulacao.
    { forma: "tapete", x: 0.05, y: 0.55, largura: 210, altura: 180, cor: tapete, redondo: true },
    { forma: "tapete", x: 0.46, y: 0.44, largura: 250, altura: 210, cor: tapete, redondo: true },

    // Araras: parede esquerda, fundo e parede direita.
    { forma: "arara", x: 0.02, y: 0.22, largura: 40, altura: 240 },
    { forma: "arara", x: 0.24, y: 0.14, largura: 200, altura: 40 },
    { forma: "arara", x: 0.89, y: 0.22, largura: 40, altura: 230 },

    // Prateleiras de calcados e bolsas, na parede de fundo.
    { forma: "prateleira", x: 0.02, y: 0.14, largura: 108, altura: 22, cor: COR.movelClaro, volume: 12 },
    { forma: "prateleira", x: 0.02, y: 0.24, largura: 108, altura: 22, cor: COR.movelClaro, volume: 12 },
    { forma: "prateleira", x: 0.76, y: 0.14, largura: 96, altura: 22, cor: COR.movelClaro, volume: 12 },

    { forma: "espelho", x: 0.42, y: 0.12, largura: 58, altura: 136 },
    { forma: "quadro", x: 0.70, y: 0.02, largura: 62, altura: 30 },
    { forma: "quadro", x: 0.82, y: 0.02, largura: 40, altura: 30 },

    // Mesa de pecas dobradas e banqueta.
    { forma: "caixa", x: 0.06, y: 0.68, largura: 168, altura: 96, cor: COR.movelClaro, corTopo: 0xfbf8f2, volume: 22 },
    { forma: "pecas", x: 0.09, y: 0.70, largura: 140, altura: 40 },
    { forma: "caixa", x: 0.40, y: 0.30, largura: 56, altura: 40, cor: 0xd5a8ab, corTopo: 0xe2babd, volume: 16 },

    // Balcao de atendimento: a frente cobre quem esta atras dele.
    { forma: "caixa", x: 0.47, y: 0.60, largura: 196, altura: 80, cor: COR.movelPreto, corTopo: COR.movelClaro, volume: 34, naFrente: true },
    { forma: "monitor", x: 0.52, y: 0.55, largura: 44, altura: 34 },

    { forma: "manequim", x: 0.86, y: 0.52, largura: 52, altura: 58 },
    { forma: "planta", x: 0.63, y: 0.28, largura: 54, altura: 54 },
    { forma: "planta", x: 0.04, y: 0.90, largura: 48, altura: 48 },
    { forma: "planta", x: 0.93, y: 0.86, largura: 44, altura: 44 },
    { forma: "luminaria", x: 0.30, y: 0.30, largura: 30, altura: 30 },
    { forma: "luminaria", x: 0.68, y: 0.70, largura: 30, altura: 30 },
  ];
}

const MOBILIARIO: Record<string, Movel[]> = {
  [SLUG.SHOWROOM]: showroom(COR.tapeteShowroom),
  [SLUG.ANACA]: showroom(COR.tapeteAnaca),

  [SLUG.REFEITORIO]: [
    // Bancada, pia e armarios encostados na parede de fundo (abaixo da placa).
    { forma: "prateleira", x: 0.20, y: 0.22, largura: 190, altura: 38, cor: COR.madeira, volume: 18 },
    { forma: "prateleira", x: 0.24, y: 0.14, largura: 118, altura: 16, cor: COR.movelClaro, volume: 8 },
    { forma: "caixa", x: 0.02, y: 0.20, largura: 56, altura: 88, cor: COR.aco, corTopo: 0xe4e8ea, volume: 46 },
    { forma: "caixa", x: 0.23, y: 0.24, largura: 32, altura: 30, cor: COR.movelPreto, corTopo: 0x46413c, volume: 24 },
    { forma: "caixa", x: 0.87, y: 0.24, largura: 30, altura: 38, cor: COR.movelPreto, corTopo: 0x46413c, volume: 26 },
    { forma: "quadro", x: 0.74, y: 0.02, largura: 52, altura: 26 },

    // Mesa central com quatro cadeiras.
    { forma: "tapete", x: 0.20, y: 0.50, largura: 210, altura: 118, cor: COR.tapeteCorredor, redondo: true },
    { forma: "caixa", x: 0.30, y: 0.56, largura: 132, altura: 66, cor: COR.madeira, corTopo: 0xc9a476, volume: 22 },
    { forma: "caixa", x: 0.20, y: 0.58, largura: 30, altura: 34, cor: 0xd5a8ab, corTopo: 0xe2babd, volume: 18 },
    { forma: "caixa", x: 0.76, y: 0.58, largura: 30, altura: 34, cor: 0xd5a8ab, corTopo: 0xe2babd, volume: 18 },
    { forma: "caixa", x: 0.36, y: 0.86, largura: 36, altura: 28, cor: 0xd5a8ab, corTopo: 0xe2babd, volume: 18 },
    { forma: "caixa", x: 0.58, y: 0.86, largura: 36, altura: 28, cor: 0xd5a8ab, corTopo: 0xe2babd, volume: 18 },
    { forma: "planta", x: 0.02, y: 0.66, largura: 44, altura: 44 },
    { forma: "luminaria", x: 0.34, y: 0.42, largura: 28, altura: 28 },
    { forma: "luminaria", x: 0.58, y: 0.42, largura: 28, altura: 28 },
  ],

  [SLUG.ENTRADA]: [
    { forma: "tapete", x: 0.26, y: 0.40, largura: 140, altura: 56, cor: COR.tapeteEntrada },
    { forma: "planta", x: 0.02, y: 0.18, largura: 48, altura: 48 },
    { forma: "planta", x: 0.84, y: 0.18, largura: 48, altura: 48 },
  ],

  [SLUG.CORREDOR]: [
    // Passadeira central, como na referencia.
    { forma: "tapete", x: 0.22, y: 0.08, largura: 156, altura: 400, cor: COR.tapeteCorredor },
    { forma: "planta", x: 0.01, y: 0.10, largura: 46, altura: 46 },
    { forma: "planta", x: 0.84, y: 0.10, largura: 46, altura: 46 },
    { forma: "planta", x: 0.01, y: 0.74, largura: 46, altura: 46 },
    { forma: "planta", x: 0.84, y: 0.74, largura: 46, altura: 46 },
    { forma: "luminaria", x: 0.44, y: 0.26, largura: 34, altura: 34 },
    { forma: "luminaria", x: 0.44, y: 0.58, largura: 34, altura: 34 },
  ],
};

export function mobiliarioDe(slug: string): Movel[] {
  return MOBILIARIO[slug] ?? MOBILIARIO[SLUG.SHOWROOM];
}

/** Converte a posicao relativa de um movel para coordenadas de planta. */
export function posicaoDoMovel(sala: Sala, movel: Movel): { x: number; y: number } {
  const util = {
    x: sala.pos_x + PAREDE,
    y: sala.pos_y + PAREDE,
    largura: Math.max(sala.largura - PAREDE * 2, 1),
    altura: Math.max(sala.altura - PAREDE * 2, 1),
  };
  return {
    x: util.x + util.largura * movel.x,
    y: util.y + util.altura * movel.y,
  };
}

// ── Postos de trabalho e assentos ──────────────────────────────────────────

/**
 * Onde as pessoas ficam dentro de cada comodo, em coordenadas relativas.
 *
 * E' uma lista de VAGAS, nao um lugar por pessoa: a primeira que estiver no
 * comodo ocupa a primeira vaga, a segunda a seguinte. Ninguem esta amarrado
 * por nome, que e' justamente o que o cadastro existe para evitar. Quando
 * houver mais gente que vaga, o restante se espalha (ver `vagaNaSala`).
 *
 * No showroom a primeira vaga e' atras do BALCAO (que e' desenhado na frente
 * da personagem, entao ela aparece por tras dele) e a segunda fica junto de
 * uma arara, como na imagem de referencia.
 */
const POSTOS: Record<string, Array<{ x: number; y: number }>> = {
  [SLUG.SHOWROOM]: [
    { x: 0.62, y: 0.60 },
    { x: 0.20, y: 0.44 },
    { x: 0.86, y: 0.46 },
  ],
  [SLUG.ANACA]: [
    { x: 0.52, y: 0.58 },
    { x: 0.20, y: 0.44 },
    { x: 0.86, y: 0.46 },
  ],
  [SLUG.REFEITORIO]: [
    { x: 0.30, y: 0.72 },
    { x: 0.56, y: 0.72 },
    { x: 0.78, y: 0.56 },
    { x: 0.14, y: 0.56 },
  ],
  [SLUG.ENTRADA]: [{ x: 0.5, y: 0.5 }],
  [SLUG.CORREDOR]: [{ x: 0.5, y: 0.5 }],
};

/** Vaga `indice` do comodo, em coordenadas de planta. `null` se acabaram. */
export function postoDoComodo(sala: Sala, indice: number): { x: number; y: number } | null {
  const vagas = POSTOS[sala.slug];
  if (!vagas || indice >= vagas.length) return null;
  const rel = vagas[indice];
  const util = {
    x: sala.pos_x + PAREDE,
    y: sala.pos_y + PAREDE,
    largura: Math.max(sala.largura - PAREDE * 2, 1),
    altura: Math.max(sala.altura - PAREDE * 2, 1),
  };
  return { x: util.x + util.largura * rel.x, y: util.y + util.altura * rel.y };
}

// ── Silhueta do predio ─────────────────────────────────────────────────────

export interface PontoPlano {
  x: number;
  y: number;
}

/**
 * Contorno externo do predio, com cantos chanfrados (o formato octogonal da
 * imagem de referencia). Derivado da UNIAO dos comodos, entao acompanha a
 * planta que vier do banco em vez de ser uma lista fixa de pontos.
 *
 * O algoritmo e' simples de proposito: percorre a borda da caixa de cada
 * "faixa" de comodos. Para plantas muito diferentes da atual ele degrada para
 * o retangulo externo, que continua correto, so menos bonito.
 */
export function silhueta(salas: Sala[], chanfro = CHANFRO): PontoPlano[] {
  if (salas.length === 0) return [];

  const topo = Math.min(...salas.map((s) => s.pos_y));
  const base = Math.max(...salas.map((s) => s.pos_y + s.altura));
  const esquerda = Math.min(...salas.map((s) => s.pos_x));
  const direita = Math.max(...salas.map((s) => s.pos_x + s.largura));

  // Faixas horizontais distintas: cada mudanca de "largura ocupada" vira um
  // degrau na silhueta.
  const cortes = new Set<number>([topo, base]);
  for (const s of salas) {
    cortes.add(s.pos_y);
    cortes.add(s.pos_y + s.altura);
  }
  const ys = [...cortes].sort((a, b) => a - b);

  const faixas: Array<{ y0: number; y1: number; x0: number; x1: number }> = [];
  for (let i = 0; i < ys.length - 1; i += 1) {
    const y0 = ys[i];
    const y1 = ys[i + 1];
    const meio = (y0 + y1) / 2;
    const naFaixa = salas.filter((s) => s.pos_y <= meio && s.pos_y + s.altura >= meio);
    if (naFaixa.length === 0) continue;
    const x0 = Math.min(...naFaixa.map((s) => s.pos_x));
    const x1 = Math.max(...naFaixa.map((s) => s.pos_x + s.largura));
    const anterior = faixas[faixas.length - 1];
    if (anterior && anterior.x0 === x0 && anterior.x1 === x1) {
      anterior.y1 = y1; // funde faixas iguais
    } else {
      faixas.push({ y0, y1, x0, x1 });
    }
  }

  if (faixas.length === 0) {
    return [
      { x: esquerda, y: topo }, { x: direita, y: topo },
      { x: direita, y: base }, { x: esquerda, y: base },
    ];
  }

  // Contorna no sentido horario: topo, lado direito descendo, base, lado
  // esquerdo subindo. Os cantos externos (primeira e ultima faixa) ganham
  // chanfro, que e' o que da o formato octogonal da referencia.
  const primeira = faixas[0];
  const ultima = faixas[faixas.length - 1];
  const chanfroDe = (f: { y0: number; y1: number; x0: number; x1: number }) =>
    Math.min(chanfro, (f.y1 - f.y0) / 2, (f.x1 - f.x0) / 2);
  const cTopo = chanfroDe(primeira);
  const cBase = chanfroDe(ultima);

  const pontos: PontoPlano[] = [{ x: primeira.x0 + cTopo, y: primeira.y0 }];
  pontos.push({ x: primeira.x1 - cTopo, y: primeira.y0 });

  faixas.forEach((f, i) => {
    pontos.push({ x: f.x1, y: i === 0 ? f.y0 + cTopo : f.y0 });
    pontos.push({ x: f.x1, y: i === faixas.length - 1 ? f.y1 - cBase : f.y1 });
  });

  pontos.push({ x: ultima.x1 - cBase, y: ultima.y1 });
  pontos.push({ x: ultima.x0 + cBase, y: ultima.y1 });

  for (let i = faixas.length - 1; i >= 0; i -= 1) {
    const f = faixas[i];
    pontos.push({ x: f.x0, y: i === faixas.length - 1 ? f.y1 - cBase : f.y1 });
    pontos.push({ x: f.x0, y: i === 0 ? f.y0 + cTopo : f.y0 });
  }

  // Remove pontos repetidos seguidos (degraus de faixas alinhadas).
  return pontos.filter((p, i) => {
    const anterior = pontos[(i - 1 + pontos.length) % pontos.length];
    return Math.abs(p.x - anterior.x) > 0.01 || Math.abs(p.y - anterior.y) > 0.01;
  });
}
