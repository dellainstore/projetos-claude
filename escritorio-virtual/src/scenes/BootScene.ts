/**
 * Carrega a imagem de fundo do escritório e ajusta a resolução base do jogo
 * para a resolução NATIVA da imagem, antes de iniciar a cena principal.
 *
 * Isso é o que garante pixel art nítida em qualquer tela: o jogo nasce do
 * tamanho exato da arte (nada de esticar/encolher de forma desigual), e o
 * `Phaser.Scale.FIT` cuida de caber a arte em qualquer container depois,
 * sempre preservando a proporção.
 *
 * A URL da imagem vem de `registry.get("bgUrl")`, setado por `main.ts` a
 * partir de `data-bg-url` no HTML — nunca hardcoded aqui. Aceita tanto uma
 * URL http(s) normal (produção, via `load.image` no ciclo padrão de
 * preload) quanto uma `data:` URI (usada nas capturas automatizadas, via
 * `textures.addBase64` — o loader XHR do Phaser não aceita `data:` URIs).
 */

import Phaser from "phaser";

export const BG_TEXTURE_KEY = "office-background";

const TAMANHO_PADRAO = { width: 1440, height: 900 };

export class BootScene extends Phaser.Scene {
  constructor() {
    super("boot");
  }

  preload(): void {
    this.cameras.main.setBackgroundColor("#232a36");
  }

  create(): void {
    const url = this.registry.get("bgUrl") as string | undefined;

    if (!url) {
      this.iniciarCena(TAMANHO_PADRAO.width, TAMANHO_PADRAO.height);
      return;
    }

    if (url.startsWith("data:")) {
      this.carregarBase64(url);
    } else {
      this.carregarPorUrl(url);
    }
  }

  private carregarPorUrl(url: string): void {
    this.load.image(BG_TEXTURE_KEY, url);
    this.load.once(Phaser.Loader.Events.COMPLETE, () => this.aoCarregar());
    this.load.start();
  }

  private carregarBase64(dataUri: string): void {
    const finalizar = () => this.aoCarregar();
    this.textures.once(`${Phaser.Textures.Events.ADD_KEY}${BG_TEXTURE_KEY}`, finalizar);
    this.textures.once(Phaser.Textures.Events.ERROR, finalizar);
    this.textures.addBase64(BG_TEXTURE_KEY, dataUri);
  }

  private aoCarregar(): void {
    if (!this.textures.exists(BG_TEXTURE_KEY)) {
      this.iniciarCena(TAMANHO_PADRAO.width, TAMANHO_PADRAO.height);
      return;
    }
    const img = this.textures.get(BG_TEXTURE_KEY).getSourceImage() as
      HTMLImageElement | HTMLCanvasElement | undefined;
    const width = (img && "width" in img ? img.width : 0) || TAMANHO_PADRAO.width;
    const height = (img && "height" in img ? img.height : 0) || TAMANHO_PADRAO.height;
    this.iniciarCena(width, height);
  }

  private iniciarCena(width: number, height: number): void {
    // Redimensiona a resolução BASE do jogo para bater exatamente com a
    // imagem carregada — funciona tanto para a arte real (qualquer
    // resolução) quanto para o placeholder/fallback.
    this.scale.setGameSize(width, height);
    this.game.registry.set("bgSize", { width, height });
    this.scene.start("escritorio");
  }
}
