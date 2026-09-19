/**
 * Grafo de rotas do escritorio: pontos de navegacao nomeados e o caminho
 * entre eles.
 *
 * Modulo PURO (sem Phaser, sem DOM). Nenhuma coordenada magica: todos os nos
 * sao DERIVADOS da planta que veio do banco, entao mover um comodo move as
 * portas, as estacoes do corredor e os trajetos junto.
 *
 * Nos, com a nomenclatura combinada:
 *
 *     entrance_outside   fora da loja, depois da porta de rua
 *     entrance_inside    hall de entrada
 *     hall_bottom        corredor, na altura da porta da entrada
 *     hall_center        corredor, na altura das portas dos showrooms
 *     hall_top           corredor, na altura da porta do refeitorio
 *     showroom_door      porta do Show Room
 *     anaca_door         porta da Anaca
 *     cafeteria_door     porta do refeitorio
 *     exit_point         igual a entrance_outside
 *
 * As POSICOES DE TRABALHO e os ASSENTOS do refeitorio nao sao nos fixos de
 * propósito: sao vagas calculadas dentro do comodo (ver `vagaNaSala`). Amarrar
 * "a cadeira da Tina" no codigo seria fixar pessoa no cenario, justamente o
 * que o cadastro existe para evitar.
 */

import type { Sala } from "../types";
import {
  corredorDe,
  eixoDoCorredor,
  portaEntre,
  vagaNaSala,
  type Ponto,
  type Porta,
} from "../environment/geometry";
import { SLUG } from "./rooms";

export const NO = {
  ENTRADA_FORA: "entrance_outside",
  ENTRADA_DENTRO: "entrance_inside",
  HALL_BAIXO: "hall_bottom",
  HALL_CENTRO: "hall_center",
  HALL_TOPO: "hall_top",
  SAIDA: "exit_point",
} as const;

/** Nome do no da porta de um comodo. */
export function noDaPorta(slug: string): string {
  if (slug === SLUG.REFEITORIO) return "cafeteria_door";
  return `${slug}_door`;
}

/** Nome da estacao do corredor em frente a porta de um comodo. */
function noDaEstacao(slug: string): string {
  return `${slug}_hall`;
}

export interface Grafo {
  pontos: Map<string, Ponto>;
  vizinhos: Map<string, Set<string>>;
  /** slug do comodo -> no da porta dele. */
  portaPorSala: Map<string, string>;
  /** slug do comodo -> estacao no corredor. */
  estacaoPorSala: Map<string, string>;
  /** Apelidos combinados (hall_center, etc.) -> no real. */
  apelidos: Map<string, string>;
}

const GRAFO_VAZIO: Grafo = {
  pontos: new Map(),
  vizinhos: new Map(),
  portaPorSala: new Map(),
  estacaoPorSala: new Map(),
  apelidos: new Map(),
};

function ligar(g: Grafo, a: string, b: string): void {
  if (!g.vizinhos.has(a)) g.vizinhos.set(a, new Set());
  if (!g.vizinhos.has(b)) g.vizinhos.set(b, new Set());
  g.vizinhos.get(a)!.add(b);
  g.vizinhos.get(b)!.add(a);
}

function pontoNoCorredor(porta: Porta, corredor: Sala): Ponto {
  const eixo = eixoDoCorredor(corredor);
  return eixo.horizontal ? { x: porta.x, y: eixo.centro } : { x: eixo.centro, y: porta.y };
}

/** Quanto a personagem anda para fora do predio antes de sumir. */
const FORA_DO_PREDIO = 110;

export function construirGrafo(salas: Sala[]): Grafo {
  const corredor = corredorDe(salas);
  if (!corredor) return GRAFO_VAZIO;

  const g: Grafo = {
    pontos: new Map(),
    vizinhos: new Map(),
    portaPorSala: new Map(),
    estacaoPorSala: new Map(),
    apelidos: new Map(),
  };

  const eixo = eixoDoCorredor(corredor);
  const estacoes: Array<{ no: string; coordenada: number }> = [];

  for (const sala of salas) {
    if (sala.slug === corredor.slug) continue;
    const porta = portaEntre(sala, corredor);
    if (!porta) continue;

    const noPorta = noDaPorta(sala.slug);
    const noEstacao = noDaEstacao(sala.slug);
    const pontoEstacao = pontoNoCorredor(porta, corredor);

    g.pontos.set(noPorta, { x: porta.x, y: porta.y });
    g.pontos.set(noEstacao, pontoEstacao);
    g.portaPorSala.set(sala.slug, noPorta);
    g.estacaoPorSala.set(sala.slug, noEstacao);
    ligar(g, noPorta, noEstacao);

    estacoes.push({
      no: noEstacao,
      coordenada: eixo.horizontal ? pontoEstacao.x : pontoEstacao.y,
    });
  }

  // O corredor e' uma linha: liga as estacoes na ordem em que aparecem nele.
  estacoes.sort((a, b) => a.coordenada - b.coordenada);
  for (let i = 0; i < estacoes.length - 1; i += 1) {
    ligar(g, estacoes[i].no, estacoes[i + 1].no);
  }

  // Entrada: hall interno e o ponto de rua, do lado de fora da porta.
  const entrada = salas.find((s) => s.slug === SLUG.ENTRADA);
  if (entrada) {
    const noPortaEntrada = g.portaPorSala.get(SLUG.ENTRADA);
    const dentro = {
      x: entrada.pos_x + entrada.largura / 2,
      y: entrada.pos_y + entrada.altura * 0.55,
    };
    const fora = ladoDeFora(entrada, salas);
    g.pontos.set(NO.ENTRADA_DENTRO, dentro);
    g.pontos.set(NO.ENTRADA_FORA, fora);
    g.pontos.set(NO.SAIDA, fora);
    g.apelidos.set(NO.SAIDA, NO.ENTRADA_FORA);
    ligar(g, NO.ENTRADA_FORA, NO.ENTRADA_DENTRO);
    if (noPortaEntrada) ligar(g, NO.ENTRADA_DENTRO, noPortaEntrada);
  }

  // Apelidos combinados, para o codigo e os testes falarem a mesma lingua.
  const apelido = (nome: string, slug: string) => {
    const alvo = g.estacaoPorSala.get(slug);
    if (alvo) g.apelidos.set(nome, alvo);
  };
  apelido(NO.HALL_BAIXO, SLUG.ENTRADA);
  apelido(NO.HALL_CENTRO, SLUG.SHOWROOM);
  apelido(NO.HALL_TOPO, SLUG.REFEITORIO);

  return g;
}

/** Ponto de rua: logo depois da porta externa da entrada. */
function ladoDeFora(entrada: Sala, salas: Sala[]): Ponto {
  const base = Math.max(...salas.map((s) => s.pos_y + s.altura));
  const direita = Math.max(...salas.map((s) => s.pos_x + s.largura));
  const esquerda = Math.min(...salas.map((s) => s.pos_x));
  const meioX = entrada.pos_x + entrada.largura / 2;
  const meioY = entrada.pos_y + entrada.altura / 2;

  if (Math.abs(entrada.pos_y + entrada.altura - base) <= 1.5) {
    return { x: meioX, y: base + FORA_DO_PREDIO };
  }
  if (Math.abs(entrada.pos_x + entrada.largura - direita) <= 1.5) {
    return { x: direita + FORA_DO_PREDIO, y: meioY };
  }
  if (Math.abs(entrada.pos_x - esquerda) <= 1.5) {
    return { x: esquerda - FORA_DO_PREDIO, y: meioY };
  }
  return { x: meioX, y: meioY };
}

export function ponto(grafo: Grafo, no: string): Ponto | null {
  const alvo = grafo.apelidos.get(no) ?? no;
  return grafo.pontos.get(alvo) ?? null;
}

/**
 * Menor sequencia de nos entre dois pontos do grafo (busca em largura).
 *
 * Com uma planta em estrela como esta o caminho e' sempre curto; a busca
 * existe para a planta poder crescer (um segundo corredor, um deposito) sem
 * ninguem reescrever rota na mao.
 */
export function rota(grafo: Grafo, de: string, para: string): string[] {
  const origem = grafo.apelidos.get(de) ?? de;
  const destino = grafo.apelidos.get(para) ?? para;
  if (origem === destino) return [origem];
  if (!grafo.pontos.has(origem) || !grafo.pontos.has(destino)) return [];

  const anterior = new Map<string, string | null>([[origem, null]]);
  const fila = [origem];
  while (fila.length > 0) {
    const atual = fila.shift()!;
    if (atual === destino) break;
    for (const vizinho of grafo.vizinhos.get(atual) ?? []) {
      if (anterior.has(vizinho)) continue;
      anterior.set(vizinho, atual);
      fila.push(vizinho);
    }
  }
  if (!anterior.has(destino)) return [];

  const caminhoInverso: string[] = [];
  let cursor: string | null = destino;
  while (cursor !== null) {
    caminhoInverso.push(cursor);
    cursor = anterior.get(cursor) ?? null;
  }
  return caminhoInverso.reverse();
}

// ── Do grafo para o trajeto em pixels ──────────────────────────────────────

function mesmoPonto(a: Ponto, b: Ponto): boolean {
  return Math.abs(a.x - b.x) < 0.5 && Math.abs(a.y - b.y) < 0.5;
}

/**
 * Insere um "cotovelo" entre dois pontos para o trecho nunca sair na
 * diagonal: a personagem anda em L, como quem respeita parede e movel.
 *
 * `preferirX` diz qual eixo percorrer primeiro.
 */
function cotovelo(de: Ponto, para: Ponto, preferirX: boolean): Ponto[] {
  if (Math.abs(de.x - para.x) < 0.5 || Math.abs(de.y - para.y) < 0.5) return [para];
  return preferirX
    ? [{ x: para.x, y: de.y }, para]
    : [{ x: de.x, y: para.y }, para];
}

export interface TrajetoOpcoes {
  salas: Sala[];
  grafo: Grafo;
  origem: Ponto;
  salaOrigem: string | null;
  destino: Ponto;
  salaDestino: string | null;
}

/**
 * Trajeto completo, em pontos, de onde a personagem esta ate onde deve ficar.
 *
 * Dentro do mesmo comodo vai em L. Entre comodos, sai pela porta, percorre o
 * corredor pelo grafo e entra pela porta de destino. Todo trecho e' horizontal
 * ou vertical: nada de cortar caminho por cima de balcao.
 */
export function trajeto(op: TrajetoOpcoes): Ponto[] {
  const { grafo, origem, destino, salaOrigem, salaDestino } = op;

  if (salaOrigem === null || salaDestino === null || grafo.pontos.size === 0) {
    return [destino];
  }
  if (salaOrigem === salaDestino) {
    return cotovelo(origem, destino, true);
  }

  const noOrigem = grafo.portaPorSala.get(salaOrigem)
    ?? grafo.estacaoPorSala.get(salaOrigem)
    ?? noDaEstacao(salaOrigem);
  const noDestino = grafo.portaPorSala.get(salaDestino)
    ?? grafo.estacaoPorSala.get(salaDestino)
    ?? noDaEstacao(salaDestino);

  const nos = rota(grafo, noOrigem, noDestino);
  if (nos.length === 0) return cotovelo(origem, destino, true);

  const bruto: Ponto[] = [];
  let anterior = origem;
  for (const no of nos) {
    const p = ponto(grafo, no);
    if (!p) continue;
    // Do ponto anterior ate o no: em L, comecando pelo eixo em que o no ja
    // esta mais alinhado (evita rodear o comodo).
    const preferirX = Math.abs(p.y - anterior.y) < Math.abs(p.x - anterior.x);
    for (const q of cotovelo(anterior, p, preferirX)) bruto.push(q);
    anterior = p;
  }
  for (const q of cotovelo(anterior, destino, false)) bruto.push(q);

  const limpo: Ponto[] = [];
  let ultimo = origem;
  for (const p of bruto) {
    if (!mesmoPonto(p, ultimo)) {
      limpo.push(p);
      ultimo = p;
    }
  }
  return limpo.length > 0 ? limpo : [destino];
}

/**
 * Assento de quem esta no refeitorio. E' a mesma repartição de vagas dos
 * outros comodos, so deslocada para a altura da mesa.
 */
export function assentoNoRefeitorio(sala: Sala, indice: number, total: number): Ponto {
  const vaga = vagaNaSala(sala, indice, total);
  return { x: vaga.x, y: sala.pos_y + sala.altura * 0.78 };
}
