/**
 * Rotas de caminhada sobre a imagem de fundo, em coordenadas NORMALIZADAS.
 *
 * Independente da geometria que vem do backend (`SalaEscritorio`, em
 * unidades de banco): aqui as rotas descrevem POSIÇÕES NA ARTE, calibradas
 * visualmente sobre a imagem aprovada. O backend continua sendo a fonte da
 * VERDADE (em que sala a pessoa está); este arquivo só diz por onde a
 * personagem anda na tela para chegar lá, sem atravessar parede, balcão ou
 * arara.
 *
 * Pontos nomeados (mesma nomenclatura do plano):
 *   entrance_outside, entrance_inside, hall_bottom, hall_center, hall_top,
 *   showroom_door, anaca_door, cafeteria_door.
 */

import type { NormalizedPoint, OfficeRoomId } from "./officeZones";

// Calibrados sobre a arte oficial (1536×1024px) — ver nota em officeZones.ts.
export const OFFICE_POINTS: Record<string, NormalizedPoint> = {
  entrance_outside: { x: 0.50, y: 1.04 },
  entrance_inside: { x: 0.50, y: 0.88 },
  hall_bottom: { x: 0.50, y: 0.74 },
  hall_center: { x: 0.50, y: 0.55 },
  hall_top: { x: 0.50, y: 0.30 },
  showroom_door: { x: 0.425, y: 0.55 },
  anaca_door: { x: 0.575, y: 0.55 },
  cafeteria_door: { x: 0.50, y: 0.265 },
};

/** Grafo de adjacência entre os pontos acima (BFS simples resolve a rota). */
const GRAPH: Record<string, string[]> = {
  entrance_outside: ["entrance_inside"],
  // (entrance_outside também é usado como âncora fora do prédio)
  entrance_inside: ["entrance_outside", "hall_bottom"],
  hall_bottom: ["entrance_inside", "hall_center"],
  hall_center: ["hall_bottom", "hall_top", "showroom_door", "anaca_door"],
  hall_top: ["hall_center", "cafeteria_door"],
  showroom_door: ["hall_center"],
  anaca_door: ["hall_center"],
  cafeteria_door: ["hall_top"],
};

/** Porta de entrada no corredor para cada ambiente. */
const DOOR_BY_ROOM: Partial<Record<OfficeRoomId, string>> = {
  showroom: "showroom_door",
  anaca: "anaca_door",
  cafeteria: "cafeteria_door",
  "store-entrance": "entrance_inside",
};

function bfs(from: string, to: string): string[] {
  if (from === to) return [from];
  const visited = new Set<string>([from]);
  const queue: string[][] = [[from]];
  while (queue.length > 0) {
    const path = queue.shift()!;
    const last = path[path.length - 1];
    for (const next of GRAPH[last] ?? []) {
      if (visited.has(next)) continue;
      const newPath = [...path, next];
      if (next === to) return newPath;
      visited.add(next);
      queue.push(newPath);
    }
  }
  return [from, to];
}

/**
 * Waypoints (em coordenadas normalizadas) de `fromPoint` (dentro de
 * `fromRoom`, ou `null` se for a rua) até `toPoint` (dentro de `toRoom`).
 *
 * Sempre sai pela porta do ambiente de origem, anda pelo corredor e entra
 * pela porta do ambiente de destino — nunca corta caminho por cima de móvel.
 */
export function buildWalkPath(
  fromRoom: OfficeRoomId | null,
  fromPoint: NormalizedPoint,
  toRoom: OfficeRoomId | null,
  toPoint: NormalizedPoint,
): NormalizedPoint[] {
  // null = do lado de fora (rua), antes de entrar ou depois de sair.
  const fromDoor = fromRoom ? DOOR_BY_ROOM[fromRoom] : "entrance_outside";
  const toDoor = toRoom ? DOOR_BY_ROOM[toRoom] : "entrance_outside";

  if (fromRoom === toRoom || !fromDoor || !toDoor) {
    return [toPoint];
  }

  const doorPath = bfs(fromDoor, toDoor);
  const pts: NormalizedPoint[] = [];
  for (const key of doorPath) pts.push(OFFICE_POINTS[key]);
  pts.push(toPoint);

  // Remove pontos consecutivos praticamente iguais, e o primeiro ponto se
  // ele coincidir com a posição atual (fromPoint) — evita um "passo" de
  // comprimento zero no início da caminhada.
  return pts.filter((p, i) => {
    const anterior = i === 0 ? fromPoint : pts[i - 1];
    return Math.abs(p.x - anterior.x) > 0.001 || Math.abs(p.y - anterior.y) > 0.001;
  });
}

/** Rotas nomeadas de alto nível, prontas (satisfaz o exemplo pedido). */
export const OFFICE_PATHS = {
  entranceToShowroom: buildWalkPath("store-entrance", OFFICE_POINTS.entrance_inside, "showroom", OFFICE_POINTS.showroom_door),
  entranceToAnaca: buildWalkPath("store-entrance", OFFICE_POINTS.entrance_inside, "anaca", OFFICE_POINTS.anaca_door),
  showroomToCafeteria: buildWalkPath("showroom", OFFICE_POINTS.showroom_door, "cafeteria", OFFICE_POINTS.cafeteria_door),
  anacaToCafeteria: buildWalkPath("anaca", OFFICE_POINTS.anaca_door, "cafeteria", OFFICE_POINTS.cafeteria_door),
  showroomToExit: buildWalkPath("showroom", OFFICE_POINTS.showroom_door, null, OFFICE_POINTS.entrance_outside),
  anacaToExit: buildWalkPath("anaca", OFFICE_POINTS.anaca_door, null, OFFICE_POINTS.entrance_outside),
} as const;
