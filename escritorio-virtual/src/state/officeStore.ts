/**
 * Guarda a ultima cena e avisa quem depende dela.
 *
 * Existe para a cena 2D, o painel de conferencia e o painel de simulacao
 * lerem a MESMA verdade, sem um chamar o outro. Modulo puro (sem Phaser, sem
 * DOM), entao da para testar a logica de precedencia sem navegador.
 *
 * Precedencia, e o motivo dela: uma cena SIMULADA (painel de
 * desenvolvimento) sobrepoe a do servidor ate alguem voltar para o modo ao
 * vivo. Sem isso, o proximo poll de 10 segundos apagaria a simulacao no meio
 * da animacao que se estava testando.
 */

import type { Cena } from "../types";

export type Origem = "api" | "simulado";

export type Ouvinte = (cena: Cena, origem: Origem) => void;

export class OfficeStore {
  private ultimaDaApi: Cena | null = null;
  private simulada: Cena | null = null;
  private readonly ouvintes = new Set<Ouvinte>();

  /** Cena que vale agora. */
  get atual(): Cena | null {
    return this.simulada ?? this.ultimaDaApi;
  }

  get origem(): Origem {
    return this.simulada ? "simulado" : "api";
  }

  /** Ultima resposta real do servidor, mesmo durante uma simulacao. */
  get daApi(): Cena | null {
    return this.ultimaDaApi;
  }

  get simulando(): boolean {
    return this.simulada !== null;
  }

  assinar(fn: Ouvinte): () => void {
    this.ouvintes.add(fn);
    const atual = this.atual;
    if (atual) fn(atual, this.origem);
    return () => this.ouvintes.delete(fn);
  }

  /** Cena vinda da API. Ignorada na tela enquanto houver simulacao ativa. */
  receberDaApi(cena: Cena): void {
    this.ultimaDaApi = cena;
    if (this.simulada) return;
    this.emitir(cena, "api");
  }

  /**
   * Aplica uma transformacao sobre a cena corrente e passa a simular.
   * Nao chama a API, nao escreve nada: e' só o que a tela mostra.
   */
  simular(transformar: (cena: Cena) => Cena): void {
    const base = this.atual;
    if (!base) return;
    this.simulada = transformar(estruturaClonada(base));
    this.emitir(this.simulada, "simulado");
  }

  /** Volta a obedecer a API. */
  voltarAoVivo(): void {
    if (!this.simulada) return;
    this.simulada = null;
    if (this.ultimaDaApi) this.emitir(this.ultimaDaApi, "api");
  }

  private emitir(cena: Cena, origem: Origem): void {
    for (const fn of this.ouvintes) fn(cena, origem);
  }
}

/** Copia profunda simples: o payload e' JSON puro, entao isto basta. */
export function estruturaClonada<T>(valor: T): T {
  const clonar = (globalThis as { structuredClone?: <V>(v: V) => V }).structuredClone;
  if (clonar) return clonar(valor);
  return JSON.parse(JSON.stringify(valor)) as T;
}
