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

import { COR } from "./config/rooms";
import { hex } from "./config/characters";
import { BootScene } from "./scenes/BootScene";
import { CenaEscritorio } from "./scenes/OfficeScene";
import { ControleDeAnimacoes, estadosQueMudaram } from "./state/diff";
import { OfficeStore } from "./state/officeStore";
import { Poller } from "./state/poller";
import { DebugPanel, podeSimular } from "./ui/DebugPanel";
import {
  renderizarCena,
  renderizarContagem,
  renderizarMeta,
  renderizarModo,
  registrarTransicoes,
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

function montarJogo(destino: HTMLElement, store: OfficeStore): Phaser.Game {
  let cenaJogo: CenaEscritorio | null = null;

  const jogo = new Phaser.Game({
    type: Phaser.AUTO,
    parent: destino,
    width: 1532,
    height: 992,
    backgroundColor: hex(COR.foraDoPredio),
    banner: false,
    audio: { noAudio: true },
    scale: {
      // FIT mantem a proporcao da planta em qualquer tela: nada de comodo
      // esticado no celular nem entrada cortada.
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_HORIZONTALLY,
    },
    scene: [BootScene, CenaEscritorio],
  });

  // Uma unica assinatura: o store decide o que vale, a cena so reflete.
  store.assinar((cena) => {
    cenaJogo ??= jogo.scene.getScene("escritorio") as CenaEscritorio | null;
    cenaJogo?.aplicar(cena);
  });

  jogo.events.once("ready", () => {
    cenaJogo = jogo.scene.getScene("escritorio") as CenaEscritorio;
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
  };

  const store = new OfficeStore();
  montarJogo(exigir(raiz, "[data-ev=palco]"), store);

  const animacoes = new ControleDeAnimacoes();
  let cenaAnterior: Cena | null = null;
  let metaAtual: MetaPoll | null = null;

  const campoData = exigir<HTMLInputElement>(raiz, "[data-ev=campo-data]");
  const campoHora = exigir<HTMLInputElement>(raiz, "[data-ev=campo-hora]");

  // Painel de conferencia e log de transicoes seguem a MESMA cena da 2D.
  store.assinar((cena, origem) => {
    renderizarCena(alvos, cena, estadosQueMudaram(cenaAnterior, cena));
    registrarTransicoes(alvos, animacoes.novasTransicoes(cena));
    renderizarModo(alvos, cena, origem === "simulado");
    if (metaAtual) renderizarMeta(alvos, metaAtual);
    cenaAnterior = cena;

    const sugestao = cena.preview?.ultimoDiaComMovimento;
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
        metaAtual = {
          situacao: "erro",
          ultimaAtualizacao: null,
          ultimaTentativa: new Date(),
          falhasSeguidas: 1,
          proximoEmMs: 0,
          mensagemErro: corpo.detalhe ?? `erro ${resposta.status}`,
        };
        renderizarMeta(alvos, metaAtual);
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

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", iniciar);
} else {
  iniciar();
}
