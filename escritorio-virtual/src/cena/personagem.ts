/**
 * Personagem 2D desenhada por codigo.
 *
 * Nao ha asset externo: cabeca, cabelo, corpo, bracos e pernas sao formas do
 * proprio Phaser, coloridas pela paleta do slug. Isso evita dependencia de
 * arte de terceiros e faz personagem nova aparecer no mesmo instante em que e'
 * cadastrada no banco.
 *
 * TROCAR POR ARTE DE VERDADE: quando houver sprite sheet, so este arquivo
 * muda. A cena fala com a personagem por `posicionar`, `caminharPor`,
 * `aplicar`, `mostrar` e `esconder`, e nenhum desses contratos depende de
 * como ela e' desenhada.
 */

import Phaser from "phaser";

import type { Personagem } from "../types";
import type { Ponto } from "./mapa";
import { CENARIO, clarear, escurecer, hex, paletaDe } from "./paleta";

/** Velocidade da caminhada, em unidades de mundo por segundo. */
const VELOCIDADE = 150;
const DURACAO_MINIMA = 160;

const LARGURA_CORPO = 22;
const ALTURA_CORPO = 24;
const RAIO_CABECA = 9;

export class Personagem2D {
  readonly id: number;
  private readonly cena: Phaser.Scene;
  private readonly raiz: Phaser.GameObjects.Container;
  private readonly corpoGrupo: Phaser.GameObjects.Container;
  private readonly pernaEsq: Phaser.GameObjects.Rectangle;
  private readonly pernaDir: Phaser.GameObjects.Rectangle;
  private readonly bracoEsq: Phaser.GameObjects.Rectangle;
  private readonly bracoDir: Phaser.GameObjects.Rectangle;
  private readonly rotulo: Phaser.GameObjects.Text;
  private readonly selo: Phaser.GameObjects.Text;

  private caminhada: Phaser.Tweens.TweenChain | null = null;
  private balanco: Phaser.Tweens.Tween | null = null;
  private passos: Phaser.Tweens.Tween | null = null;
  private visivel = false;
  private slugAtual = "";

  /** Ultima sala em que a cena colocou a personagem (para saber se andou). */
  salaAtual: string | null = null;

  constructor(cena: Phaser.Scene, dados: Personagem, posicao: Ponto) {
    this.cena = cena;
    this.id = dados.id;
    this.raiz = cena.add.container(posicao.x, posicao.y);
    this.raiz.setDepth(10);

    const paleta = paletaDe(dados.personagem);
    this.slugAtual = dados.personagem;

    const sombra = cena.add.ellipse(0, 4, LARGURA_CORPO + 8, 9, 0x000000, 0.16);

    this.pernaEsq = cena.add.rectangle(-5, -6, 6, 13, escurecer(paleta.roupa, 0.45));
    this.pernaDir = cena.add.rectangle(5, -6, 6, 13, escurecer(paleta.roupa, 0.45));
    this.pernaEsq.setOrigin(0.5, 0);
    this.pernaDir.setOrigin(0.5, 0);

    this.corpoGrupo = cena.add.container(0, 0);

    const corpo = cena.add.graphics();
    corpo.fillStyle(paleta.roupa, 1);
    corpo.fillRoundedRect(-LARGURA_CORPO / 2, -ALTURA_CORPO - 6, LARGURA_CORPO, ALTURA_CORPO, 7);
    corpo.fillStyle(paleta.detalhe, 1);
    corpo.fillRoundedRect(-LARGURA_CORPO / 2, -ALTURA_CORPO - 6, LARGURA_CORPO, 7, 4);

    this.bracoEsq = cena.add.rectangle(-LARGURA_CORPO / 2 - 2, -ALTURA_CORPO - 2, 5, 16, paleta.roupa);
    this.bracoDir = cena.add.rectangle(LARGURA_CORPO / 2 + 2, -ALTURA_CORPO - 2, 5, 16, paleta.roupa);
    this.bracoEsq.setOrigin(0.5, 0);
    this.bracoDir.setOrigin(0.5, 0);

    const pescoco = cena.add.rectangle(0, -ALTURA_CORPO - 6, 7, 5, paleta.pele);
    pescoco.setOrigin(0.5, 1);

    const cabeca = cena.add.circle(0, -ALTURA_CORPO - 13 - RAIO_CABECA, RAIO_CABECA, paleta.pele);

    const cabelo = cena.add.graphics();
    cabelo.fillStyle(paleta.cabelo, 1);
    cabelo.fillCircle(0, -ALTURA_CORPO - 15 - RAIO_CABECA, RAIO_CABECA + 1.5);
    cabelo.fillRect(
      -RAIO_CABECA - 1.5, -ALTURA_CORPO - 15 - RAIO_CABECA,
      (RAIO_CABECA + 1.5) * 2, RAIO_CABECA + 4,
    );
    cabelo.fillStyle(paleta.pele, 1);
    cabelo.fillCircle(0, -ALTURA_CORPO - 12 - RAIO_CABECA, RAIO_CABECA - 0.5);

    const olhoEsq = cena.add.circle(-3, -ALTURA_CORPO - 13 - RAIO_CABECA, 1.2, 0x2b2119);
    const olhoDir = cena.add.circle(3, -ALTURA_CORPO - 13 - RAIO_CABECA, 1.2, 0x2b2119);

    this.corpoGrupo.add([
      corpo, this.bracoEsq, this.bracoDir, pescoco, cabelo, cabeca, olhoEsq, olhoDir,
    ]);

    this.rotulo = cena.add.text(0, 10, "", {
      fontFamily: "system-ui, sans-serif",
      fontSize: "11px",
      color: hex(CENARIO.texto),
    });
    this.rotulo.setOrigin(0.5, 0);

    this.selo = cena.add.text(RAIO_CABECA + 4, -ALTURA_CORPO - 26 - RAIO_CABECA, "", {
      fontFamily: "system-ui, sans-serif",
      fontSize: "13px",
      fontStyle: "bold",
      color: hex(CENARIO.atencao),
    });
    this.selo.setOrigin(0, 0.5);
    this.selo.setVisible(false);

    this.raiz.add([
      sombra, this.pernaEsq, this.pernaDir, this.corpoGrupo, this.rotulo, this.selo,
    ]);
    this.raiz.setAlpha(0);
    this.raiz.setVisible(false);
  }

  /** Move o container da personagem para dentro de outra camada da cena. */
  anexarEm(alvo: Phaser.GameObjects.Container): void {
    alvo.add(this.raiz);
  }

  get x(): number {
    return this.raiz.x;
  }

  get y(): number {
    return this.raiz.y;
  }

  get posicao(): Ponto {
    return { x: this.raiz.x, y: this.raiz.y };
  }

  get estaVisivel(): boolean {
    return this.visivel;
  }

  /** True quando a aparencia depende de um slug diferente do atual. */
  precisaRecriar(dados: Personagem): boolean {
    return dados.personagem !== this.slugAtual;
  }

  aplicar(dados: Personagem): void {
    this.rotulo.setText(dados.nome);
    const precisaSelo = dados.estado === "AWAY";
    this.selo.setVisible(precisaSelo);
    if (precisaSelo) this.selo.setText("!");
    this.animarOcioso(dados.estado);
  }

  posicionar(ponto: Ponto): void {
    this.pararCaminhada();
    this.raiz.setPosition(ponto.x, ponto.y);
  }

  mostrar(imediato = false): void {
    if (this.visivel) return;
    this.visivel = true;
    this.raiz.setVisible(true);
    this.cena.tweens.killTweensOf(this.raiz);
    if (imediato) {
      this.raiz.setAlpha(1);
      return;
    }
    this.cena.tweens.add({ targets: this.raiz, alpha: 1, duration: 320, ease: "Sine.easeOut" });
  }

  esconder(imediato = false): void {
    if (!this.visivel && imediato) return;
    this.visivel = false;
    this.pararCaminhada();
    this.cena.tweens.killTweensOf(this.raiz);
    if (imediato) {
      this.raiz.setAlpha(0);
      this.raiz.setVisible(false);
      return;
    }
    this.cena.tweens.add({
      targets: this.raiz,
      alpha: 0,
      duration: 320,
      ease: "Sine.easeIn",
      onComplete: () => this.raiz.setVisible(false),
    });
  }

  /**
   * Caminha pelos waypoints. Cancela qualquer caminhada anterior: o estado do
   * servidor sempre manda, entao um destino novo interrompe o antigo na hora.
   */
  caminharPor(pontos: Ponto[], duracaoMs: number, aoChegar?: () => void): void {
    this.pararCaminhada();
    if (pontos.length === 0) {
      aoChegar?.();
      return;
    }

    const porTrecho = Math.max(duracaoMs / pontos.length, DURACAO_MINIMA / pontos.length);
    this.iniciarPassos();

    this.caminhada = this.cena.tweens.chain({
      targets: this.raiz,
      tweens: pontos.map((p) => ({
        x: p.x,
        y: p.y,
        duration: porTrecho,
        ease: "Linear",
      })),
      onComplete: () => {
        this.caminhada = null;
        this.pararPassos();
        aoChegar?.();
      },
    });
  }

  /** Duracao sugerida para percorrer uma distancia, em ms. */
  static duracaoPara(distancia: number): number {
    return Math.max((distancia / VELOCIDADE) * 1000, DURACAO_MINIMA);
  }

  destruir(): void {
    this.pararCaminhada();
    this.pararOcioso();
    this.raiz.destroy(true);
  }

  // ── interno ────────────────────────────────────────────────────────────

  private pararCaminhada(): void {
    this.caminhada?.destroy();
    this.caminhada = null;
    this.pararPassos();
  }

  private iniciarPassos(): void {
    this.pararPassos();
    this.passos = this.cena.tweens.add({
      targets: [this.pernaEsq, this.bracoDir],
      angle: { from: -16, to: 16 },
      duration: 240,
      yoyo: true,
      repeat: -1,
      ease: "Sine.easeInOut",
    });
    this.cena.tweens.add({
      targets: [this.pernaDir, this.bracoEsq],
      angle: { from: 16, to: -16 },
      duration: 240,
      yoyo: true,
      repeat: -1,
      ease: "Sine.easeInOut",
    });
  }

  private pararPassos(): void {
    this.passos?.destroy();
    this.passos = null;
    this.cena.tweens.killTweensOf([this.pernaEsq, this.pernaDir, this.bracoEsq, this.bracoDir]);
    for (const membro of [this.pernaEsq, this.pernaDir, this.bracoEsq, this.bracoDir]) {
      membro.setAngle(0);
    }
  }

  private animarOcioso(estado: Personagem["estado"]): void {
    this.pararOcioso();
    if (estado === "LUNCH") {
      // Mastigando: balanco curto e rapido.
      this.balanco = this.cena.tweens.add({
        targets: this.corpoGrupo,
        y: { from: 0, to: 2 },
        duration: 420,
        yoyo: true,
        repeat: -1,
        ease: "Sine.easeInOut",
      });
      return;
    }
    if (estado === "WORKING" || estado === "AWAY") {
      // Respirando.
      this.balanco = this.cena.tweens.add({
        targets: this.corpoGrupo,
        y: { from: 0, to: -1.6 },
        duration: 1600,
        yoyo: true,
        repeat: -1,
        ease: "Sine.easeInOut",
      });
    }
  }

  private pararOcioso(): void {
    this.balanco?.destroy();
    this.balanco = null;
    this.corpoGrupo.setY(0);
  }
}

/** Cor auxiliar exportada para a cena desenhar moveis combinando. */
export const TOM_MOVEL = clarear(CENARIO.movel, 0.1);
