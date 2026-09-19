/**
 * Etiqueta com o nome da personagem, no estilo da imagem de referencia:
 * pilula escura com texto claro, flutuando acima da cabeca.
 *
 * Vive numa camada ACIMA dos moveis, e nao dentro da personagem. Sem isso o
 * nome de quem esta atras do balcao ficaria escondido pelo proprio balcao —
 * que e' desenhado na frente de proposito.
 */

import Phaser from "phaser";

import { COR } from "../config/rooms";
import { hex } from "../config/characters";

/** Altura da etiqueta acima do ponto onde a personagem pisa. */
const ACIMA_DA_CABECA = 96;

export class NameTag {
  private readonly raiz: Phaser.GameObjects.Container;
  private readonly fundo: Phaser.GameObjects.Rectangle;
  private readonly texto: Phaser.GameObjects.Text;

  constructor(cena: Phaser.Scene, camada: Phaser.GameObjects.Container, nome: string) {
    this.texto = cena.add.text(0, 0, nome, {
      fontFamily: "system-ui, sans-serif",
      fontSize: "13px",
      fontStyle: "600",
      color: hex(COR.paredeInterna),
    });
    this.texto.setOrigin(0.5, 0.5);

    this.fundo = cena.add.rectangle(
      0, 0, this.texto.width + 18, 22, COR.acentoShowroom, 0.92,
    );
    this.fundo.setStrokeStyle(1, COR.metalDourado, 0.5);

    this.raiz = cena.add.container(0, 0, [this.fundo, this.texto]);
    this.raiz.setAlpha(0);
    camada.add(this.raiz);
  }

  definirNome(nome: string): void {
    if (this.texto.text === nome) return;
    this.texto.setText(nome);
    this.fundo.setSize(this.texto.width + 18, 22);
  }

  /** Acompanha a personagem. Chamado uma vez por quadro, para todas juntas. */
  seguir(x: number, y: number, visivel: boolean, opacidade: number): void {
    this.raiz.setPosition(x, y - ACIMA_DA_CABECA);
    this.raiz.setVisible(visivel);
    this.raiz.setAlpha(opacidade);
  }

  destruir(): void {
    this.raiz.destroy(true);
  }
}
