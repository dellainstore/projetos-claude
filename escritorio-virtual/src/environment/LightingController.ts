/**
 * Iluminacao por COMODO, nao um apagao geral do escritorio.
 *
 * Com a loja aberta, acende onde tem gente mais as areas de circulacao
 * (corredor e entrada); comodo vazio fica na penumbra. Com a loja fechada,
 * tudo apagado. A decisao de QUAIS comodos acendem e' de `geometry.comodosAcesos`
 * (puro e testado); aqui so fica o tween.
 */

import Phaser from "phaser";

import type { Sala } from "../types";
import { COR } from "../config/rooms";

/** Opacidade da sombra em cada situacao. */
export const SOMBRA = {
  ACESO: 0,
  COMODO_VAZIO: 0.26,
  LOJA_FECHADA: 0.62,
} as const;

const DURACAO = 650;

export class LightingController {
  private readonly sombras = new Map<string, Phaser.GameObjects.Rectangle>();
  private readonly brilhos = new Map<string, Phaser.GameObjects.Rectangle>();

  constructor(
    private readonly cena: Phaser.Scene,
    private readonly camada: Phaser.GameObjects.Container,
  ) {}

  limpar(): void {
    this.sombras.clear();
    this.brilhos.clear();
  }

  /** Cria a sombra e o brilho quente de um comodo. */
  registrar(sala: Sala, area: { x: number; y: number; largura: number; altura: number }): void {
    const brilho = this.cena.add.rectangle(
      area.x, area.y, area.largura, area.altura, 0xffd9a0, 1,
    );
    brilho.setOrigin(0, 0);
    brilho.setAlpha(0);
    brilho.setBlendMode(Phaser.BlendModes.MULTIPLY);

    const sombra = this.cena.add.rectangle(
      area.x, area.y, area.largura, area.altura, COR.luzApagada, 1,
    );
    sombra.setOrigin(0, 0);
    sombra.setAlpha(SOMBRA.LOJA_FECHADA);

    this.brilhos.set(sala.slug, brilho);
    this.sombras.set(sala.slug, sombra);
    this.camada.add([brilho, sombra]);
  }

  /** Aplica a iluminacao. `imediato` pula o tween (carga inicial e testes). */
  aplicar(acesos: Set<string>, lojaAberta: boolean, imediato = false): void {
    for (const [slug, sombra] of this.sombras) {
      const alvo = !lojaAberta
        ? SOMBRA.LOJA_FECHADA
        : acesos.has(slug) ? SOMBRA.ACESO : SOMBRA.COMODO_VAZIO;
      this.mover(sombra, alvo, imediato);

      const brilho = this.brilhos.get(slug);
      if (brilho) {
        this.mover(brilho, lojaAberta && acesos.has(slug) ? 0.16 : 0, imediato);
      }
    }
  }

  /** Opacidade atual da sombra de um comodo. Exposto para teste. */
  opacidadeDe(slug: string): number | null {
    return this.sombras.get(slug)?.alpha ?? null;
  }

  private mover(alvo: Phaser.GameObjects.Rectangle, valor: number, imediato: boolean): void {
    if (Math.abs(alvo.alpha - valor) < 0.01) return;
    this.cena.tweens.killTweensOf(alvo);
    if (imediato) {
      alvo.setAlpha(valor);
      return;
    }
    this.cena.tweens.add({
      targets: alvo, alpha: valor, duration: DURACAO, ease: "Sine.easeInOut",
    });
  }
}
