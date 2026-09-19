/**
 * Cores do cenario e das personagens. Modulo PURO (sem Phaser, sem DOM).
 *
 * Nenhuma cor esta amarrada a uma pessoa: a chave e' o slug do personagem
 * (`PersonagemEscritorio.personagem`), e quem nao estiver na tabela recebe uma
 * paleta derivada do proprio slug por hash. Cadastrar uma personagem nova
 * funciona sem tocar em codigo; se depois quiser afinar a cor dela, basta
 * acrescentar uma linha aqui.
 */

export interface PaletaPersonagem {
  pele: number;
  cabelo: number;
  roupa: number;
  detalhe: number;
}

/** Tons de pele possiveis, escolhidos pelo hash quando nao ha ajuste manual. */
const PELES = [0xf1c9a5, 0xe0ac86, 0xc68863, 0x8d5524, 0xffdbb4];

/** Ajustes manuais. Chave = slug do personagem, nunca o nome da pessoa. */
const AJUSTES: Record<string, Partial<PaletaPersonagem>> = {
  tina: { roupa: 0x8b1e3f, cabelo: 0x2f2119 },
  sara: { roupa: 0x1f4e79, cabelo: 0x4a2c17 },
  michelle: { roupa: 0x2e6b4f, cabelo: 0x1a1a1a },
};

/** Cores da marca usadas no cenario (mesmas famílias do painel). */
export const CENARIO = {
  fundo: 0xf4f1ea,
  piso: 0xece6db,
  parede: 0xd9d0c1,
  paredeEscura: 0xb9ae9b,
  sala: 0xfdfbf7,
  salaBorda: 0xcfc5b4,
  movel: 0xd6c8b0,
  movelEscuro: 0xa9977c,
  texto: 0x3a332b,
  textoFraco: 0x8a8177,
  porta: 0x8a6f4e,
  luzApagada: 0x0b1020,
  alerta: 0xb91c1c,
  atencao: 0xb45309,
  ok: 0x15803d,
} as const;

function hash(texto: string): number {
  let h = 2166136261;
  for (let i = 0; i < texto.length; i += 1) {
    h ^= texto.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

/** HSL para inteiro 0xRRGGBB. h em graus (qualquer valor), s e l entre 0 e 1. */
export function hslParaHex(h: number, s: number, l: number): number {
  // Normaliza a matiz ANTES de qualquer conta. Sem isso, um h negativo faz
  // `(h / 60) % 2` ficar negativo em JS e `x` sair abaixo de zero, gerando um
  // componente fora de 0..255 (e uma cor levemente errada apos o & 0xff).
  const matiz = ((h % 360) + 360) % 360;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((matiz / 60) % 2) - 1));
  const m = l - c / 2;
  const setor = Math.floor(matiz / 60) % 6;
  const rgb: Array<[number, number, number]> = [
    [c, x, 0], [x, c, 0], [0, c, x], [0, x, c], [x, 0, c], [c, 0, x],
  ];
  const [r, g, b] = rgb[setor];
  const byte = (v: number) => Math.round((v + m) * 255) & 0xff;
  return (byte(r) << 16) | (byte(g) << 8) | byte(b);
}

export function paletaDe(slug: string): PaletaPersonagem {
  const h = hash(slug || "sem-nome");
  const matiz = h % 360;
  const base: PaletaPersonagem = {
    pele: PELES[h % PELES.length],
    cabelo: hslParaHex(matiz, 0.35, 0.18),
    roupa: hslParaHex((matiz + 140) % 360, 0.45, 0.38),
    detalhe: hslParaHex((matiz + 140) % 360, 0.5, 0.55),
  };
  const ajuste = AJUSTES[slug];
  if (!ajuste) return base;
  const roupa = ajuste.roupa ?? base.roupa;
  return {
    pele: ajuste.pele ?? base.pele,
    cabelo: ajuste.cabelo ?? base.cabelo,
    roupa,
    detalhe: ajuste.detalhe ?? clarear(roupa, 0.25),
  };
}

/** Clareia uma cor 0xRRGGBB por uma fracao (0 a 1). */
export function clarear(cor: number, fracao: number): number {
  const r = (cor >> 16) & 0xff;
  const g = (cor >> 8) & 0xff;
  const b = cor & 0xff;
  const mistura = (v: number) => Math.round(v + (255 - v) * fracao) & 0xff;
  return (mistura(r) << 16) | (mistura(g) << 8) | mistura(b);
}

/** Escurece uma cor 0xRRGGBB por uma fracao (0 a 1). */
export function escurecer(cor: number, fracao: number): number {
  const r = (cor >> 16) & 0xff;
  const g = (cor >> 8) & 0xff;
  const b = cor & 0xff;
  const mistura = (v: number) => Math.round(v * (1 - fracao)) & 0xff;
  return (mistura(r) << 16) | (mistura(g) << 8) | mistura(b);
}

export function hex(cor: number): string {
  return `#${cor.toString(16).padStart(6, "0")}`;
}
