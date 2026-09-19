/**
 * Ambiente de navegador minimo para bootar o Phaser em HEADLESS dentro do Node.
 *
 * Existe por um motivo so: a cena 2D e a personagem sao ~400 linhas de codigo
 * Phaser que o `tsc` valida mas nao EXECUTA. Sem isso, um `tweens.chain` mal
 * usado ou um metodo que nao existe mais so apareceria no navegador do
 * usuario. Aqui a cena roda de verdade, com dados de verdade.
 *
 * Precisa ser importado ANTES do Phaser.
 */

import { JSDOM } from "jsdom";

export function prepararDOM(): JSDOM {
  const dom = new JSDOM("<!DOCTYPE html><html><body><div id=\"palco\"></div></body></html>", {
    pretendToBeVisual: true,
    url: "https://sistemas.example/escritorio/",
  });

  const g = globalThis as Record<string, unknown>;
  // O `phaser3spectorjs` (debug de WebGL, puxado pela arvore de fontes do
  // Phaser) e' um bundle de navegador e referencia `self` no topo. Sem isso
  // ele estoura antes de qualquer coisa nossa rodar.
  g.self = globalThis;
  g.window = dom.window;
  g.document = dom.window.document;
  g.navigator = dom.window.navigator;
  g.location = dom.window.location;
  // O jsdom nao carrega data-URI, entao o `onload` das texturas padrao do
  // Phaser nunca dispara e o evento `ready` do jogo nunca chega. Esta Image
  // falsa resolve na hora: nao ha imagem de verdade para carregar aqui.
  g.Image = ImagemFalsa;
  g.HTMLImageElement = ImagemFalsa;
  g.HTMLElement = dom.window.HTMLElement;
  g.HTMLCanvasElement = dom.window.HTMLCanvasElement;
  g.HTMLVideoElement = dom.window.HTMLVideoElement;
  g.Element = dom.window.Element;
  g.Event = dom.window.Event;
  g.MouseEvent = dom.window.MouseEvent;
  g.TouchEvent = dom.window.TouchEvent;
  g.KeyboardEvent = dom.window.KeyboardEvent;
  g.WheelEvent = dom.window.WheelEvent;
  g.XMLHttpRequest = dom.window.XMLHttpRequest;
  g.requestAnimationFrame = dom.window.requestAnimationFrame.bind(dom.window);
  g.cancelAnimationFrame = dom.window.cancelAnimationFrame.bind(dom.window);
  g.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);
  g.screen = dom.window.screen;
  // `performance` NAO e' sobrescrito de proposito: o Node ja tem o dele, e
  // apontar o global para o do jsdom causa recursao infinita (a implementacao
  // do jsdom consulta o global). O TweenManager do Phaser mede o tempo com
  // `Date.now()` de qualquer forma.
  g.devicePixelRatio = 1;
  g.Blob = dom.window.Blob;
  g.URL = dom.window.URL;
  g.CanvasRenderingContext2D = dom.window.CanvasRenderingContext2D;
  g.ImageData = dom.window.ImageData;
  g.matchMedia =
    dom.window.matchMedia ??
    (() => ({ matches: false, addListener: () => undefined, removeListener: () => undefined }));

  // O jsdom nao implementa canvas de verdade; o renderer HEADLESS do Phaser
  // nao desenha nada, mas alguns caminhos internos ainda pedem um contexto.
  const proto = dom.window.HTMLCanvasElement.prototype as unknown as {
    getContext: (tipo: string) => unknown;
  };
  proto.getContext = () => contexto2dFalso();

  return dom;
}

/** Image que "carrega" imediatamente: o jsdom nao busca data-URI. */
class ImagemFalsa {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  width = 1;
  height = 1;
  complete = true;
  private valor = "";

  get src(): string {
    return this.valor;
  }

  set src(v: string) {
    this.valor = v;
    queueMicrotask(() => this.onload?.());
  }
}

/** Contexto 2D inerte: aceita qualquer chamada e nao desenha. */
function contexto2dFalso(): Record<string, unknown> {
  const ruido = () => undefined;
  return new Proxy(
    {
      canvas: null,
      fillStyle: "",
      strokeStyle: "",
      globalAlpha: 1,
      measureText: () => ({ width: 10 }),
      getImageData: () => ({ data: new Uint8ClampedArray(4) }),
      createLinearGradient: () => ({ addColorStop: ruido }),
      createPattern: () => null,
      save: ruido,
      restore: ruido,
    } as Record<string, unknown>,
    {
      get(alvo, chave) {
        if (chave in alvo) return alvo[chave as string];
        return ruido;
      },
      set(alvo, chave, valor) {
        alvo[chave as string] = valor;
        return true;
      },
    },
  );
}
