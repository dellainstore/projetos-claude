/**
 * Entrada do bundle. Liga o poller a cena 2D e ao painel de diagnostico.
 *
 * A configuracao (URL da API e intervalo) vem de data-attributes no HTML
 * servido pelo Django, nunca hardcoded aqui.
 *
 * Fluxo: poller -> `onCena` -> cena Phaser (visual) + painel (conferencia).
 * A cena nunca deriva estado proprio; ela so reflete a resposta do servidor.
 */

import Phaser from "phaser";

import { CENARIO, hex } from "./cena/paleta";
import { CenaEscritorio } from "./cena/escritorio";
import { ControleDeAnimacoes, estadosQueMudaram } from "./diff";
import { Poller } from "./poller";
import {
  renderizarCena,
  renderizarContagem,
  renderizarMeta,
  registrarTransicoes,
  type Alvos,
} from "./render";
import type { Cena } from "./types";

function exigir<T extends HTMLElement>(raiz: ParentNode, seletor: string): T {
  const el = raiz.querySelector<T>(seletor);
  if (!el) throw new Error(`elemento ausente no HTML: ${seletor}`);
  return el;
}

function montarJogo(destino: HTMLElement): {
  aplicar: (cena: Cena) => void;
} {
  let cenaJogo: CenaEscritorio | null = null;
  let ultima: Cena | null = null;

  const jogo = new Phaser.Game({
    type: Phaser.AUTO,
    parent: destino,
    width: 928,
    height: 496,
    backgroundColor: hex(CENARIO.fundo),
    banner: false,
    audio: { noAudio: true },
    scale: {
      mode: Phaser.Scale.FIT,
      autoCenter: Phaser.Scale.CENTER_HORIZONTALLY,
    },
    scene: [CenaEscritorio],
  });

  jogo.events.once("ready", () => {
    cenaJogo = jogo.scene.getScene("escritorio") as CenaEscritorio;
    if (ultima) cenaJogo.aplicar(ultima);
  });

  return {
    aplicar(cena: Cena) {
      ultima = cena;
      cenaJogo?.aplicar(cena);
    },
  };
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
  };

  const jogo = montarJogo(exigir(raiz, "[data-ev=palco]"));
  const animacoes = new ControleDeAnimacoes();
  let cenaAnterior: Cena | null = null;

  const poller = new Poller({
    url,
    intervaloMs,
    onCena: (cena, meta) => {
      // O servidor manda: cena e painel sao sempre reconstruidos a partir da
      // resposta, nunca de estado acumulado no cliente.
      jogo.aplicar(cena);
      const mudaram = estadosQueMudaram(cenaAnterior, cena);
      renderizarCena(alvos, cena, mudaram);
      registrarTransicoes(alvos, animacoes.novasTransicoes(cena));
      renderizarMeta(alvos, meta);
      cenaAnterior = cena;
    },
    onSemMudanca: (meta) => renderizarMeta(alvos, meta),
    onErro: (_mensagem, meta) => renderizarMeta(alvos, meta),
    onMeta: (meta) => renderizarMeta(alvos, meta),
  });

  poller.iniciar();

  // Contagem regressiva: timer proprio, so de exibicao, independente do poll.
  window.setInterval(() => renderizarContagem(alvos, poller.msAteProximo()), 500);

  // O botão fica no cabeçalho da página, fora do container de dados.
  const botao = document.querySelector<HTMLButtonElement>("[data-ev=atualizar]");
  botao?.addEventListener("click", () => void poller.consultarAgora());
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", iniciar);
} else {
  iniciar();
}
