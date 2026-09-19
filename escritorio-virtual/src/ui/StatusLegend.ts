/**
 * Legenda discreta dos estados possíveis, para quem está assistindo entender
 * as cores/rótulos sem precisar perguntar.
 */

const ITENS: Array<{ cor: string; rotulo: string }> = [
  { cor: "#5aa85c", rotulo: "Trabalhando" },
  { cor: "#e0a458", rotulo: "Almoço" },
  { cor: "#6f9bd1", rotulo: "Chegando/Saindo" },
  { cor: "#c2493f", rotulo: "Pendência no ponto" },
  { cor: "#8a8177", rotulo: "Fora do expediente" },
];

export function montarLegenda(container: HTMLElement): void {
  container.replaceChildren();
  for (const item of ITENS) {
    const el = document.createElement("span");
    el.className = "ev-legenda-item";
    const bolinha = document.createElement("i");
    bolinha.style.background = item.cor;
    el.append(bolinha, document.createTextNode(item.rotulo));
    container.appendChild(el);
  }
}
