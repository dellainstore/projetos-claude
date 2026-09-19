/**
 * Personagem em pixel art PROCEDURAL: gerada pixel a pixel num canvas (blocos
 * de cor sólida, sem anti-aliasing, contorno escuro de 1px), registrada como
 * textura do Phaser e desenhada com filtro NEAREST — nada de círculo,
 * cápsula ou retângulo suave. É um estilo pixel-art legítimo (muito usado em
 * jogos indie para placeholder de personagem), mas **não é um spritesheet
 * desenhado à mão**: é a solução enquanto o spritesheet real não chega (ver
 * `ASSETS_LICENSES.md` para a especificação exata do que substituir aqui).
 *
 * Contrato com a cena: `posicionar`, `caminharPor`, `aplicar`, `mostrar`,
 * `esconder` — os mesmos nomes de sempre, para a cena nunca depender de como
 * a personagem é desenhada por dentro.
 */

import Phaser from "phaser";

import type { Personagem } from "../types";

export interface PixelPalette {
  pele: number;
  cabelo: number;
  roupa: number;
  roupaEscura: number;
  sapato: number;
}

const LARGURA = 20;
const ALTURA = 30;

function hexCss(cor: number): string {
  return `#${cor.toString(16).padStart(6, "0")}`;
}

/**
 * Desenha a personagem num canvas 20x30, pixel a pixel (fillRect com
 * coordenadas inteiras — sem anti-aliasing), em duas variantes: de frente
 * (`facing="front"`, usada parada/andando para baixo ou para os lados via
 * espelhamento) e de costas (`facing="back"`, usada andando para cima).
 * `passo` alterna a posição das pernas para o ciclo de caminhada.
 */
function desenharPersonagem(
  ctx: CanvasRenderingContext2D, paleta: PixelPalette, facing: "front" | "back", passo: boolean,
): void {
  const contorno = "#241f1a";
  const px = (x: number, y: number, w: number, h: number, cor: string) => {
    ctx.fillStyle = cor;
    ctx.fillRect(x, y, w, h);
  };

  ctx.clearRect(0, 0, LARGURA, ALTURA);

  // Sombra no chão.
  px(4, 27, 12, 2, "rgba(0,0,0,0.25)");

  // Pernas (alternam no passo).
  const pernaEsqX = passo ? 6 : 7;
  const pernaDirX = passo ? 11 : 10;
  px(pernaEsqX, 20, 3, 7, hexCss(paleta.roupaEscura));
  px(pernaDirX, 20, 3, 7, hexCss(paleta.roupaEscura));
  px(pernaEsqX, 26, 3, 2, hexCss(paleta.sapato));
  px(pernaDirX, 26, 3, 2, hexCss(paleta.sapato));

  // Torso.
  px(5, 11, 10, 10, hexCss(paleta.roupa));
  px(5, 11, 10, 2, hexCss(paleta.roupaEscura)); // gola/ombro

  // Braços.
  px(3, 12, 2, 8, hexCss(paleta.roupa));
  px(15, 12, 2, 8, hexCss(paleta.roupa));
  px(3, 19, 2, 2, hexCss(paleta.pele));
  px(15, 19, 2, 2, hexCss(paleta.pele));

  // Cabeça.
  px(6, 3, 8, 8, hexCss(paleta.pele));

  if (facing === "front") {
    // Olhos (só de frente).
    px(8, 6, 1, 1, contorno);
    px(11, 6, 1, 1, contorno);
    // Cabelo: franja + laterais.
    px(6, 1, 8, 3, hexCss(paleta.cabelo));
    px(5, 3, 2, 5, hexCss(paleta.cabelo));
    px(13, 3, 2, 5, hexCss(paleta.cabelo));
  } else {
    // De costas: cabelo cobre a cabeça inteira, sem rosto.
    px(5, 1, 10, 9, hexCss(paleta.cabelo));
    px(6, 3, 8, 7, hexCss(paleta.pele)); // pescoço/nuca à mostra por baixo
    px(5, 1, 10, 5, hexCss(paleta.cabelo));
  }

  // Contorno simples (silhueta) para separar do fundo.
  ctx.strokeStyle = contorno;
  ctx.lineWidth = 1;
  ctx.strokeRect(5.5, 11.5, 10, 10);
  ctx.strokeRect(6.5, 3.5, 8, 8);
}

function chavesTextura(slug: string) {
  return {
    frontIdle: `emp-${slug}-front-idle`,
    frontWalk: `emp-${slug}-front-walk`,
    backIdle: `emp-${slug}-back-idle`,
    backWalk: `emp-${slug}-back-walk`,
  };
}

/** Gera (ou reaproveita, se já existir) as 4 texturas de uma personagem. */
export function garantirTexturas(scene: Phaser.Scene, slug: string, paleta: PixelPalette): ReturnType<typeof chavesTextura> {
  const chaves = chavesTextura(slug);
  const specs: Array<[string, "front" | "back", boolean]> = [
    [chaves.frontIdle, "front", false],
    [chaves.frontWalk, "front", true],
    [chaves.backIdle, "back", false],
    [chaves.backWalk, "back", true],
  ];
  for (const [key, facing, passo] of specs) {
    if (scene.textures.exists(key)) continue;
    const canvasTexture = scene.textures.createCanvas(key, LARGURA, ALTURA);
    if (!canvasTexture) continue;
    const ctx = canvasTexture.getContext();
    ctx.imageSmoothingEnabled = false;
    desenharPersonagem(ctx, paleta, facing, passo);
    try {
      // `refresh()` sobe o canvas para a GPU (WebGL). Sob `Phaser.HEADLESS`
      // (usado nos testes automatizados, sem renderer nenhum) essa chamada
      // sempre falha — inofensivo ali, porque nada é desenhado na tela de
      // qualquer forma. No navegador real (Phaser.AUTO), com renderer de
      // verdade, o refresh acontece normalmente.
      canvasTexture.refresh();
    } catch {
      /* ambiente sem renderer (headless/teste) — sem efeito visual aqui. */
    }
    canvasTexture.setFilter(Phaser.Textures.FilterMode.NEAREST);
  }
  return chaves;
}

const VELOCIDADE = 130; // pixels de tela por segundo
const DURACAO_MINIMA = 200;
const ESCALA_EXIBICAO = 2.6;

export class EmployeeCharacter {
  readonly id: number;
  private readonly scene: Phaser.Scene;
  private readonly raiz: Phaser.GameObjects.Container;
  private readonly sprite: Phaser.GameObjects.Sprite;
  private readonly nomeTag: Phaser.GameObjects.Text;
  private readonly nomeFundo: Phaser.GameObjects.Rectangle;
  private readonly alerta: Phaser.GameObjects.Text;
  private readonly chaves: ReturnType<typeof chavesTextura>;

  private caminhada: Phaser.Tweens.TweenChain | null = null;
  private cicloAndar: Phaser.Time.TimerEvent | null = null;
  private idleTween: Phaser.Tweens.Tween | null = null;
  private visivel = false;
  private nome = "";

  /** Última sala em que a cena colocou a personagem. */
  salaAtual: string | null = null;

  constructor(scene: Phaser.Scene, dados: Personagem, paleta: PixelPalette, x: number, y: number) {
    this.scene = scene;
    this.id = dados.id;
    this.chaves = garantirTexturas(scene, dados.personagem, paleta);

    this.raiz = scene.add.container(x, y);

    this.sprite = scene.add.sprite(0, 0, this.chaves.frontIdle);
    this.sprite.setOrigin(0.5, 0.92);
    this.sprite.setScale(ESCALA_EXIBICAO);

    this.nomeFundo = scene.add.rectangle(0, -this.spriteAlturaExibida() - 12, 10, 16, 0x241f1a, 0.85);
    this.nomeTag = scene.add.text(0, -this.spriteAlturaExibida() - 12, dados.nome, {
      fontFamily: "system-ui, sans-serif",
      fontSize: "11px",
      fontStyle: "600",
      color: "#f5ece0",
    });
    this.nomeTag.setOrigin(0.5, 0.5);
    this.nomeFundo.setSize(this.nomeTag.width + 14, 16);

    this.alerta = scene.add.text(this.sprite.displayWidth / 2, -this.spriteAlturaExibida() - 30, "!", {
      fontFamily: "system-ui, sans-serif",
      fontSize: "14px",
      fontStyle: "bold",
      color: "#ffe0e0",
      backgroundColor: "#c2493f",
      padding: { x: 4, y: 1 },
    });
    this.alerta.setOrigin(0.5, 0.5);
    this.alerta.setVisible(false);

    this.raiz.add([this.nomeFundo, this.nomeTag, this.sprite, this.alerta]);
    this.raiz.setAlpha(0);
    this.raiz.setVisible(false);
    this.raiz.setSize(this.sprite.displayWidth, this.sprite.displayHeight);
    this.raiz.setInteractive(
      new Phaser.Geom.Rectangle(-this.sprite.displayWidth / 2, -this.sprite.displayHeight, this.sprite.displayWidth, this.sprite.displayHeight),
      Phaser.Geom.Rectangle.Contains,
    );
  }

  private spriteAlturaExibida(): number {
    return ALTURA * ESCALA_EXIBICAO;
  }

  get gameObject(): Phaser.GameObjects.Container {
    return this.raiz;
  }

  get x(): number { return this.raiz.x; }
  get y(): number { return this.raiz.y; }
  get posicao(): { x: number; y: number } { return { x: this.raiz.x, y: this.raiz.y }; }
  get estaVisivel(): boolean { return this.visivel; }
  get opacidade(): number { return this.raiz.alpha; }

  precisaRecriar(_dados: Personagem): boolean {
    return false; // a paleta é fixa por slug; nunca precisa recriar aqui.
  }

  aplicar(dados: Personagem): void {
    this.nome = dados.nome;
    if (this.nomeTag.text !== this.nome) {
      this.nomeTag.setText(this.nome);
      this.nomeFundo.setSize(this.nomeTag.width + 14, 16);
    }
    const mostrarAlerta = dados.estado === "AWAY" || dados.inconsistencia !== null;
    this.alerta.setVisible(mostrarAlerta);
    this.animarOcioso(dados.estado);
  }

  posicionar(p: { x: number; y: number }): void {
    this.pararCaminhada();
    this.raiz.setPosition(p.x, p.y);
  }

  mostrar(imediato = false): void {
    if (this.visivel) return;
    this.visivel = true;
    this.raiz.setVisible(true);
    this.scene.tweens.killTweensOf(this.raiz);
    if (imediato) { this.raiz.setAlpha(1); return; }
    this.scene.tweens.add({ targets: this.raiz, alpha: 1, duration: 320, ease: "Sine.easeOut" });
  }

  esconder(imediato = false): void {
    if (!this.visivel && imediato) return;
    this.visivel = false;
    this.pararCaminhada();
    this.scene.tweens.killTweensOf(this.raiz);
    if (imediato) { this.raiz.setAlpha(0); this.raiz.setVisible(false); return; }
    this.scene.tweens.add({
      targets: this.raiz, alpha: 0, duration: 320, ease: "Sine.easeIn",
      onComplete: () => this.raiz.setVisible(false),
    });
  }

  /** Caminha pelos waypoints (pixels de tela), virando o sprite conforme a direção. */
  caminharPor(pontos: Array<{ x: number; y: number }>, duracaoMs: number, aoChegar?: () => void): void {
    this.pararCaminhada();
    if (pontos.length === 0) { aoChegar?.(); return; }

    const porTrecho = Math.max(duracaoMs / pontos.length, DURACAO_MINIMA / pontos.length);
    this.iniciarCicloDeAndar();

    this.caminhada = this.scene.tweens.chain({
      targets: this.raiz,
      tweens: pontos.map((p) => ({ x: p.x, y: p.y, duration: porTrecho, ease: "Linear" })),
      onComplete: () => {
        this.caminhada = null;
        this.pararCicloDeAndar();
        this.sprite.setTexture(this.chaves.frontIdle);
        aoChegar?.();
      },
    });

    // Orientação: horizontal pelo sinal do deslocamento total; vertical
    // (de costas) quando o movimento é majoritariamente para cima.
    const alvo = pontos[pontos.length - 1];
    const dx = alvo.x - this.raiz.x;
    const dy = alvo.y - this.raiz.y;
    if (dx < -2) this.sprite.setFlipX(true);
    else if (dx > 2) this.sprite.setFlipX(false);
    this.deCostas = dy < -6 && Math.abs(dy) > Math.abs(dx);
  }

  static duracaoPara(distancia: number): number {
    return Math.max((distancia / VELOCIDADE) * 1000, DURACAO_MINIMA);
  }

  destruir(): void {
    this.pararCaminhada();
    this.pararOcioso();
    this.raiz.destroy(true);
  }

  // ── interno ────────────────────────────────────────────────────────────

  private deCostas = false;
  private passoAtual = false;

  private iniciarCicloDeAndar(): void {
    this.pararCicloDeAndar();
    this.cicloAndar = this.scene.time.addEvent({
      delay: 220,
      loop: true,
      callback: () => {
        this.passoAtual = !this.passoAtual;
        const chave = this.deCostas
          ? (this.passoAtual ? this.chaves.backWalk : this.chaves.backIdle)
          : (this.passoAtual ? this.chaves.frontWalk : this.chaves.frontIdle);
        this.sprite.setTexture(chave);
      },
    });
  }

  private pararCicloDeAndar(): void {
    this.cicloAndar?.remove();
    this.cicloAndar = null;
  }

  private pararCaminhada(): void {
    this.caminhada?.destroy();
    this.caminhada = null;
    this.pararCicloDeAndar();
  }

  private animarOcioso(estado: Personagem["estado"]): void {
    this.pararOcioso();
    if (estado === "WORKING" || estado === "LUNCH" || estado === "AWAY") {
      this.idleTween = this.scene.tweens.add({
        targets: this.sprite, y: { from: 0, to: -1 }, duration: 1500, yoyo: true, repeat: -1, ease: "Sine.easeInOut",
      });
    }
  }

  private pararOcioso(): void {
    this.idleTween?.destroy();
    this.idleTween = null;
    this.sprite.setY(0);
  }
}
