/**
 * Controle de animacoes ja disparadas.
 *
 * O servidor marca um evento como "recente" por uma janela curta
 * (`evento_recente_segundos`, 120s por padrao). Dentro dessa janela o mesmo
 * `eventId` aparece em varios polls seguidos; sem controle, a animacao
 * dispararia a cada 10 segundos.
 *
 * ARMAZENAMENTO: nada e' gravado no navegador. O conjunto de `eventId` ja
 * vistos vive apenas em memoria, enquanto a aba estiver aberta. A escolha e'
 * deliberada:
 *
 * - um `eventId` (`ponto_98221`) e' identificador tecnico, mas nao ha motivo
 *   para persistir sequer isso;
 * - recarregar a pagina pode, no maximo, repetir UMA animacao por personagem,
 *   e so se a batida tiver menos de 120 segundos. O incomodo e' irrelevante
 *   perto de manter estado no navegador.
 *
 * O estado do servidor sempre prevalece: este modulo so decide se ANIMA a
 * transicao, nunca qual estado a personagem tem.
 */

import type { Cena, Personagem } from "../types";

export interface Transicao {
  personagemId: number;
  eventId: string;
  evento: NonNullable<Personagem["evento"]>["event"];
  estado: Personagem["estado"];
}

export class ControleDeAnimacoes {
  private readonly vistos = new Set<string>();
  /** Teto defensivo: uma aba aberta o dia todo acumula poucas dezenas. */
  private readonly limite: number;

  constructor(limite = 500) {
    this.limite = limite;
  }

  /**
   * Transicoes novas desta cena. Um `eventId` ja visto nunca volta.
   */
  novasTransicoes(cena: Cena): Transicao[] {
    const novas: Transicao[] = [];
    for (const p of cena.personagens) {
      if (!p.evento) continue;
      if (this.vistos.has(p.evento.eventId)) continue;
      this.marcar(p.evento.eventId);
      novas.push({
        personagemId: p.id,
        eventId: p.evento.eventId,
        evento: p.evento.event,
        estado: p.estado,
      });
    }
    return novas;
  }

  jaViu(eventId: string): boolean {
    return this.vistos.has(eventId);
  }

  private marcar(eventId: string): void {
    if (this.vistos.size >= this.limite) {
      // Descarta o mais antigo (Set preserva ordem de insercao).
      const primeiro = this.vistos.values().next();
      if (!primeiro.done) this.vistos.delete(primeiro.value);
    }
    this.vistos.add(eventId);
  }

  limpar(): void {
    this.vistos.clear();
  }
}

/** Mudancas de estado entre duas cenas, para destacar na tela. */
export function estadosQueMudaram(anterior: Cena | null, atual: Cena): Set<number> {
  const mudaram = new Set<number>();
  if (anterior === null) return mudaram;
  const antes = new Map(anterior.personagens.map((p) => [p.id, p.estado]));
  for (const p of atual.personagens) {
    if (antes.get(p.id) !== p.estado) mudaram.add(p.id);
  }
  return mudaram;
}
