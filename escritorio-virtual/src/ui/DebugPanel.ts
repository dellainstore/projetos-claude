/**
 * Painel de simulacao, para conferir animacao sem depender do relogio.
 *
 * O QUE ELE NAO FAZ, e nao pode fazer: criar batida, editar ponto, chamar
 * endpoint de escrita ou tocar no banco. Ele so transforma a cena que ja esta
 * na tela (`OfficeStore.simular`) — o servidor nem fica sabendo. Voltar para
 * "ao vivo" descarta a simulacao e a proxima resposta da API manda de novo.
 *
 * Quem pode ver: so quando o container da pagina trouxer
 * `data-debug="1"`, que o Django so emite para usuario com permissao de
 * configurar o escritorio. Nunca entra na visao publica (que nem existe
 * ainda).
 */

import type { OfficeStore } from "../state/officeStore";
import type { Cena, EstadoLoja, EstadoPersonagem, Personagem } from "../types";
import { SLUG } from "../config/rooms";

type Acao = (cena: Cena) => Cena;

/** Aplica uma mudanca a UMA personagem, preservando o resto da cena. */
function mexerNa(cena: Cena, id: number, mudanca: Partial<Personagem>): Cena {
  return {
    ...cena,
    personagens: cena.personagens.map((p) => (p.id === id ? { ...p, ...mudanca } : p)),
  };
}

function comLoja(cena: Cena, loja: Partial<Cena["loja"]>): Cena {
  return { ...cena, loja: { ...cena.loja, ...loja } };
}

/** Deduz a sala de trabalho da personagem a partir do proprio cadastro. */
function salaDeTrabalho(p: Personagem): string {
  return p.salaTrabalho ?? SLUG.SHOWROOM;
}

/**
 * Recalcula o estado da loja depois de mexer em alguem, para o painel nao
 * produzir combinacoes impossiveis (todo mundo no almoco com a loja fechada,
 * por exemplo).
 */
function reavaliarLoja(cena: Cena): Cena {
  const presentes = cena.personagens.filter(
    (p) => p.estado === "WORKING" || p.estado === "AWAY" || p.estado === "ARRIVING"
      || p.estado === "RETURNING_FROM_LUNCH" || p.estado === "LEAVING",
  );
  const almocando = cena.personagens.filter((p) => p.estado === "LUNCH");

  let estado: EstadoLoja = "CLOSED";
  if (presentes.length > 0) estado = "OPEN";
  else if (almocando.length > 0) estado = "OPEN_LUNCH_ONLY";

  const aberta = estado !== "CLOSED";
  return comLoja(cena, { estado, luzesAcesas: aberta, portaAberta: aberta });
}

function mudarEstado(id: number, estado: EstadoPersonagem, sala: string | null): Acao {
  return (cena) => {
    const alvo = cena.personagens.find((p) => p.id === id);
    if (!alvo) return cena;
    return reavaliarLoja(
      mexerNa(cena, id, { estado, estadoEstavel: estado, sala, evento: null }),
    );
  };
}

interface Botao {
  rotulo: string;
  acao: Acao | "ao-vivo";
  grupo: string;
}

function botoesDaPersonagem(p: Personagem): Botao[] {
  const trabalho = salaDeTrabalho(p);
  return [
    { grupo: p.nome, rotulo: "entrar", acao: mudarEstado(p.id, "ARRIVING", SLUG.ENTRADA) },
    { grupo: p.nome, rotulo: "trabalhar", acao: mudarEstado(p.id, "WORKING", trabalho) },
    { grupo: p.nome, rotulo: "almoço", acao: mudarEstado(p.id, "LUNCH", SLUG.REFEITORIO) },
    { grupo: p.nome, rotulo: "voltar", acao: mudarEstado(p.id, "RETURNING_FROM_LUNCH", trabalho) },
    { grupo: p.nome, rotulo: "sair", acao: mudarEstado(p.id, "LEAVING", SLUG.ENTRADA) },
    { grupo: p.nome, rotulo: "fora", acao: mudarEstado(p.id, "OFF_SHIFT", null) },
  ];
}

const BOTOES_DA_LOJA: Botao[] = [
  {
    grupo: "Loja", rotulo: "abrir",
    acao: (c) => comLoja(c, { estado: "OPEN", luzesAcesas: true, portaAberta: true }),
  },
  {
    grupo: "Loja", rotulo: "fechar",
    acao: (c) => ({
      ...comLoja(c, { estado: "CLOSED", luzesAcesas: false, portaAberta: false }),
      personagens: c.personagens.map((p) => ({
        ...p, estado: "OFF_SHIFT" as EstadoPersonagem,
        estadoEstavel: "OFF_SHIFT" as EstadoPersonagem, sala: null, evento: null,
      })),
    }),
  },
  { grupo: "Loja", rotulo: "apagar luzes", acao: (c) => comLoja(c, { luzesAcesas: false }) },
  { grupo: "Loja", rotulo: "acender luzes", acao: (c) => comLoja(c, { luzesAcesas: true }) },
  { grupo: "Loja", rotulo: "voltar ao vivo", acao: "ao-vivo" },
];

export class DebugPanel {
  private readonly raiz: HTMLElement;
  private desmontar: Array<() => void> = [];

  constructor(
    destino: HTMLElement,
    private readonly store: OfficeStore,
  ) {
    this.raiz = document.createElement("div");
    this.raiz.className = "ev-debug";
    this.raiz.hidden = true;
    destino.appendChild(this.raiz);
  }

  /** Redesenha os botoes a partir do elenco atual. */
  montar(): void {
    const cena = this.store.atual;
    this.raiz.replaceChildren();
    this.desmontar.forEach((fn) => fn());
    this.desmontar = [];

    if (!cena) {
      this.raiz.hidden = true;
      return;
    }
    this.raiz.hidden = false;

    const titulo = document.createElement("strong");
    titulo.textContent = "Simulação (não altera o ponto)";
    this.raiz.appendChild(titulo);

    const grupos = new Map<string, Botao[]>();
    for (const b of [...cena.personagens.flatMap(botoesDaPersonagem), ...BOTOES_DA_LOJA]) {
      const lista = grupos.get(b.grupo) ?? [];
      lista.push(b);
      grupos.set(b.grupo, lista);
    }

    for (const [nome, botoes] of grupos) {
      const linha = document.createElement("div");
      linha.className = "ev-debug-linha";

      const rotulo = document.createElement("span");
      rotulo.className = "ev-debug-nome";
      rotulo.textContent = nome;
      linha.appendChild(rotulo);

      for (const b of botoes) {
        const botao = document.createElement("button");
        botao.type = "button";
        botao.className = "ev-botao ev-botao-mini";
        botao.textContent = b.rotulo;
        const ouvinte = () => {
          if (b.acao === "ao-vivo") this.store.voltarAoVivo();
          else this.store.simular(b.acao);
        };
        botao.addEventListener("click", ouvinte);
        this.desmontar.push(() => botao.removeEventListener("click", ouvinte));
        linha.appendChild(botao);
      }
      this.raiz.appendChild(linha);
    }
  }

  destruir(): void {
    this.desmontar.forEach((fn) => fn());
    this.desmontar = [];
    this.raiz.remove();
  }
}

/** O painel so existe quando o servidor autorizou. */
export function podeSimular(raiz: HTMLElement): boolean {
  return raiz.dataset.debug === "1";
}
