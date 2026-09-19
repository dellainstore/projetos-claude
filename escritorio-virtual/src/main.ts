/**
 * Entrada do bundle. Liga o poller a pagina diagnostica.
 *
 * A configuracao (URL da API e intervalo) vem de data-attributes no HTML
 * servido pelo Django, nunca hardcoded aqui.
 */

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

  const animacoes = new ControleDeAnimacoes();
  let cenaAnterior: Cena | null = null;

  const poller = new Poller({
    url,
    intervaloMs,
    onCena: (cena, meta) => {
      // O servidor manda: a tela e' sempre reconstruida a partir da resposta.
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
