"""Controle de ponto: geofence (haversine), ordenação das batidas e banco de horas."""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import asin, cos, radians, sin, sqrt

from django.utils import timezone

from apps.rh.models import AbonoPonto, BatidaPonto, LocalEmpresa, ParametrosPonto

# Ordem cronológica esperada das batidas no dia. O índice define o tipo:
# 1ª batida = entrada, 2ª = saída p/ almoço, 3ª = volta, 4ª = saída.
_ORDEM = ["entrada", "saida_almoco", "volta_almoco", "saida"]

# Nº de batidas que fecham um dia completo (entrada, almoço ida/volta, saída).
BATIDAS_POR_DIA = len(_ORDEM)


def distancia_metros(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em metros entre dois pontos (fórmula de Haversine)."""
    r = 6371000.0  # raio da Terra em metros
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _lojas_do_colaborador(colaborador) -> list[LocalEmpresa]:
    """Lojas ativas em que o colaborador pode bater. Sem vínculo → todas as ativas
    (compatibilidade: antes havia uma loja única)."""
    lojas = list(colaborador.lojas_ponto.filter(ativo=True))
    if not lojas:
        lojas = list(LocalEmpresa.objects.filter(ativo=True))
    return lojas


def validar_geofence(colaborador, lat: float, lon: float) -> tuple[bool, float | None, LocalEmpresa | None]:
    """Valida se (lat, lon) está dentro do raio de alguma loja do colaborador.

    Retorna (dentro_do_raio, distancia_m_da_mais_proxima, loja_mais_proxima).
    Se não há loja cadastrada/vinculada, retorna (False, None, None) e a batida
    deve ser recusada.
    """
    lojas = _lojas_do_colaborador(colaborador)
    if not lojas:
        return False, None, None
    melhor_dist: float | None = None
    melhor_loja: LocalEmpresa | None = None
    dentro = False
    for loja in lojas:
        dist = distancia_metros(lat, lon, float(loja.latitude), float(loja.longitude))
        if melhor_dist is None or dist < melhor_dist:
            melhor_dist, melhor_loja = dist, loja
        if dist <= loja.raio_metros:
            dentro = True
            melhor_dist, melhor_loja = dist, loja
            break
    return dentro, melhor_dist, melhor_loja


def _batidas_do_dia_qs(colaborador, dia: date):
    return BatidaPonto.objects.filter(colaborador=colaborador, momento__date=dia).order_by("momento")


def proximo_tipo(colaborador, dia: date) -> str | None:
    """Tipo da próxima batida do dia, pela ordem. None se o dia já está completo."""
    n = _batidas_do_dia_qs(colaborador, dia).count()
    return _ORDEM[n] if n < BATIDAS_POR_DIA else None


def reordenar_tipos_do_dia(colaborador, dia: date) -> None:
    """Reatribui o `tipo` de todas as batidas do dia pela ordem cronológica.

    Garante a invariante: a 1ª batida do dia é a entrada, a 2ª a saída p/ almoço,
    etc. — independentemente de como/quando foram incluídas (app ou manual)."""
    batidas = list(_batidas_do_dia_qs(colaborador, dia))
    for i, b in enumerate(batidas):
        tipo = _ORDEM[i] if i < BATIDAS_POR_DIA else _ORDEM[-1]
        if b.tipo != tipo:
            b.tipo = tipo
            b.save(update_fields=["tipo"])


def formatar_horas_hm(valor) -> str:
    """Converte horas decimais (ex.: 8.5) para 'H:MM' (ex.: '8:30'). Preserva o
    sinal em saldos negativos, com espaço entre o sinal e o horário. Usa o
    sinal de menos tipográfico (−, U+2212) em vez do hífen ASCII: o hífen fica
    fino demais perto de números e é facilmente confundido com um ponto
    (ex.: -1.5 → '− 1:30')."""
    if valor is None:
        valor = 0
    total_minutos = round(float(valor) * 60)
    sinal = "− " if total_minutos < 0 else ""
    total_minutos = abs(total_minutos)
    horas, minutos = divmod(total_minutos, 60)
    return f"{sinal}{horas:02d}:{minutos:02d}"


def tolerancia_minutos() -> Decimal:
    """Tolerância (em minutos) configurada nos parâmetros do ponto."""
    return Decimal(ParametrosPonto.get().tolerancia_minutos)


def dia_incompleto(colaborador, dia: date) -> bool:
    """True se o colaborador trabalha nesse dia mas ficou com menos batidas que o
    esperado (esqueceu de bater). Usado para gerar pendências/notificações."""
    if not colaborador.registra_ponto or not colaborador.ativo:
        return False
    # Sem loja vinculada → sem onde bater ponto, não cobra nem gera pendência.
    if not colaborador.lojas_ponto.filter(ativo=True).exists():
        return False
    # Sábado, domingo e feriado não têm horário de almoço fixo (normalmente só
    # entrada/saída) e não são cobrados pelo fluxo automático de correção — o
    # gestor confere manualmente pela Jornada, se precisar.
    from apps.rh.services.calendario import eh_dia_util
    if not eh_dia_util(dia):
        return False
    # Dia justificado (férias, folga, atestado…) → não cobra ponto.
    from apps.rh.services.afastamentos import afastamento_no_dia
    if afastamento_no_dia(colaborador, dia) is not None:
        return False

    from apps.rh.services.escala import horas_esperadas_no_dia
    esperado = horas_esperadas_no_dia(colaborador, dia)
    if esperado is None:
        esperado = colaborador.carga_horaria_diaria
    dia_util = bool(esperado and esperado > 0)

    n = _batidas_do_dia_qs(colaborador, dia).count()
    # Folga sem nenhuma batida → tudo bem, não cobra.
    if not dia_util and n == 0:
        return False
    # Dia completo (4 batidas) ou "sem almoço" aprovado (2 bastam) → ok.
    if n >= BATIDAS_POR_DIA:
        return False
    from apps.rh.services.correcoes import sem_almoco_aprovado
    if sem_almoco_aprovado(colaborador, dia) and n >= 2:
        return False
    # Dia útil incompleto, OU folga com batida parcial (começou a bater e não fechou).
    return True


def _horas_trabalhadas(batidas_do_dia: list[BatidaPonto]) -> Decimal:
    """Horas efetivamente trabalhadas no dia, somando pares entrada→saída.

    Modelo padrão de ponto: as batidas se alternam IN/OUT em ordem cronológica.
    A 1ª com a 2ª (manhã), a 3ª com a 4ª (tarde), etc. O intervalo entre um par e
    o próximo (almoço) NÃO conta. Funciona com almoço (4 batidas), sem almoço
    (2 batidas) e jornadas com mais paradas (6+). Batida ímpar solta é ignorada."""
    bs = sorted(batidas_do_dia, key=lambda x: x.momento)
    total = 0.0
    for i in range(0, len(bs) - 1, 2):
        ini, fim = bs[i].momento, bs[i + 1].momento
        if fim > ini:
            total += (fim - ini).total_seconds()
    return Decimal(str(round(total / 3600.0, 2)))


def banco_de_horas(colaborador, inicio: date, fim: date) -> dict:
    """Agrega o banco de horas do colaborador no período.

    Retorna dict com 'dias' (lista por dia: data, batidas, horas, saldo) e
    'saldo_total' (positivo = horas extras; negativo = a compensar)."""
    batidas = list(
        BatidaPonto.objects
        .filter(colaborador=colaborador, momento__date__gte=inicio, momento__date__lte=fim)
        .order_by("momento")
    )

    # Agrupa pelo dia LOCAL (não UTC) — uma batida às 21h em SP pertence ao mesmo
    # dia, não ao dia seguinte em UTC.
    por_dia: dict[date, list[BatidaPonto]] = {}
    for b in batidas:
        por_dia.setdefault(timezone.localtime(b.momento).date(), []).append(b)

    from apps.rh.services.calendario import feriados
    from apps.rh.services.escala import batidas_esperadas_no_dia, horas_esperadas_no_dia

    hoje = timezone.localdate()
    carga_fixa = colaborador.carga_horaria_diaria
    tolerancia = tolerancia_minutos()
    abonos = {
        a.data: a
        for a in AbonoPonto.objects.filter(
            colaborador=colaborador, data__gte=inicio, data__lte=fim,
        )
    }
    dias = []
    saldo_total = Decimal("0")
    def _aplica_tolerancia(saldo: Decimal) -> Decimal:
        # Carência: zera o saldo dentro de ±tolerância. Compara em minutos inteiros
        # para o limite ser exato apesar do arredondamento (0,01h ≈ 0,6 min).
        if (abs(saldo) * 60).to_integral_value(rounding=ROUND_HALF_UP) <= tolerancia:
            return Decimal("0")
        return saldo

    from apps.rh.services.afastamentos import afastamento_no_dia

    dia = inicio
    while dia <= fim:
        do_dia = por_dia.get(dia, [])
        n = len(do_dia)
        horas = _horas_trabalhadas(do_dia)
        # Par fechado = nº par de batidas (entrada→saída). Ímpar = falta uma batida.
        pareado = n >= 2 and n % 2 == 0
        # Quantas batidas a escala espera nesse dia: 4 (com almoço) ou 2 (dia
        # configurado sem almoço, ex.: sábado só entrada/saída). Sem escala ou
        # dia não previsto → cai no padrão de 4 (comportamento anterior).
        esperado_batidas = batidas_esperadas_no_dia(colaborador, dia) or BATIDAS_POR_DIA
        # "conferir" só faz sentido se o par fechado não bate com o que a escala
        # previu pra esse dia (ex.: 4 batidas num sábado de só 2, ou vice-versa)
        # — batida ímpar (falta uma) já é sinalizada separadamente por `pareado`.
        parcial = pareado and n != esperado_batidas

        # Horas esperadas pela escala: None = sem escala; 0 = folga (não trabalha
        # nesse dia); >0 = jornada do dia (8h na semana, 4h no sábado, etc.).
        esperado_escala = horas_esperadas_no_dia(colaborador, dia)
        tem_escala = esperado_escala is not None
        esperado = esperado_escala if tem_escala else carga_fixa

        # Feriado nunca é dia de trabalho esperado, mesmo que a escala normalmente
        # preveja jornada nesse dia da semana (ex.: quinta-feira que caiu feriado)
        # — trata como folga: sem batida não gera dívida, e se trabalhou, tudo
        # vira hora extra (mesma regra de domingo/folga da escala).
        folga = (tem_escala and esperado_escala <= 0) or dia in feriados(dia.year)
        afastamento = afastamento_no_dia(colaborador, dia)
        # Dia útil sem NENHUMA batida (e sem afastamento cobrindo o dia): não é
        # "falta uma batida" (esqueceu de bater a saída), é ausência total — vira
        # dívida integral no banco de horas (igual a um atraso do dia inteiro) até
        # o gestor lançar atestado/afastamento (zera abaixo) ou preencher os
        # horários reais na Jornada (recalcula normal). Só se aplica a dias
        # PASSADOS — hoje e o futuro ainda podem ser batidos, não são dívida.
        sem_registro = (
            dia < hoje and n == 0 and not folga and afastamento is None
            and bool(esperado and esperado > 0)
        )

        if n == 0 and not sem_registro:
            # Fim de semana, folga da escala, sem escala definida ou já coberto
            # por um afastamento — nada a apurar, nem aparece no banco/espelho.
            dia += timedelta(days=1)
            continue

        if sem_registro:
            saldo = Decimal("0") - esperado
        elif esperado is None and not folga:
            # Sem jornada definida (sócio, sem escala e sem carga) → sem banco.
            saldo = Decimal("0")
        elif not pareado:
            # Falta uma batida (nº ímpar) → não apura; vira pendência p/ correção.
            saldo = Decimal("0")
        elif folga:
            # Trabalhou em dia de folga (ex.: domingo) → tudo é hora extra.
            saldo = _aplica_tolerancia(horas)
        else:
            # Dia normal: saldo = horas trabalhadas − jornada esperada.
            # Positivo = horas extras; negativo = horas devidas.
            saldo = _aplica_tolerancia((horas - esperado).quantize(Decimal("0.01")))

        # Dia abonado (atestado, folga, falta remunerada...) nunca gera saldo,
        # positivo ou negativo — mesmo com batida parcial (ex.: bateu entrada e
        # foi ao médico). O período é pago; não deve virar hora extra nem devida.
        if afastamento is not None and afastamento.remunerado:
            saldo = Decimal("0")

        # Abono manual do gestor (saída antecipada autorizada, hora extra que não
        # deve contar, falta sem batida justificada de outra forma...) zera o
        # saldo do dia — decisão pontual, não muda o cálculo, só o resultado.
        abono = abonos.get(dia)
        if abono is not None:
            saldo = Decimal("0")

        saldo_total += saldo
        dias.append({
            "data": dia,
            "batidas": sorted(do_dia, key=lambda x: x.momento),
            "horas": horas,
            "saldo": saldo,
            "esperado": (esperado or Decimal("0")) if not folga else Decimal("0"),
            "folga": folga,
            "pareado": pareado,
            "parcial": parcial,
            "completo": pareado and not parcial,
            "sem_registro": sem_registro,
            "abono": abono,
        })
        dia += timedelta(days=1)

    return {"dias": dias, "saldo_total": saldo_total.quantize(Decimal("0.01"))}
