/**
 * Contrato da API interna do escritorio virtual.
 *
 * Espelha `apps/escritorio_virtual/services/serializacao.py`. Se um campo
 * mudar la, muda aqui: o teste `test_api.py::ContratoDoPayloadTests` trava a
 * lista de campos do lado do servidor.
 */

export type EstadoPersonagem =
  | "OFFLINE"
  | "ARRIVING"
  | "WORKING"
  | "LUNCH"
  | "RETURNING_FROM_LUNCH"
  | "LEAVING"
  | "MISSING_PUNCH"
  | "DAY_OFF"
  | "AWAY"
  | "ABSENT"
  | "OFF_SHIFT";

export type EstadoLoja =
  | "CLOSED"
  | "OPENING"
  | "OPEN"
  | "OPEN_LUNCH_ONLY"
  | "CLOSED_WITH_PENDING";

export type OrigemSala = "loja" | "sala_padrao" | "fallback" | "indefinida";

export interface EventoRecente {
  eventId: string;
  event: "CLOCK_IN" | "LUNCH_END" | "CLOCK_OUT";
  occurredAt: string;
}

export interface Personagem {
  id: number;
  personagem: string;
  nome: string;
  tipoAtor: "HUMAN_EMPLOYEE" | "AI_AGENT" | "SYSTEM_ACTOR";
  estado: EstadoPersonagem;
  estadoEstavel: EstadoPersonagem;
  desde: string | null;
  sala: string | null;
  salaTrabalho: string | null;
  salaOrigem: OrigemSala;
  posX: number;
  posY: number;
  evento: EventoRecente | null;
  inconsistencia: string | null;
}

export interface Sala {
  slug: string;
  nome: string;
  ordem: number;
  pos_x: number;
  pos_y: number;
  largura: number;
  altura: number;
}

/** Pré-visualização de um instante passado (ver views/api.py). */
export interface Preview {
  ativo: boolean;
  data?: string;
  hora?: string | null;
  /**
   * Dia que a tela deve sugerir: o mais recente com MAIS gente de expediente
   * completo, não simplesmente o último com batida. Num dia em que ninguém
   * bateu almoço a cena fica igual das 9h às 19h, e a pré-visualização
   * parece quebrada.
   */
  diaSugerido?: string | null;
}

export interface Cena {
  preview: Preview;
  versao: number;
  data: string;
  geradoEm: string;
  pollSegundos: number;
  loja: {
    estado: EstadoLoja;
    luzesAcesas: boolean;
    portaAberta: boolean;
    pendencias: number;
  };
  salas: Sala[];
  personagens: Personagem[];
  avisos: string[];
}

/** Situacao do canal de atualizacao, para o indicador da tela. */
export type SituacaoConexao = "conectando" | "ok" | "sem-mudanca" | "erro" | "pausado";

export interface MetaPoll {
  situacao: SituacaoConexao;
  ultimaAtualizacao: Date | null;
  ultimaTentativa: Date | null;
  falhasSeguidas: number;
  proximoEmMs: number;
  mensagemErro: string | null;
}
