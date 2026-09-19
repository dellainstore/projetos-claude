/**
 * Poller do escritorio virtual.
 *
 * Regras que este modulo garante (e que os testes cobrem):
 *
 * - UM unico timer. Sempre `setTimeout` reagendado, nunca `setInterval`, e
 *   sempre limpando o anterior antes de agendar o proximo.
 * - UMA unica requisicao em voo. Se um poll comeca com outro pendente, o
 *   anterior e' abortado (`AbortController`).
 * - `If-None-Match` com o ETag da ultima resposta 200. Um 304 nao reconstroi
 *   a tela: so atualiza o indicador de "conferido agora".
 * - Backoff exponencial em falha, com teto, voltando ao intervalo normal
 *   assim que uma resposta boa chega.
 * - Pausa completa quando `document.hidden`; ao voltar para a aba, consulta
 *   imediatamente em vez de esperar o ciclo.
 * - O estado do servidor SEMPRE prevalece: o cliente nunca deriva estado
 *   proprio a partir de evento, so renderiza o que veio.
 */

import type { Cena, MetaPoll } from "./types";

export interface OpcoesPoller {
  url: string;
  intervaloMs: number;
  /** Teto do backoff. Padrao: 5 minutos. */
  backoffMaximoMs?: number;
  onCena: (cena: Cena, meta: MetaPoll) => void;
  onSemMudanca: (meta: MetaPoll) => void;
  onErro: (mensagem: string, meta: MetaPoll) => void;
  onMeta?: (meta: MetaPoll) => void;
  /** Injetaveis para teste. */
  fetchImpl?: typeof fetch;
  doc?: Pick<Document, "hidden" | "addEventListener" | "removeEventListener">;
}

const BACKOFF_MAXIMO_PADRAO = 5 * 60 * 1000;

export class Poller {
  private readonly opcoes: Required<Pick<OpcoesPoller, "backoffMaximoMs">> & OpcoesPoller;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private controller: AbortController | null = null;
  private etag: string | null = null;
  private falhasSeguidas = 0;
  private rodando = false;
  private proximoEm: number | null = null;
  private meta: MetaPoll = {
    situacao: "conectando",
    ultimaAtualizacao: null,
    ultimaTentativa: null,
    falhasSeguidas: 0,
    proximoEmMs: 0,
    mensagemErro: null,
  };

  constructor(opcoes: OpcoesPoller) {
    this.opcoes = { backoffMaximoMs: BACKOFF_MAXIMO_PADRAO, ...opcoes };
    this.aoMudarVisibilidade = this.aoMudarVisibilidade.bind(this);
  }

  private get doc() {
    return this.opcoes.doc ?? document;
  }

  private get fetchImpl(): typeof fetch {
    return this.opcoes.fetchImpl ?? fetch.bind(globalThis);
  }

  iniciar(): void {
    if (this.rodando) return;
    this.rodando = true;
    this.doc.addEventListener("visibilitychange", this.aoMudarVisibilidade);
    void this.consultarAgora();
  }

  parar(): void {
    this.rodando = false;
    this.limparTimer();
    this.abortarEmVoo();
    this.doc.removeEventListener("visibilitychange", this.aoMudarVisibilidade);
  }

  /** Milissegundos ate o proximo poll (para a contagem regressiva da tela). */
  msAteProximo(agora: number = Date.now()): number {
    if (!this.rodando || this.proximoEm === null) return 0;
    return Math.max(0, this.proximoEm - agora);
  }

  /** Dispara um poll imediato, cancelando o agendamento pendente. */
  async consultarAgora(): Promise<void> {
    if (!this.rodando) return;
    this.limparTimer();
    await this.consultar();
  }

  // ── interno ────────────────────────────────────────────────────────────

  private aoMudarVisibilidade(): void {
    if (!this.rodando) return;
    if (this.doc.hidden) {
      // Aba escondida: para de consultar e solta a requisicao em voo.
      this.limparTimer();
      this.abortarEmVoo();
      this.proximoEm = null;
      this.atualizarMeta({ situacao: "pausado", proximoEmMs: 0 });
      return;
    }
    void this.consultarAgora();
  }

  private limparTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private abortarEmVoo(): void {
    if (this.controller !== null) {
      this.controller.abort();
      this.controller = null;
    }
  }

  private agendar(atrasoMs: number): void {
    this.limparTimer();
    if (!this.rodando || this.doc.hidden) {
      this.proximoEm = null;
      return;
    }
    this.proximoEm = Date.now() + atrasoMs;
    this.atualizarMeta({ proximoEmMs: atrasoMs });
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.consultar();
    }, atrasoMs);
  }

  private atrasoAtual(): number {
    if (this.falhasSeguidas === 0) return this.opcoes.intervaloMs;
    const fator = 2 ** Math.min(this.falhasSeguidas, 10);
    return Math.min(this.opcoes.intervaloMs * fator, this.opcoes.backoffMaximoMs);
  }

  private atualizarMeta(parcial: Partial<MetaPoll>): void {
    this.meta = { ...this.meta, ...parcial, falhasSeguidas: this.falhasSeguidas };
    this.opcoes.onMeta?.(this.meta);
  }

  private async consultar(): Promise<void> {
    if (!this.rodando || this.doc.hidden) return;

    // Uma requisicao por vez: a anterior perdeu a validade.
    this.abortarEmVoo();
    const controller = new AbortController();
    this.controller = controller;

    const cabecalhos: Record<string, string> = { Accept: "application/json" };
    if (this.etag) cabecalhos["If-None-Match"] = this.etag;

    this.atualizarMeta({ ultimaTentativa: new Date() });

    try {
      const resposta = await this.fetchImpl(this.opcoes.url, {
        method: "GET",
        headers: cabecalhos,
        credentials: "same-origin",
        signal: controller.signal,
      });

      if (this.controller !== controller) return; // superada por outra
      this.controller = null;

      if (resposta.status === 304) {
        this.falhasSeguidas = 0;
        this.atualizarMeta({ situacao: "sem-mudanca", mensagemErro: null });
        this.opcoes.onSemMudanca(this.meta);
        this.agendar(this.opcoes.intervaloMs);
        return;
      }

      if (!resposta.ok) {
        this.registrarFalha(this.mensagemDeStatus(resposta.status));
        return;
      }

      const cena = (await resposta.json()) as Cena;
      const etagNovo = resposta.headers.get("ETag");
      if (etagNovo) this.etag = etagNovo;

      this.falhasSeguidas = 0;
      this.atualizarMeta({
        situacao: "ok",
        ultimaAtualizacao: new Date(),
        mensagemErro: null,
      });
      this.opcoes.onCena(cena, this.meta);

      // O servidor pode mudar o intervalo (ParametrosEscritorio).
      if (cena.pollSegundos > 0) {
        this.opcoes.intervaloMs = cena.pollSegundos * 1000;
      }
      this.agendar(this.opcoes.intervaloMs);
    } catch (erro) {
      if (controller.signal.aborted) return; // cancelamento nosso, nao e' falha
      if (this.controller === controller) this.controller = null;
      this.registrarFalha(erro instanceof Error ? erro.message : "falha de rede");
    }
  }

  private mensagemDeStatus(status: number): string {
    if (status === 401) return "sessão expirada: faça login novamente";
    if (status === 403) return "sem permissão para ver o escritório";
    if (status === 404) return "escritório desativado";
    return `erro ${status} ao consultar o estado`;
  }

  private registrarFalha(mensagem: string): void {
    this.falhasSeguidas += 1;
    this.atualizarMeta({ situacao: "erro", mensagemErro: mensagem });
    this.opcoes.onErro(mensagem, this.meta);
    this.agendar(this.atrasoAtual());
  }
}
