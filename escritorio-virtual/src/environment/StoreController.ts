/**
 * Traduz o estado da loja (vindo do backend) em decisoes visuais.
 *
 * Modulo PURO: nao toca em Phaser nem no DOM, so devolve o que a cena deve
 * mostrar. E' aqui que mora a regra "almoco nao e' fim de expediente" e
 * "ninguem trabalhando de madrugada", entao vale ter teste proprio.
 */

import type { Cena, EstadoLoja } from "../types";
import { comodosAcesos } from "./geometry";

export type EstadoPorta = "CLOSED" | "OPENING" | "OPEN" | "CLOSING";

export interface VisualDaLoja {
  estado: EstadoLoja;
  /** Comodos com a luz acesa (slugs). */
  acesos: Set<string>;
  porta: EstadoPorta;
  /** Texto da faixa, sem nome de ninguem. */
  rotulo: string;
  /** Quantidade de registros a conferir (so a visao autorizada usa). */
  pendencias: number;
  /** Alerta administrativo: nunca aparece na cena, so na interface. */
  alerta: boolean;
}

const ROTULO: Record<EstadoLoja, string> = {
  CLOSED: "Loja fechada",
  OPENING: "Abrindo a loja",
  OPEN: "Loja aberta",
  OPEN_LUNCH_ONLY: "Horário de almoço",
  CLOSED_WITH_PENDING: "Fechada · há registro para conferir",
};

/** Estados em que a loja conta como aberta. */
export const ABERTA: EstadoLoja[] = ["OPENING", "OPEN", "OPEN_LUNCH_ONLY"];

export function lojaAberta(estado: EstadoLoja): boolean {
  return ABERTA.includes(estado);
}

/**
 * Estado visual da porta de rua a partir do estado da loja e do anterior.
 *
 * `OPENING` e `CLOSING` sao TRANSICOES: so existem enquanto a porta se move.
 * Passar de fechada para aberta gera `OPENING`; o contrario, `CLOSING`.
 */
export function proximoEstadoDaPorta(
  anterior: EstadoPorta,
  cena: Cena,
): EstadoPorta {
  const querAberta = cena.loja.portaAberta || cena.loja.estado === "OPENING";
  const estavaAberta = anterior === "OPEN" || anterior === "OPENING";

  if (querAberta && !estavaAberta) return "OPENING";
  if (!querAberta && estavaAberta) return "CLOSING";
  if (querAberta) return "OPEN";
  return "CLOSED";
}

/** Estado final de uma transicao de porta (o que fica quando o tween acaba). */
export function repousoDaPorta(estado: EstadoPorta): EstadoPorta {
  if (estado === "OPENING") return "OPEN";
  if (estado === "CLOSING") return "CLOSED";
  return estado;
}

export function visualDaLoja(cena: Cena, portaAnterior: EstadoPorta): VisualDaLoja {
  const aberta = lojaAberta(cena.loja.estado);
  return {
    estado: cena.loja.estado,
    acesos: comodosAcesos(
      cena.salas, aberta, cena.personagens.map((p) => ({ sala: p.sala })),
    ),
    porta: proximoEstadoDaPorta(portaAnterior, cena),
    rotulo: ROTULO[cena.loja.estado] ?? cena.loja.estado,
    pendencias: cena.loja.pendencias,
    alerta: cena.loja.pendencias > 0,
  };
}
