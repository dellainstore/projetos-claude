/**
 * Zonas visuais sobre a imagem de fundo do escritorio.
 *
 * TUDO em coordenadas NORMALIZADAS (0..1, relativas a largura/altura da
 * imagem de fundo real). Nao ha pixel magico espalhado pelo codigo: a
 * conversao para pixels de tela acontece em UM lugar so
 * (`environment/ImageLayout.ts::paraTela`).
 *
 * Estas coordenadas foram estimadas visualmente a partir da imagem de
 * referencia aprovada (planta: Refeitorio no topo, Show Room a esquerda,
 * Anaca a direita, corredor central, entrada embaixo). Elas SAO uma
 * aproximacao inicial — ajuste fino aqui mesmo, sem tocar em nenhuma outra
 * parte do codigo, usando o overlay de depuracao (`?debugZonas=1` na URL)
 * que desenha os retangulos por cima da arte para calibrar visualmente.
 *
 * O `room` de cada zona usa os MESMOS slugs que ja vem da API
 * (`SalaEscritorio.slug`): showroom, anaca, cafeteria, store-entrance,
 * corredor. Isso e' o que liga a zona visual ao estado real do ponto sem
 * tabela de tradução no meio.
 */

export type OfficeRoomId =
  | "store-entrance"
  | "corredor"
  | "showroom"
  | "anaca"
  | "cafeteria";

export interface NormalizedRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface NormalizedPoint {
  x: number;
  y: number;
}

export interface OfficeZone {
  id: string;
  room: OfficeRoomId;
  /** Retangulo do AMBIENTE inteiro (usado para o overlay de luz). */
  rect: NormalizedRect;
  /** Cor do overlay de luz quando o ambiente esta ocupado (0xRRGGBB). */
  lightColor: number;
}

/** Um objeto clicavel/hover dentro de um ambiente (móvel ou equipamento). */
export interface InteractiveObject {
  id: string;
  room: OfficeRoomId;
  label: string;
  kind: "computador" | "arara" | "cafeteira" | "geladeira" | "mesa";
  point: NormalizedPoint;
  /** Raio de toque/clique, em fração da largura da imagem. */
  radius: number;
}

// Coordenadas calibradas visualmente sobre a arte OFICIAL aprovada
// (`della_sistemas/static/escritorio/office-bg.png`, 1536×1024px). Se a arte
// for substituída por uma versão com proporção/planta diferente, recalibrar
// só aqui — ligue `?debugZonas=1` na URL para ver as zonas e os pontos de
// rota desenhados por cima da imagem enquanto ajusta.
export const OFFICE_ZONES: OfficeZone[] = [
  {
    id: "zone-cafeteria",
    room: "cafeteria",
    rect: { x: 0.255, y: 0.015, width: 0.49, height: 0.25 },
    lightColor: 0xffd9a0,
  },
  {
    id: "zone-showroom",
    room: "showroom",
    rect: { x: 0.015, y: 0.265, width: 0.41, height: 0.535 },
    lightColor: 0xff9fc7,
  },
  {
    id: "zone-corredor",
    room: "corredor",
    rect: { x: 0.425, y: 0.265, width: 0.15, height: 0.535 },
    lightColor: 0xf3e6c8,
  },
  {
    id: "zone-anaca",
    room: "anaca",
    rect: { x: 0.575, y: 0.265, width: 0.41, height: 0.535 },
    lightColor: 0x8fd6a8,
  },
  {
    id: "zone-entrance",
    room: "store-entrance",
    rect: { x: 0.40, y: 0.80, width: 0.20, height: 0.165 },
    lightColor: 0xf3e6c8,
  },
];

/** Posição padrão de trabalho de cada colaboradora dentro do seu ambiente. */
export const WORK_SPOTS: Record<string, NormalizedPoint> = {
  // slug do personagem -> ponto de trabalho.
  // Tina: perto da arara de roupas, organizando (lado esquerdo do Show Room).
  tina: { x: 0.145, y: 0.44 },
  // Sara: no balcão/computador do Show Room.
  sara: { x: 0.20, y: 0.575 },
  // Michelle: no balcão/computador da Anacã.
  michelle: { x: 0.755, y: 0.47 },
};

/** Assentos do refeitório (ao redor da mesa), ocupados por ordem de chegada. */
export const CAFETERIA_SEATS: NormalizedPoint[] = [
  { x: 0.455, y: 0.175 },
  { x: 0.545, y: 0.175 },
  { x: 0.475, y: 0.225 },
  { x: 0.525, y: 0.225 },
];

/** Objetos interativos exibidos como pontos clicáveis sobre a arte. */
export const INTERACTIVE_OBJECTS: InteractiveObject[] = [
  { id: "obj-computador-sara", room: "showroom", label: "Computador", kind: "computador", point: { x: 0.20, y: 0.575 }, radius: 0.014 },
  { id: "obj-arara-showroom", room: "showroom", label: "Arara de roupas", kind: "arara", point: { x: 0.14, y: 0.395 }, radius: 0.016 },
  { id: "obj-computador-anaca", room: "anaca", label: "Computador", kind: "computador", point: { x: 0.755, y: 0.47 }, radius: 0.014 },
  { id: "obj-arara-anaca", room: "anaca", label: "Arara de roupas", kind: "arara", point: { x: 0.925, y: 0.68 }, radius: 0.016 },
  { id: "obj-provador-anaca", room: "anaca", label: "Provador", kind: "arara", point: { x: 0.875, y: 0.45 }, radius: 0.02 },
  { id: "obj-cafeteira", room: "cafeteria", label: "Cafeteira", kind: "cafeteira", point: { x: 0.545, y: 0.095 }, radius: 0.014 },
  { id: "obj-geladeira", room: "cafeteria", label: "Geladeira", kind: "geladeira", point: { x: 0.365, y: 0.10 }, radius: 0.018 },
  { id: "obj-mesa-refeitorio", room: "cafeteria", label: "Mesa do refeitório", kind: "mesa", point: { x: 0.50, y: 0.19 }, radius: 0.03 },
];

export function zonaDaSala(room: OfficeRoomId): OfficeZone | undefined {
  return OFFICE_ZONES.find((z) => z.room === room);
}
