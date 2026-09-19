/**
 * Entrada do bundle: liga a API a cena 2D, ao painel de conferencia e ao
 * painel de simulacao.
 *
 * Quem manda no que aparece e' o `OfficeStore`. A cena so ouve.
 *
 * Modos, um de cada vez:
 *
 * - AO VIVO: o `Poller` consulta a cada 10s, com ETag/304 e pausa em aba
 *   oculta;
 * - PRE-VISUALIZACAO: um instante passado escolhido na tela, com as batidas
 *   REAIS daquele dia. Uma consulta so, sem polling;
 * - REPLAY: percorre o dia em passos, para ver o expediente inteiro;
 * - SIMULACAO: estados inventados no navegador, so para testar animacao
 *   (painel de desenvolvimento, nunca toca no ponto).
 */

import Phaser from "phaser";

import { BootScene } from "./scenes/BootScene";
import { OfficeScene } from "./scenes/OfficeScene";
import { montarLegenda } from "./ui/StatusLegend";
import { ControleDeAnimacoes, estadosQueMudaram } from "./state/diff";
import { OfficeStore } from "./state/officeStore";
import { Poller } from "./state/poller";
import { DebugPanel, podeSimular } from "./ui/DebugPanel";
import {
  assinaturaDaCena,
  registrarTransicoes,
  renderizarAviso,
  renderizarCena,
  renderizarContagem,
  renderizarMeta,
  renderizarModo,
  type Alvos,
} from "./ui/painel";
import type { Cena, MetaPoll } from "./types";

/** Janela e passo do replay do dia. */
const REPLAY_INICIO_MIN = 7 * 60;
const REPLAY_FIM_MIN = 21 * 60;
const REPLAY_PASSO_MIN = 10;
const REPLAY_INTERVALO_MS = 520;

function exigir<T extends HTMLElement>(raiz: ParentNode, seletor: string): T {
  const el = raiz.querySelector<T>(seletor);
  if (!el) throw new Error(`elemento ausente no HTML: ${seletor}`);
  return el;
}

function hhmm(minutos: number): string {
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/**
 * Caminho da imagem de fundo. Enquanto o arquivo oficial não é aprovado e
 * salvo em `della_sistemas/static/escritorio/office-bg.png`, cai num
 * placeholder claramente identificado (não é a arte final — ver
 * `ASSETS_LICENSES.md`).
 */
function resolverUrlDeFundo(raiz: HTMLElement): string {
  return raiz.dataset.bgUrl || "escritorio/office-bg-placeholder.svg";
}

function montarJogo(
  destino: HTMLElement, cardHost: HTMLElement, store: OfficeStore, bgUrl: string,
  aoRedimensionar: (tamanho: { width: number; height: number }) => void,
): Phaser.Game {
  let cenaJogo: OfficeScene | null = null;

  const jogo = new Phaser.Game({
    type: Phaser.AUTO,
    parent: destino,
    width: 1440,
    height: 900,
    backgroundColor: "#1c2230",
    banner: false,
    audio: { noAudio: true },
    // Pixel art nítida: sem suavização/antialiasing e com os pixels sempre
    // arredondados para posição inteira na tela.
    pixelArt: true,
    roundPixels: true,
    antialias: false,
    scale: {
      // FIT mantém a proporção da arte em qualquer tela: nada de ambiente
      // esticado no celular nem entrada cortada.
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_HORIZONTALLY,
    },
    scene: [BootScene, OfficeScene],
  });

  jogo.registry.set("bgUrl", bgUrl);
  jogo.registry.set("cardHost", cardHost);
  jogo.registry.events.on("changedata-bgSize", (_parent: unknown, value: { width: number; height: number }) => {
    aoRedimensionar(value);
  });

  // Uma unica assinatura: o store decide o que vale, a cena so reflete.
  store.assinar((cena) => {
    cenaJogo ??= jogo.scene.getScene("escritorio") as OfficeScene | null;
    cenaJogo?.aplicar(cena);
  });

  jogo.events.once("ready", () => {
    cenaJogo = jogo.scene.getScene("escritorio") as OfficeScene;
    const atual = store.atual;
    if (atual) cenaJogo.aplicar(atual);
  });

  return jogo;
}

function iniciar(): void {
  const raiz = document.getElementById("escritorio-diagnostico");
  if (!raiz) return; // bundle carregado em outra pagina: nao faz nada

  const url = raiz.dataset.apiUrl;
  if (!url) throw new Error("data-api-url ausente no container do escritório");
  const intervaloMs = Number(raiz.dataset.pollSegundos ?? "10") * 1000;

  const alvos: Alvos = {
    loja: exigir(raiz, "[data-ev=loja]"),
    luzes: exigir(raiz, "[data-ev=luzes]"),
    pendencias: exigir(raiz, "[data-ev=pendencias]"),
    data: exigir(raiz, "[data-ev=data]"),
    corpo: exigir(raiz, "[data-ev=corpo]"),
    situacao: exigir(raiz, "[data-ev=situacao]"),
    atualizadoEm: exigir(raiz, "[data-ev=atualizado]"),
    contagem: exigir(raiz, "[data-ev=contagem]"),
    erro: exigir(raiz, "[data-ev=erro]"),
    avisos: exigir(raiz, "[data-ev=avisos]"),
    log: exigir(raiz, "[data-ev=log]"),
    modo: exigir(raiz, "[data-ev=modo]"),
    aviso: exigir(raiz, "[data-ev=aviso]"),
  };

  const store = new OfficeStore();
  const palco = exigir(raiz, "[data-ev=palco]");
  const cardHost = palco; // o card fica ancorado dentro do próprio palco.
  const bgUrl = resolverUrlDeFundo(raiz);

  // Proporção do palco: parte de um valor padrão (evita "pulo" de layout) e
  // é corrigida para a proporção REAL da imagem assim que ela carrega — é
  // isso, e não mais brigar com `height:auto` no CSS, que evita a cena
  // "puxando zoom" sozinha ao abrir.
  palco.style.aspectRatio = "1440 / 900";
  montarJogo(palco, cardHost, store, bgUrl, ({ width, height }) => {
    palco.style.aspectRatio = `${width} / ${height}`;
    palco.classList.add("ev-palco-pronto");
  });

  montarUiComplementar(raiz, palco);

  const animacoes = new ControleDeAnimacoes();
  let cenaAnterior: Cena | null = null;
  let metaAtual: MetaPoll | null = null;

  const campoData = exigir<HTMLInputElement>(raiz, "[data-ev=campo-data]");
  const campoHora = exigir<HTMLInputElement>(raiz, "[data-ev=campo-hora]");

  // Painel de conferencia e log de transicoes seguem a MESMA cena da 2D.
  let assinaturaAnterior: string | null = null;

  store.assinar((cena, origem) => {
    const assinatura = assinaturaDaCena(cena);
    const repetida = assinaturaAnterior === assinatura;

    renderizarCena(alvos, cena, estadosQueMudaram(cenaAnterior, cena));
    registrarTransicoes(alvos, animacoes.novasTransicoes(cena));
    renderizarModo(alvos, cena, origem === "simulado");
    renderizarAviso(alvos, cena, { repetida });
    if (metaAtual) renderizarMeta(alvos, metaAtual);
    cenaAnterior = cena;
    assinaturaAnterior = assinatura;

    const sugestao = cena.preview?.diaSugerido;
    if (sugestao && !campoData.value) campoData.value = sugestao;
  });

  const poller = new Poller({
    url,
    intervaloMs,
    onCena: (cena, meta) => {
      metaAtual = meta;
      store.receberDaApi(cena);
      renderizarMeta(alvos, meta);
    },
    onSemMudanca: (meta) => {
      metaAtual = meta;
      renderizarMeta(alvos, meta);
    },
    onErro: (_mensagem, meta) => {
      metaAtual = meta;
      renderizarMeta(alvos, meta);
    },
    onMeta: (meta) => {
      metaAtual = meta;
      renderizarMeta(alvos, meta);
    },
  });

  // ── painel de simulação (só para quem o servidor autorizou) ──────────

  const debug = podeSimular(raiz)
    ? new DebugPanel(exigir(raiz, "[data-ev=debug]"), store)
    : null;
  if (debug) {
    let montado = false;
    store.assinar((cena) => {
      // Monta uma vez, quando o elenco chega; depois só se o elenco mudar.
      if (montado && cena.personagens.length > 0) return;
      montado = cena.personagens.length > 0;
      debug.montar();
    });
  }

  // ── controles de pré-visualização ────────────────────────────────────

  const botaoVer = exigir<HTMLButtonElement>(raiz, "[data-ev=ver]");
  const botaoTocar = exigir<HTMLButtonElement>(raiz, "[data-ev=tocar]");
  const botaoAoVivo = exigir<HTMLButtonElement>(raiz, "[data-ev=ao-vivo]");

  let replay: ReturnType<typeof setInterval> | null = null;
  let buscando: AbortController | null = null;

  async function buscar(params: URLSearchParams): Promise<void> {
    buscando?.abort();
    const controller = new AbortController();
    buscando = controller;
    try {
      const resposta = await fetch(`${url}?${params}`, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
        signal: controller.signal,
      });
      if (!resposta.ok) {
        const corpo = await resposta.json().catch(() => ({}));
        const mensagem = corpo.detalhe ?? `erro ${resposta.status}`;
        metaAtual = {
          situacao: "erro",
          ultimaAtualizacao: null,
          ultimaTentativa: new Date(),
          falhasSeguidas: 1,
          proximoEmMs: 0,
          mensagemErro: mensagem,
        };
        renderizarMeta(alvos, metaAtual);
        renderizarAviso(alvos, null, { erro: mensagem });
        pararReplay();
        return;
      }
      metaAtual = {
        situacao: "ok",
        ultimaAtualizacao: new Date(),
        ultimaTentativa: new Date(),
        falhasSeguidas: 0,
        proximoEmMs: 0,
        mensagemErro: null,
      };
      store.receberDaApi((await resposta.json()) as Cena);
      renderizarMeta(alvos, metaAtual);
    } catch {
      if (!controller.signal.aborted) pararReplay();
    }
  }

  function pararReplay(): void {
    if (replay !== null) {
      clearInterval(replay);
      replay = null;
    }
    botaoTocar.textContent = "Tocar o dia";
  }

  function entrarEmPreview(): void {
    store.voltarAoVivo();
    poller.parar();
    renderizarContagem(alvos, 0);
  }

  botaoVer.addEventListener("click", () => {
    pararReplay();
    entrarEmPreview();
    const params = new URLSearchParams();
    if (campoData.value) params.set("data", campoData.value);
    if (campoHora.value) params.set("hora", campoHora.value);
    if (![...params.keys()].length) params.set("hora", "12:00");
    void buscar(params);
  });

  botaoTocar.addEventListener("click", () => {
    if (replay !== null) {
      pararReplay();
      return;
    }
    entrarEmPreview();
    botaoTocar.textContent = "Parar";

    let minutos = REPLAY_INICIO_MIN;
    const dia = campoData.value;
    const passo = () => {
      if (minutos > REPLAY_FIM_MIN) {
        pararReplay();
        return;
      }
      const params = new URLSearchParams({ hora: hhmm(minutos) });
      if (dia) params.set("data", dia);
      campoHora.value = hhmm(minutos);
      minutos += REPLAY_PASSO_MIN;
      void buscar(params);
    };
    passo();
    replay = setInterval(passo, REPLAY_INTERVALO_MS);
  });

  botaoAoVivo.addEventListener("click", () => {
    pararReplay();
    buscando?.abort();
    store.voltarAoVivo();
    campoHora.value = "";
    renderizarAviso(alvos, null);
    poller.iniciar();
    void poller.consultarAgora();
  });

  document.querySelector<HTMLButtonElement>("[data-ev=atualizar]")
    ?.addEventListener("click", () => {
      if (replay !== null) return;
      void poller.consultarAgora();
    });

  poller.iniciar();

  // Contagem regressiva: timer próprio, só de exibição (um só, não um por
  // personagem), e o poller não é consultado dentro do loop do Phaser.
  window.setInterval(() => renderizarContagem(alvos, poller.msAteProximo()), 500);
}

/**
 * Título, relógio (America/Sao_Paulo), indicador de som (inerte — sem áudio
 * implementado ainda) e tela cheia. Interface discreta: nada disso cobre o
 * cenário.
 */
function montarUiComplementar(raiz: HTMLElement, palco: HTMLElement): void {
  const relogio = raiz.querySelector<HTMLElement>("[data-ev=relogio]");
  if (relogio) {
    const atualizar = () => {
      relogio.textContent = new Date().toLocaleString("pt-BR", {
        timeZone: "America/Sao_Paulo",
        dateStyle: "short",
        timeStyle: "short",
      });
    };
    atualizar();
    window.setInterval(atualizar, 30_000);
  }

  const legenda = raiz.querySelector<HTMLElement>("[data-ev=legenda]");
  if (legenda) montarLegenda(legenda);

  const botaoSom = raiz.querySelector<HTMLButtonElement>("[data-ev=som]");
  if (botaoSom) {
    let ligado = false;
    botaoSom.setAttribute("aria-pressed", "false");
    botaoSom.addEventListener("click", () => {
      // Sem áudio implementado ainda (pedido explícito: som desabilitado
      // por padrão). O botão só guarda a preferência para quando existir.
      ligado = !ligado;
      botaoSom.setAttribute("aria-pressed", String(ligado));
      botaoSom.textContent = ligado ? "🔊" : "🔇";
      botaoSom.title = ligado ? "Som ligado (sem efeitos sonoros ainda)" : "Som desligado";
    });
  }

  const botaoTelaCheia = raiz.querySelector<HTMLButtonElement>("[data-ev=tela-cheia]");
  if (botaoTelaCheia) {
    if (!document.fullscreenEnabled) {
      botaoTelaCheia.hidden = true;
    } else {
      botaoTelaCheia.addEventListener("click", () => {
        if (document.fullscreenElement) {
          void document.exitFullscreen();
        } else {
          void palco.requestFullscreen().catch(() => {
            /* navegador recusou; sem tela cheia, sem quebrar o resto. */
          });
        }
      });
    }
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", iniciar);
} else {
  iniciar();
}
