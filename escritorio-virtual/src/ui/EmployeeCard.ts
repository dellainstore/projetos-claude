/**
 * Cartao de detalhes exibido ao clicar numa funcionaria ou objeto.
 *
 * DOM (nao Phaser): fica mais simples de tornar acessivel, legivel e
 * responsivo (o card nunca ultrapassa a tela no celular, tem botao de
 * fechar explicito porque toque nao tem "clicar fora" natural em todo
 * dispositivo).
 *
 * So mostra o que ja vem no payload da API (nome, setor, estado, desde,
 * ultimo evento) — nada de dado que a API nao expoe (sem GPS, sem saldo,
 * sem tipo de afastamento).
 */

import type { Personagem } from "../types";

const ESTADO_LABEL: Record<Personagem["estado"], string> = {
  OFFLINE: "Ainda não chegou",
  ARRIVING: "Chegando",
  WORKING: "Trabalhando",
  LUNCH: "No almoço",
  RETURNING_FROM_LUNCH: "Voltando do almoço",
  LEAVING: "Saindo",
  MISSING_PUNCH: "Batida pendente de conferência",
  DAY_OFF: "Sem expediente hoje",
  AWAY: "Afastada no momento",
  ABSENT: "Não registrou ponto",
  OFF_SHIFT: "Expediente encerrado",
};

const SETOR_LABEL: Record<string, string> = {
  showroom: "Show Room",
  anaca: "Anacã",
  cafeteria: "Refeitório",
  "store-entrance": "Entrada",
  corredor: "Corredor",
};

function hhmm(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

export interface ObjectCardInfo {
  kind: "object";
  label: string;
}

export type CardInfo = { kind: "employee"; personagem: Personagem } | ObjectCardInfo;

export class EmployeeCard {
  private readonly el: HTMLElement;

  constructor(container: HTMLElement) {
    this.el = document.createElement("div");
    this.el.className = "ev-popup";
    this.el.hidden = true;
    container.appendChild(this.el);
  }

  show(info: CardInfo): void {
    this.el.replaceChildren();

    const fechar = document.createElement("button");
    fechar.type = "button";
    fechar.className = "ev-popup-fechar";
    fechar.setAttribute("aria-label", "Fechar");
    fechar.textContent = "×";
    fechar.addEventListener("click", () => this.hide());
    this.el.appendChild(fechar);

    if (info.kind === "object") {
      const titulo = document.createElement("strong");
      titulo.textContent = info.label;
      this.el.appendChild(titulo);
    } else {
      const p = info.personagem;
      const titulo = document.createElement("strong");
      titulo.textContent = p.nome;
      this.el.appendChild(titulo);

      const linhas: Array<[string, string | null]> = [
        ["Setor", SETOR_LABEL[p.salaTrabalho ?? ""] ?? p.salaTrabalho ?? "—"],
        ["Estado", ESTADO_LABEL[p.estado] ?? p.estado],
        ["Desde", hhmm(p.desde)],
      ];
      if (p.evento) {
        linhas.push(["Última batida", hhmm(p.evento.occurredAt)]);
      }
      for (const [rotulo, valor] of linhas) {
        if (!valor) continue;
        const linha = document.createElement("div");
        linha.className = "ev-card-linha";
        const r = document.createElement("span");
        r.className = "ev-card-rotulo";
        r.textContent = rotulo;
        const v = document.createElement("span");
        v.textContent = valor;
        linha.append(r, v);
        this.el.appendChild(linha);
      }
    }

    this.el.hidden = false;
  }

  hide(): void {
    this.el.hidden = true;
  }

  get isOpen(): boolean {
    return !this.el.hidden;
  }

  destroy(): void {
    this.el.remove();
  }
}
