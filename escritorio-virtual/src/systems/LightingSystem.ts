/**
 * Iluminacao por ambiente sobre a imagem de fundo real.
 *
 * Um retangulo semi-transparente por zona (`OFFICE_ZONES`), que escurece
 * quando o ambiente esta vazio/fechado e clareia (quase transparente) quando
 * tem gente trabalhando ali — nunca um apagao geral: só o ambiente sem
 * ninguém fica escuro, os demais continuam normais.
 */

import Phaser from "phaser";

import { OFFICE_ZONES, type OfficeRoomId } from "../config/officeZones";
import type { ImageFrame } from "../environment/ImageLayout";
import { rectToScreen } from "../environment/ImageLayout";

const ESCURO_FECHADO = 0.72;
const ESCURO_VAZIO = 0.34;
const ACESO = 0;
const DURACAO_MS = 650;

export class LightingSystem {
  private readonly overlays = new Map<OfficeRoomId, Phaser.GameObjects.Rectangle>();

  constructor(
    private readonly scene: Phaser.Scene,
    private readonly layer: Phaser.GameObjects.Container,
  ) {}

  build(frame: ImageFrame): void {
    this.clear();
    for (const zone of OFFICE_ZONES) {
      const r = rectToScreen(frame, zone.rect);
      const overlay = this.scene.add.rectangle(r.x, r.y, r.width, r.height, 0x0a0e18, ESCURO_FECHADO);
      overlay.setOrigin(0, 0);
      this.overlays.set(zone.room, overlay);
      this.layer.add(overlay);
    }
  }

  clear(): void {
    for (const overlay of this.overlays.values()) overlay.destroy();
    this.overlays.clear();
  }

  /**
   * Aplica a iluminação: `lojaAberta=false` escurece tudo (loja fechada,
   * ninguém trabalhando de madrugada); com a loja aberta, cada ambiente
   * fica claro se `ocupados` contiver seu slug, e numa penumbra leve (não
   * um apagão) se estiver vazio.
   */
  apply(lojaAberta: boolean, ocupados: Set<OfficeRoomId>, imediato = false): void {
    for (const [room, overlay] of this.overlays) {
      const alvo = !lojaAberta ? ESCURO_FECHADO : ocupados.has(room) ? ACESO : ESCURO_VAZIO;
      if (Math.abs(overlay.fillAlpha - alvo) < 0.01) continue;
      this.scene.tweens.killTweensOf(overlay);
      if (imediato) {
        overlay.setFillStyle(0x0a0e18, alvo);
      } else {
        this.scene.tweens.add({
          targets: overlay,
          fillAlpha: alvo,
          duration: DURACAO_MS,
          ease: "Sine.easeInOut",
        });
      }
    }
  }

  opacidadeDe(room: OfficeRoomId): number | null {
    return this.overlays.get(room)?.fillAlpha ?? null;
  }
}
