"""Projeção do escritório virtual a partir do ponto.

**Somente leitura.** Nenhuma função deste módulo cria, altera ou apaga
qualquer registro, nem mesmo de parâmetros (por isso `ParametrosEscritorio`
é lido por `atual()` e `ParametrosPonto` por consulta direta, nunca por
`get_or_create`, que escreveria a partir de um GET de API).

Toda regra trabalhista é reaproveitada de `apps.rh.services`: escala,
feriados, afastamentos e a própria definição de "dia incompleto". Este
módulo não reimplementa nenhuma delas; só traduz o resultado em estados de
cena.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from apps.escritorio_virtual.models import (
    ParametrosEscritorio,
    PersonagemEscritorio,
    SalaEscritorio,
)
from apps.escritorio_virtual.services import salas as svc_salas
from apps.escritorio_virtual.services.eventos import (
    Evento,
    eventos_das_batidas,
    evento_recente,
)
from apps.rh.models import AbonoPonto, BatidaPonto, ParametrosPonto
from apps.rh.services.afastamentos import afastamento_no_dia
from apps.rh.services.calendario import feriados
from apps.rh.services.escala import horas_esperadas_no_dia, tempos_esperados_no_dia
from apps.rh.services.ponto import dia_incompleto


class EstadoPersonagem:
    """Estados da personagem. Os três de transição são EFÊMEROS: derivam da
    idade da última batida e nunca são persistidos."""

    OFFLINE              = "OFFLINE"
    ARRIVING             = "ARRIVING"               # efêmero
    WORKING              = "WORKING"
    LUNCH                = "LUNCH"
    RETURNING_FROM_LUNCH = "RETURNING_FROM_LUNCH"   # efêmero
    LEAVING              = "LEAVING"                # efêmero
    MISSING_PUNCH        = "MISSING_PUNCH"
    DAY_OFF              = "DAY_OFF"
    AWAY                 = "AWAY"
    ABSENT               = "ABSENT"
    OFF_SHIFT            = "OFF_SHIFT"


EFEMEROS = {
    EstadoPersonagem.ARRIVING,
    EstadoPersonagem.RETURNING_FROM_LUNCH,
    EstadoPersonagem.LEAVING,
}

# Estado estável -> estado efêmero quando há evento de transição recente.
_TRANSICAO_POR_EVENTO = {
    "CLOCK_IN": EstadoPersonagem.ARRIVING,
    "LUNCH_END": EstadoPersonagem.RETURNING_FROM_LUNCH,
    "CLOCK_OUT": EstadoPersonagem.LEAVING,
}

# Estado estável a partir do tipo da última batida do dia.
_ESTADO_POR_TIPO = {
    "entrada": EstadoPersonagem.WORKING,
    "saida_almoco": EstadoPersonagem.LUNCH,
    "volta_almoco": EstadoPersonagem.WORKING,
    "saida": EstadoPersonagem.OFF_SHIFT,
}


class EstadoLoja:
    CLOSED              = "CLOSED"
    OPENING             = "OPENING"                # efêmero
    OPEN                = "OPEN"
    OPEN_LUNCH_ONLY     = "OPEN_LUNCH_ONLY"
    CLOSED_WITH_PENDING = "CLOSED_WITH_PENDING"


# Estados que contam como "alguém na loja trabalhando".
_PRESENTES = {
    EstadoPersonagem.WORKING,
    EstadoPersonagem.AWAY,
    EstadoPersonagem.ARRIVING,
    EstadoPersonagem.RETURNING_FROM_LUNCH,
    EstadoPersonagem.LEAVING,
}

# Motivos técnicos (não expõem tipo de afastamento nem dado pessoal).
class Motivo:
    ATOR_NAO_HUMANO        = "ator_nao_humano"
    COLABORADOR_INATIVO    = "colaborador_inativo"
    AFASTAMENTO_DIA_INTEIRO = "afastamento_dia_inteiro"
    AFASTAMENTO_PARCIAL    = "afastamento_parcial"
    FERIADO                = "feriado"
    FOLGA_ESCALA           = "folga_escala"
    ANTES_DO_CONTROLE      = "antes_do_inicio_do_controle"
    DIA_FUTURO             = "dia_futuro"
    AGUARDANDO_ENTRADA     = "aguardando_entrada"
    SEM_JORNADA_PREVISTA   = "sem_jornada_prevista"
    SEM_REGISTRO           = "sem_registro_em_dia_previsto"
    BATIDA_FALTANDO        = "batida_faltando"
    DIA_ENCERRADO          = "dia_encerrado"
    ULTIMA_BATIDA          = "ultima_batida"
    DIA_RESOLVIDO          = "dia_resolvido_pelo_gestor"


@dataclass
class AtorProjetado:
    personagem: PersonagemEscritorio
    estado: str
    estado_estavel: str
    motivo: str
    desde: datetime | None
    sala: svc_salas.ResolucaoSala
    sala_trabalho: svc_salas.ResolucaoSala
    evento_recente: Evento | None
    eventos: list[Evento] = field(default_factory=list)
    inconsistencia: str | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def nome_exibicao(self) -> str:
        """Primeiro nome, capitalizado. O cadastro guarda o nome civil completo
        (`TINA MARIA DA COSTA DIAS`); a cena não precisa dele."""
        colab = self.personagem.colaborador
        if colab is None:
            return self.personagem.personagem.title()
        return (colab.nome or "").strip().split(" ")[0].title() or self.personagem.personagem


@dataclass
class Cena:
    data: date
    gerado_em: datetime
    estado_loja: str
    luzes_acesas: bool
    porta_aberta: bool
    atores: list[AtorProjetado]
    salas: list[SalaEscritorio]
    parametros: ParametrosEscritorio
    avisos: list[str] = field(default_factory=list)


# ── Helpers de leitura ───────────────────────────────────────────────────────

def _data_inicio_controle() -> date | None:
    """`ParametrosPonto.data_inicio` sem escrever no banco.

    `ParametrosPonto.get()` usa `get_or_create`; aqui a leitura precisa ser
    inerte, então consultamos direto e aceitamos a ausência."""
    p = ParametrosPonto.objects.filter(pk=1).first()
    return p.data_inicio if p else None


def _janela_fechamento(dia: date, params: ParametrosEscritorio, tempos: dict | None) -> datetime:
    """Instante em que a loja apaga as luzes e uma batida faltando vira
    `MISSING_PUNCH`.

    Com escala: saída prevista + `margem_fechamento_minutos`. Sem escala (ou
    dia de escala sem horário de saída): `hora_limite_absoluta`. O limite
    absoluto é fallback, não teto da margem."""
    if tempos and tempos.get("saida"):
        naive = datetime.combine(dia, tempos["saida"]) + timedelta(
            minutes=params.margem_fechamento_minutos
        )
    else:
        naive = datetime.combine(dia, params.hora_limite_absoluta)
    return timezone.make_aware(naive)


def _afastamento_cobre_agora(af, agora: datetime) -> bool:
    """True se um afastamento PARCIAL cobre o instante atual."""
    if af is None or af.dia_inteiro:
        return False
    if not af.hora_inicio or not af.hora_fim:
        return False
    hora = timezone.localtime(agora).time()
    return af.hora_inicio <= hora <= af.hora_fim


# ── Projeção de um ator ──────────────────────────────────────────────────────

def _estado_estavel_do_ator(
    personagem, dia, agora, batidas, contexto,
) -> tuple[str, str, datetime | None, str | None]:
    """Devolve (estado_estavel, motivo, desde, inconsistencia).

    Precedência, do mais forte para o mais fraco:
    1. ator sem fonte de estado (não humano ou colaborador inativo);
    2. dia fora da janela de controle do ponto ou no futuro;
    3. afastamento de dia inteiro, feriado ou folga da escala sem batida;
    4. dia já encerrado: pergunta a `dia_incompleto()` (regra oficial);
    5. dia em andamento: tipo da última batida, ou ausência de batida.
    """
    colaborador = personagem.colaborador
    if personagem.tipo_ator != PersonagemEscritorio.HUMAN_EMPLOYEE or colaborador is None:
        return EstadoPersonagem.OFFLINE, Motivo.ATOR_NAO_HUMANO, None, None
    if not colaborador.ativo or not colaborador.registra_ponto:
        return EstadoPersonagem.OFFLINE, Motivo.COLABORADOR_INATIVO, None, None

    hoje = contexto["hoje"]
    params = contexto["params"]
    data_inicio = contexto["data_inicio"]

    if dia > hoje:
        return EstadoPersonagem.OFFLINE, Motivo.DIA_FUTURO, None, None

    ultima = batidas[-1] if batidas else None
    desde = ultima.momento if ultima else None

    # Antes do início do controle o ponto não cobra nada — a cena também não
    # pode acusar ausência nem batida faltando.
    antes_do_controle = data_inicio is not None and dia < data_inicio

    tempos = tempos_esperados_no_dia(colaborador, dia)
    esperado = horas_esperadas_no_dia(colaborador, dia)
    eh_feriado = dia in feriados(dia.year)
    af = afastamento_no_dia(colaborador, dia)
    tem_abono = colaborador.pk in contexto["abonos_por_colaborador"].get(dia, set())

    # 3. Dia sem expediente previsto.
    if af is not None and af.dia_inteiro:
        return EstadoPersonagem.DAY_OFF, Motivo.AFASTAMENTO_DIA_INTEIRO, None, None
    if eh_feriado and not batidas:
        return EstadoPersonagem.DAY_OFF, Motivo.FERIADO, None, None
    if esperado is not None and esperado <= 0 and not batidas:
        return EstadoPersonagem.DAY_OFF, Motivo.FOLGA_ESCALA, None, None

    janela = _janela_fechamento(dia, params, tempos)
    dia_fechado = dia < hoje or agora > janela

    # 4. Dia encerrado: a autoridade sobre "faltou batida" é o próprio ponto.
    if dia_fechado:
        if antes_do_controle:
            estado = EstadoPersonagem.OFF_SHIFT if batidas else EstadoPersonagem.DAY_OFF
            return estado, Motivo.ANTES_DO_CONTROLE, desde, None
        if tem_abono:
            # Gestor já decidiu o dia (abono): nada a acusar.
            return EstadoPersonagem.DAY_OFF, Motivo.DIA_RESOLVIDO, None, None
        if dia_incompleto(colaborador, dia):
            if batidas:
                return (
                    EstadoPersonagem.MISSING_PUNCH, Motivo.BATIDA_FALTANDO, desde,
                    EstadoPersonagem.MISSING_PUNCH,
                )
            return (
                EstadoPersonagem.ABSENT, Motivo.SEM_REGISTRO, None,
                EstadoPersonagem.ABSENT,
            )
        if batidas:
            return EstadoPersonagem.OFF_SHIFT, Motivo.DIA_ENCERRADO, desde, None
        return EstadoPersonagem.DAY_OFF, Motivo.SEM_JORNADA_PREVISTA, None, None

    # 5. Dia em andamento.
    if not batidas:
        if esperado is None or esperado <= 0:
            # Sem jornada prevista: não dá para afirmar ausência.
            return EstadoPersonagem.OFFLINE, Motivo.SEM_JORNADA_PREVISTA, None, None
        if antes_do_controle:
            return EstadoPersonagem.OFFLINE, Motivo.ANTES_DO_CONTROLE, None, None
        entrada_prevista = (tempos or {}).get("entrada")
        if entrada_prevista is None:
            return EstadoPersonagem.OFFLINE, Motivo.AGUARDANDO_ENTRADA, None, None
        limite = timezone.make_aware(
            datetime.combine(dia, entrada_prevista)
        ) + timedelta(minutes=contexto["tolerancia_minutos"])
        if agora <= limite:
            return EstadoPersonagem.OFFLINE, Motivo.AGUARDANDO_ENTRADA, None, None
        return EstadoPersonagem.ABSENT, Motivo.SEM_REGISTRO, None, EstadoPersonagem.ABSENT

    estado = _ESTADO_POR_TIPO.get(ultima.tipo, EstadoPersonagem.WORKING)
    if estado == EstadoPersonagem.WORKING and _afastamento_cobre_agora(af, agora):
        return EstadoPersonagem.AWAY, Motivo.AFASTAMENTO_PARCIAL, desde, None
    return estado, Motivo.ULTIMA_BATIDA, desde, None


def projetar_ator(personagem, dia: date, agora: datetime, contexto: dict) -> AtorProjetado:
    batidas = contexto["batidas_por_colaborador"].get(personagem.colaborador_id, [])
    eventos = eventos_das_batidas(batidas)

    estado_estavel, motivo, desde, inconsistencia = _estado_estavel_do_ator(
        personagem, dia, agora, batidas, contexto,
    )

    # Transição efêmera: só quando o estado estável é compatível, para não
    # animar uma "chegada" de quem já está marcada como ausente/pendente.
    recente = evento_recente(eventos, agora, contexto["params"].evento_recente_segundos)
    estado = estado_estavel
    if recente is not None:
        candidato = _TRANSICAO_POR_EVENTO.get(recente.event)
        compativel = (
            (candidato == EstadoPersonagem.ARRIVING and estado_estavel == EstadoPersonagem.WORKING)
            or (candidato == EstadoPersonagem.RETURNING_FROM_LUNCH
                and estado_estavel == EstadoPersonagem.WORKING)
            or (candidato == EstadoPersonagem.LEAVING
                and estado_estavel == EstadoPersonagem.OFF_SHIFT)
        )
        if candidato and compativel:
            estado = candidato
        else:
            recente = None

    sala_trabalho = svc_salas.resolver_sala_trabalho(
        personagem, batidas, contexto["salas"], contexto["por_loja"],
    )
    sala = svc_salas.sala_da_cena(estado, sala_trabalho, contexto["salas"])

    avisos = [a for a in {sala_trabalho.aviso, sala.aviso} if a]
    return AtorProjetado(
        personagem=personagem,
        estado=estado,
        estado_estavel=estado_estavel,
        motivo=motivo,
        desde=desde,
        sala=sala,
        sala_trabalho=sala_trabalho,
        evento_recente=recente,
        eventos=eventos,
        inconsistencia=inconsistencia,
        avisos=avisos,
    )


# ── Projeção da cena ─────────────────────────────────────────────────────────

def _estado_da_loja(atores: list[AtorProjetado]) -> str:
    presentes = [a for a in atores if a.estado in _PRESENTES]
    almocando = [a for a in atores if a.estado == EstadoPersonagem.LUNCH]
    pendentes = [a for a in atores if a.estado == EstadoPersonagem.MISSING_PUNCH]

    if presentes:
        # Abertura: todo mundo que está presente acabou de chegar.
        chegando = [a for a in presentes if a.estado == EstadoPersonagem.ARRIVING]
        if chegando and len(chegando) == len(presentes) and not almocando:
            return EstadoLoja.OPENING
        return EstadoLoja.OPEN
    if almocando:
        # Todas no almoço não é loja encerrada: é pausa.
        return EstadoLoja.OPEN_LUNCH_ONLY
    if pendentes:
        return EstadoLoja.CLOSED_WITH_PENDING
    return EstadoLoja.CLOSED


def _agora_padrao(dia: date, hoje: date) -> datetime:
    """Instante de referência. Para um dia passado, o fim daquele dia — assim
    o diagnóstico mostra como a cena terminou, não como ela estaria agora."""
    if dia >= hoje:
        return timezone.now()
    return timezone.make_aware(datetime.combine(dia, time(23, 59, 59)))


def projetar_cena(
    dia: date | None = None,
    agora: datetime | None = None,
    colaborador_id: int | None = None,
) -> Cena:
    """Cena completa do dia. Não escreve nada."""
    hoje = timezone.localdate()
    dia = dia or hoje
    agora = agora or _agora_padrao(dia, hoje)

    salas = list(SalaEscritorio.objects.filter(ativo=True).select_related("loja"))
    por_loja = svc_salas.mapa_loja_para_sala(salas)

    personagens = (
        PersonagemEscritorio.objects.filter(ativo=True)
        .select_related("colaborador", "colaborador__escala", "sala_padrao", "sala_padrao__loja")
        .order_by("personagem")
    )
    if colaborador_id is not None:
        personagens = personagens.filter(colaborador_id=colaborador_id)
    personagens = list(personagens)

    ids = [p.colaborador_id for p in personagens if p.colaborador_id]
    batidas_por_colaborador: dict[int, list[BatidaPonto]] = {i: [] for i in ids}
    if ids:
        for b in (
            BatidaPonto.objects
            .filter(colaborador_id__in=ids, momento__date=dia)
            .select_related("loja")
            .order_by("momento")
        ):
            batidas_por_colaborador.setdefault(b.colaborador_id, []).append(b)

    abonos_por_colaborador: dict[date, set[int]] = {}
    if ids:
        for colab_id in AbonoPonto.objects.filter(
            colaborador_id__in=ids, data=dia,
        ).values_list("colaborador_id", flat=True):
            abonos_por_colaborador.setdefault(dia, set()).add(colab_id)

    parametros = ParametrosEscritorio.atual()
    parametros_ponto = ParametrosPonto.objects.filter(pk=1).first()
    contexto = {
        "hoje": hoje,
        "params": parametros,
        "salas": salas,
        "por_loja": por_loja,
        "batidas_por_colaborador": batidas_por_colaborador,
        "abonos_por_colaborador": abonos_por_colaborador,
        "data_inicio": _data_inicio_controle(),
        "tolerancia_minutos": parametros_ponto.tolerancia_minutos if parametros_ponto else 10,
    }

    atores = [projetar_ator(p, dia, agora, contexto) for p in personagens]
    estado_loja = _estado_da_loja(atores)

    avisos: list[str] = []
    if not salas:
        avisos.append("sem_salas_configuradas")
    for a in atores:
        for aviso in a.avisos:
            if aviso not in avisos:
                avisos.append(aviso)

    luzes = estado_loja in (EstadoLoja.OPENING, EstadoLoja.OPEN, EstadoLoja.OPEN_LUNCH_ONLY)
    return Cena(
        data=dia,
        gerado_em=agora,
        estado_loja=estado_loja,
        luzes_acesas=luzes,
        porta_aberta=luzes,
        atores=atores,
        salas=salas,
        parametros=parametros,
        avisos=avisos,
    )
