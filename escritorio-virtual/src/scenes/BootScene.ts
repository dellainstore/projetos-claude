/**
 * Cena de carga.
 *
 * Hoje o cenario inteiro e' desenhado por codigo (Phaser Graphics), entao nao
 * ha arquivo de arte para baixar e esta cena termina num piscar. Ela existe
 * mesmo assim por dois motivos:
 *
 * 1. e' o lugar certo para o `preload` quando entrarem sprites de verdade, e
 *    trocar arte nao vai mexer na cena do escritorio;
 * 2. evita o "flash" de fundo branco: pinta o fundo certo antes de tudo.
 *
 * Se um dia houver atlas, ele entra aqui, e so aqui.
 */

import Phaser from "phaser";

import { COR } from "../config/rooms";
import { hex } from "../config/characters";

export class BootScene extends Phaser.Scene {
  constructor() {
    super("boot");
  }

  preload(): void {
    this.cameras.main.setBackgroundColor(hex(COR.foraDoPredio));
    // Sem assets externos: tudo e' procedural. Quando houver atlas:
    //   this.load.atlas("personagens", "escritorio/personagens.png", "...json");
  }

  create(): void {
    this.scene.start("escritorio");
  }
}
