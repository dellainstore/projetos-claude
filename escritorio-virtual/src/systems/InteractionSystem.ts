/**
 * Hover e clique em objetos interativos (computador, arara, cafeteira,
 * geladeira, mesa) e nas próprias personagens.
 *
 * Desktop: cursor vira "pointer" sobre o objeto, leve destaque no hover.
 * Celular: toque seleciona (Phaser unifica pointer events — o mesmo handler
 * cobre os dois), um botão explícito no card fecha (nunca depende só de
 * hover, que não existe em touch).
 */

import Phaser from "phaser";

import { INTERACTIVE_OBJECTS, type InteractiveObject } from "../config/officeZones";
import { pointToScreen, type ImageFrame } from "../environment/ImageLayout";
import { EmployeeCard } from "../ui/EmployeeCard";
import type { EmployeeCharacter } from "../actors/EmployeeCharacter";

/**
 * Cor do marcador por tipo de objeto. Emoji foi descartado de propósito:
 * depende de fonte de emoji instalada no sistema, e nem todo ambiente tem
 * uma (o Chromium headless usado nas capturas automatizadas não tem,
 * renderiza "tofu boxes" — quadrados vazios). Um círculo colorido sólido
 * funciona em qualquer navegador, sem depender de fonte nenhuma.
 */
const COR_MARCADOR: Record<InteractiveObject["kind"], number> = {
  computador: 0x6f9bd1,
  arara: 0xc86b7a,
  cafeteira: 0x8a5a3a,
  geladeira: 0xb9c2cb,
  mesa: 0xa8743f,
};

export class InteractionSystem {
  private readonly marcadores: Array<{ obj: InteractiveObject; zone: Phaser.GameObjects.Zone; icone: Phaser.GameObjects.Arc }> = [];

  constructor(
    private readonly scene: Phaser.Scene,
    private readonly layer: Phaser.GameObjects.Container,
    private readonly card: EmployeeCard,
  ) {}

  build(frame: ImageFrame): void {
    this.clear();
    for (const obj of INTERACTIVE_OBJECTS) {
      const p = pointToScreen(frame, obj.point);
      const raio = obj.radius * frame.displayWidth;

      const raioIcone = Math.max(raio * 0.6, 7);
      const icone = this.scene.add.circle(p.x, p.y, raioIcone, COR_MARCADOR[obj.kind], 0.9);
      icone.setStrokeStyle(1.5, 0x241f1a, 0.85);

      const zone = this.scene.add.zone(p.x, p.y, raio * 2.4, raio * 2.4);
      zone.setInteractive({ useHandCursor: true });
      zone.on("pointerover", () => this.scene.tweens.add({ targets: icone, scale: 1.25, duration: 120 }));
      zone.on("pointerout", () => this.scene.tweens.add({ targets: icone, scale: 1, duration: 120 }));
      zone.on("pointerdown", () => this.card.show({ kind: "object", label: obj.label }));

      this.layer.add([icone, zone]);
      this.marcadores.push({ obj, zone, icone });
    }
  }

  /** Liga o clique/hover na personagem ao mesmo cartão de detalhes. */
  registerEmployee(character: EmployeeCharacter, getPersonagem: () => import("../types").Personagem | undefined): void {
    const go = character.gameObject;
    go.setInteractive({ useHandCursor: true });
    go.on("pointerover", () => this.scene.tweens.add({ targets: go, scale: 1.06, duration: 100 }));
    go.on("pointerout", () => this.scene.tweens.add({ targets: go, scale: 1, duration: 100 }));
    go.on("pointerdown", () => {
      const p = getPersonagem();
      if (p) this.card.show({ kind: "employee", personagem: p });
    });
  }

  clear(): void {
    for (const m of this.marcadores) { m.zone.destroy(); m.icone.destroy(); }
    this.marcadores.length = 0;
  }
}
