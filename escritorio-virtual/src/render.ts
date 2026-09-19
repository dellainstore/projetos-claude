/**
 * Renderizacao da pagina DIAGNOSTICA (fase 4).
 *
 * Nao e' o cenario: e' uma tabela ao vivo do que a API esta devolvendo,
 * usada para validar o poller e o contrato antes de existir mapa e sprite.
 * O Phaser entra numa fase seguinte consumindo o mesmo endpoint.
 */

import type { Cena, MetaPoll, Personagem, SituacaoConexao } from "./types";
import type { Transicao } from "./diff";

const ROTULO_ESTADO: Record<Personagem["estado"], string> = {
  OFFLINE: "Fora do ar",
  ARRIVING: "Chegando",
  WORKING: "Trabalhando",
  LUNCH: "Almoço",
  RETURNING_FROM_LUNCH: "Voltando do almoço",
  LEAVING: "Saindo",
  MISSING_PUNCH: "Batida faltando",
  DAY_OFF: "Sem expediente",
  AWAY: "Afastada no momento",
  ABSENT: "Não registrou ponto",
  OFF_SHIFT: "Expediente encerrado",
};

const ROTULO_LOJA: Record<Cena["loja"]["estado"], string> = {
  CLOSED: "Fechada",
  OPENING: "Abrindo",
  OPEN: "Aberta",
  OPEN_LUNCH_ONLY: "Aberta (todas no almoço)",
  CLOSED_WITH_PENDING: "Fechada com pendência",
};

const ROTULO_ORIGEM: Record<Personagem["salaOrigem"], string> = {
  loja: "loja da batida",
  sala_padrao: "sala padrão (fallback)",
  fallback: "entrada (fallback)",
  indefinida: "sem configuração",
};

const ROTULO_SITUACAO: Record<SituacaoConexao, string> = {
  conectando: "conectando",
  ok: "atualizado",
  "sem-mudanca": "sem mudança",
  erro: "erro",
  pausado: "pausado (aba oculta)",
};

function hhmm(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function texto(el: Element | null, valor: string): void {
  if (el) el.textContent = valor;
}

export interface Alvos {
  loja: HTMLElement;
  luzes: HTMLElement;
  pendencias: HTMLElement;
  data: HTMLElement;
  corpo: HTMLElement;
  situacao: HTMLElement;
  atualizadoEm: HTMLElement;
  contagem: HTMLElement;
  erro: HTMLElement;
  avisos: HTMLElement;
  log: HTMLElement;
}

export function renderizarCena(alvos: Alvos, cena: Cena, destacar: Set<number>): void {
  texto(alvos.loja, ROTULO_LOJA[cena.loja.estado] ?? cena.loja.estado);
  alvos.loja.dataset.estado = cena.loja.estado;
  texto(alvos.luzes, cena.loja.luzesAcesas ? "acesas" : "apagadas");
  texto(
    alvos.pendencias,
    cena.loja.pendencias === 0
      ? "nenhuma"
      : `${cena.loja.pendencias} registro(s) para conferir`,
  );
  texto(alvos.data, new Date(`${cena.data}T12:00:00`).toLocaleDateString("pt-BR"));

  texto(alvos.avisos, cena.avisos.length ? cena.avisos.join(", ") : "nenhum");

  alvos.corpo.replaceChildren();
  if (cena.personagens.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.className = "ev-vazio";
    td.textContent =
      "Nenhuma personagem configurada. Use manage.py escritorio_personagem.";
    tr.appendChild(td);
    alvos.corpo.appendChild(tr);
    return;
  }

  for (const p of cena.personagens) {
    const tr = document.createElement("tr");
    if (destacar.has(p.id)) tr.className = "ev-mudou";

    const celulas: Array<[string, string?]> = [
      [p.nome],
      [ROTULO_ESTADO[p.estado] ?? p.estado, p.estado],
      [p.sala ?? "fora de cena"],
      [ROTULO_ORIGEM[p.salaOrigem] ?? p.salaOrigem],
      [p.desde ? `desde ${hhmm(p.desde)}` : ""],
      [p.inconsistencia ? "conferir no ponto" : ""],
    ];

    for (const [valor, dado] of celulas) {
      const td = document.createElement("td");
      td.textContent = valor;
      if (dado) td.dataset.estado = dado;
      tr.appendChild(td);
    }
    alvos.corpo.appendChild(tr);
  }
}

export function renderizarMeta(alvos: Alvos, meta: MetaPoll): void {
  texto(alvos.situacao, ROTULO_SITUACAO[meta.situacao] ?? meta.situacao);
  alvos.situacao.dataset.situacao = meta.situacao;
  texto(
    alvos.atualizadoEm,
    meta.ultimaAtualizacao
      ? meta.ultimaAtualizacao.toLocaleTimeString("pt-BR")
      : "aguardando",
  );
  texto(alvos.erro, meta.mensagemErro ?? "");
  alvos.erro.hidden = !meta.mensagemErro;
}

export function renderizarContagem(alvos: Alvos, ms: number): void {
  texto(alvos.contagem, ms <= 0 ? "" : `próxima consulta em ${Math.ceil(ms / 1000)}s`);
}

export function registrarTransicoes(alvos: Alvos, transicoes: Transicao[]): void {
  for (const t of transicoes) {
    const linha = document.createElement("li");
    linha.textContent = `${new Date().toLocaleTimeString("pt-BR")} · ${t.evento} · ${t.eventId}`;
    alvos.log.prepend(linha);
  }
  while (alvos.log.childElementCount > 20) {
    alvos.log.lastElementChild?.remove();
  }
}
