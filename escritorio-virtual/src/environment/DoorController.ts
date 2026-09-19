/**
 * Portas do escritorio.
 *
 * A porta de RUA e' dupla e animada, com quatro estados
 * (`CLOSED`/`OPENING`/`OPEN`/`CLOSING`): e' ela que conta a historia de abrir
 * e fechar a loja. As portas INTERNAS (showrooms e refeitorio) ficam abertas,
 * encostadas na parede, como na imagem de referencia — servem de moldura para
 * o vao, nao de obstaculo.
 */

import Phaser from "phaser";

import { COR } from "../config/rooms";
import type { Porta } from "./geometry";
import type { EstadoPorta } from "./StoreController";

const DURACAO = 620;
/** Abertura de cada folha, em graus. */
const ANGULO_ABERTA = 78;

export class DoorController {
  private folhaEsquerda: Phaser.GameObjects.Rectangle | null = null;
  private folhaDireita: Phaser.GameObjects.Rectangle | null = null;
  private estado: EstadoPorta = "CLOSED";
  private tween: Phaser.Tweens.Tween | null = null;

  constructor(
    private readonly cena: Phaser.Scene,
    private readonly camada: Phaser.GameObjects.Container,
  ) {}

  get estadoAtual(): EstadoPorta {
    return this.estado;
  }

  limpar(): void {
    this.tween?.destroy();
    this.tween = null;
    this.folhaEsquerda = null;
    this.folhaDireita = null;
    this.estado = "CLOSED";
  }

  /**
   * Cria a porta de rua: duas folhas com dobradica nas pontas do vao, que
   * abrem para fora.
   */
  criarPortaDeRua(
    x: number, y: number, vao: number, espessura: number, horizontal: boolean,
  ): void {
    const metade = vao / 2;
    const comprimento = metade - 2;

    const folha = (origemX: number, ancoraX: number) => {
      const r = horizontal
        ? this.cena.add.rectangle(origemX, y, comprimento, espessura, COR.madeiraEscura)
        : this.cena.add.rectangle(x, origemX, espessura, comprimento, COR.madeiraEscura);
      r.setOrigin(horizontal ? ancoraX : 0.5, horizontal ? 0.5 : ancoraX);
      r.setStrokeStyle(2, COR.metalDourado, 0.9);
      return r;
    };

    if (horizontal) {
      this.folhaEsquerda = folha(x - metade, 0);
      this.folhaDireita = folha(x + metade, 1);
    } else {
      this.folhaEsquerda = folha(y - metade, 0);
      this.folhaDireita = folha(y + metade, 1);
    }

    this.camada.add([this.folhaEsquerda, this.folhaDireita]);
    this.aplicar("CLOSED", true);
  }

  /** Desenha o batente de uma porta interna, sempre aberta. */
  desenharPortaInterna(g: Phaser.GameObjects.Graphics, porta: Porta, espessura: number): void {
    const metade = porta.vao / 2;
    const folha = Math.min(metade * 0.82, 44);

    g.fillStyle(COR.vidro, 0.55);
    g.lineStyle(2, COR.metalDourado, 0.85);

    if (porta.horizontal) {
      // Folhas encostadas na parede, uma para cada lado do vao.
      g.fillRect(porta.x - metade, porta.y - espessura / 2 - folha, 5, folha);
      g.strokeRect(porta.x - metade, porta.y - espessura / 2 - folha, 5, folha);
      g.fillRect(porta.x + metade - 5, porta.y - espessura / 2 - folha, 5, folha);
      g.strokeRect(porta.x + metade - 5, porta.y - espessura / 2 - folha, 5, folha);
    } else {
      g.fillRect(porta.x - espessura / 2 - folha, porta.y - metade, folha, 5);
      g.strokeRect(porta.x - espessura / 2 - folha, porta.y - metade, folha, 5);
      g.fillRect(porta.x - espessura / 2 - folha, porta.y + metade - 5, folha, 5);
      g.strokeRect(porta.x - espessura / 2 - folha, porta.y + metade - 5, folha, 5);
    }
  }

  /**
   * Leva a porta ao estado pedido. `OPENING`/`CLOSING` animam e assentam
   * sozinhos em `OPEN`/`CLOSED` quando o tween termina.
   */
  aplicar(estado: EstadoPorta, imediato = false): void {
    if (!this.folhaEsquerda || !this.folhaDireita) {
      this.estado = estado;
      return;
    }
    if (estado === this.estado && !imediato) return;

    this.estado = estado;
    const aberta = estado === "OPEN" || estado === "OPENING";
    const angulo = aberta ? ANGULO_ABERTA : 0;

    this.tween?.destroy();
    if (imediato || estado === "OPEN" || estado === "CLOSED") {
      this.folhaEsquerda.setAngle(-angulo);
      this.folhaDireita.setAngle(angulo);
      this.tween = null;
      return;
    }

    this.tween = this.cena.tweens.add({
      targets: this.folhaEsquerda,
      angle: -angulo,
      duration: DURACAO,
      ease: "Cubic.easeInOut",
      onComplete: () => {
        this.tween = null;
        this.estado = aberta ? "OPEN" : "CLOSED";
      },
    });
    this.cena.tweens.add({
      targets: this.folhaDireita,
      angle: angulo,
      duration: DURACAO,
      ease: "Cubic.easeInOut",
    });
  }
}
