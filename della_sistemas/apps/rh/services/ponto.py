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
    """Tipo da próxima batida do dia — o rótulo que aparece no botão ANTES de
    bater. None se o dia já está completo.

    Quando a escala tem horário definido pra esse dia, estima pelo horário
    ATUAL qual seria o melhor encaixe (mesma lógica de
    `reordenar_tipos_do_dia`, projetada pra antes de bater): perto do horário
    de saída, mesmo sem ter batido o almoço, já sugere "Saída" em vez de
    "Saída p/ almoço" só por ser a 2ª batida do dia. Sem escala pro dia (ou
    dia sem nenhum horário configurado) cai no comportamento antigo: pela
    posição."""
    batidas = list(_batidas_do_dia_qs(colaborador, dia))
    n = len(batidas)
    if n >= BATIDAS_POR_DIA:
        return None

    from apps.rh.services.escala import tempos_esperados_no_dia
    tempos = tempos_esperados_no_dia(colaborador, dia)
    if tempos:
        slots_disponiveis = [t for t in _ORDEM if tempos.get(t) is not None]
        if slots_disponiveis:
            if n >= len(slots_disponiveis):
                return None
            agora_min = _minutos_do_dia(timezone.localtime(timezone.now()).time())
            momentos_min = [_minutos_do_dia(timezone.localtime(b.momento).time()) for b in batidas] + [agora_min]
            esperados_min = [_minutos_do_dia(tempos[t]) for t in slots_disponiveis]
            indices = _melhor_encaixe(momentos_min, esperados_min)
            return slots_disponiveis[indices[-1]]

    return _ORDEM[n]


def _minutos_do_dia(t) -> int:
    return t.hour * 60 + t.minute


def _melhor_encaixe(momentos: list[int], esperados: list[int]) -> list[int]:
    """Casa `momentos` (minuto do dia de cada batida, em ordem cronológica) com
    `esperados` (minuto do dia de cada slot disponível, também em ordem),
    preservando a ordem — a i-ésima batida só pode ocupar um slot igual ou
    posterior ao da (i-1)-ésima — e minimizando a distância total em minutos.

    Programação dinâmica clássica de subsequência monótona de custo mínimo:
    `len(momentos)` batidas, `len(esperados)` slots (sempre poucos, ≤ 4),
    então roda instantâneo. Pressupõe `len(momentos) <= len(esperados)` (quem
    chama garante isso e cai pro fallback posicional quando não vale).

    Retorna os ÍNDICES dos slots escolhidos, um por batida, na mesma ordem de
    `momentos`."""
    m, k = len(momentos), len(esperados)
    inf = float("inf")
    # dp[i][j] = custo mínimo casando as i primeiras batidas usando só os j
    # primeiros slots como candidatos.
    dp = [[inf] * (k + 1) for _ in range(m + 1)]
    escolha: list[list[tuple | None]] = [[None] * (k + 1) for _ in range(m + 1)]
    for j in range(k + 1):
        dp[0][j] = 0
    for i in range(1, m + 1):
        for j in range(i, k + 1):
            melhor, origem = dp[i][j - 1], ("pular",)
            custo = dp[i - 1][j - 1] + abs(momentos[i - 1] - esperados[j - 1])
            if custo < melhor:
                melhor, origem = custo, ("casar", j - 1)
            dp[i][j] = melhor
            escolha[i][j] = origem

    slots_escolhidos: list[int] = [0] * m
    i, j = m, k
    while i > 0:
        acao, *resto = escolha[i][j]
        if acao == "casar":
            slots_escolhidos[i - 1] = resto[0]
            i -= 1
            j -= 1
        else:
            j -= 1
    return slots_escolhidos


def reordenar_tipos_do_dia(colaborador, dia: date) -> None:
    """Reatribui o `tipo` de todas as batidas do dia.

    Quando a escala tem horário definido pra esse dia, casa cada batida com o
    slot (entrada/saída almoço/volta almoço/saída) de horário esperado mais
    próximo, preservando a ordem cronológica — evita que uma saída sem bater
    o almoço (ex.: só entrada às 8h e saída às 19h) fique rotulada "saída p/
    almoço" só por ser a 2ª batida do dia, o que deixava a tela de aprovação
    confusa. Sem escala pro dia (feriado/folga sem jornada) ou mais batidas
    que slots disponíveis (caso atípico, bateu demais) → cai no comportamento
    antigo: tipo pela posição (1ª = entrada, 2ª = saída almoço, ...)."""
    batidas = list(_batidas_do_dia_qs(colaborador, dia))
    if not batidas:
        return

    tipos: list[str] | None = None
    from apps.rh.services.escala import tempos_esperados_no_dia
    tempos = tempos_esperados_no_dia(colaborador, dia)
    if tempos:
        slots_disponiveis = [t for t in _ORDEM if tempos.get(t) is not None]
        if 0 < len(batidas) <= len(slots_disponiveis):
            esperados_min = [_minutos_do_dia(tempos[t]) for t in slots_disponiveis]
            momentos_min = [_minutos_do_dia(timezone.localtime(b.momento).time()) for b in batidas]
            indices = _melhor_encaixe(momentos_min, esperados_min)
            tipos = [slots_disponiveis[idx] for idx in indices]

    if tipos is None:
        tipos = [_ORDEM[i] if i < BATIDAS_POR_DIA else _ORDEM[-1] for i in range(len(batidas))]

    for b, tipo in zip(batidas, tipos):
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
    # Dia abonado pelo gestor (faltou sem atestado, saída antecipada autorizada
    # etc.) → decisão manual já cobre a falta; não gera/mantém pendência de
    # correção mesmo com batida faltando ou ímpar.
    if AbonoPonto.objects.filter(colaborador=colaborador, data=dia).exists():
        return False
    # Dia justificado (férias, folga, atestado…) → não cobra ponto. Afastamento
    # parcial (por horas) só dispensa as batidas dentro do intervalo coberto —
    # o resto do dia continua sendo cobrado normalmente.
    from apps.rh.services.afastamentos import afastamento_no_dia, slots_dispensados_por_afastamento
    af = afastamento_no_dia(colaborador, dia)
    if af is not None and af.dia_inteiro:
        return False
    dispensados = slots_dispensados_por_afastamento(colaborador, dia, af) if af else set()

    from apps.rh.services.escala import horas_esperadas_no_dia
    esperado = horas_esperadas_no_dia(colaborador, dia)
    if esperado is None:
        esperado = colaborador.carga_horaria_diaria
    dia_util = bool(esperado and esperado > 0)

    n = _batidas_do_dia_qs(colaborador, dia).count()
    # Folga sem nenhuma batida → tudo bem, não cobra.
    if not dia_util and n == 0:
        return False
    # Nº ÍMPAR de batidas nunca fecha o dia — bater ponto sempre anda em pares
    # (entrada→saída, saída-almoço→volta-almoço). Um total ímpar significa que
    # falta a outra metade de algum par (ex.: bateu entrada e não bateu mais
    # nada, ou entrada+saída-almoço+volta e esqueceu a saída final), mesmo que
    # já tenha alcançado/superado `esperadas` — um afastamento parcial (ex.:
    # atestado só de manhã) reduz quantas batidas a escala cobra, mas não muda
    # a regra de que as que ela DE FATO bateu têm que fechar par.
    if n % 2 == 1:
        return True
    esperadas = BATIDAS_POR_DIA - len(dispensados)
    # Dia completo (todas as batidas esperadas, descontadas as dispensadas por
    # afastamento parcial) ou "sem almoço" aprovado (2 bastam) → ok.
    if n >= esperadas:
        return False
    from apps.rh.services.correcoes import sem_almoco_aprovado
    if sem_almoco_aprovado(colaborador, dia) and n >= min(2, esperadas):
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

    Retorna dict com 'dias' (lista por dia: data, batidas, horas, saldo — TODO
    dia do período, inclusive sábado/domingo/feriado/afastamento sem nenhuma
    batida, com saldo 0; o espelho de ponto (PDF) e o relatório mensal
    precisam do calendário completo, não só dos dias com batida) e
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
    # Só cobra dívida de dia sem batida (`sem_registro`) de quem realmente
    # bate ponto: precisa de `registra_ponto` E ao menos uma loja vinculada
    # (sem loja não tem onde bater — mesma regra de `dia_incompleto`). Um
    # colaborador com escala só "de cadastro" (ex.: admin sem vínculo de
    # loja) não deve acumular saldo negativo por nunca ter batido nada.
    pode_bater_ponto = colaborador.registra_ponto and colaborador.lojas_ponto.filter(ativo=True).exists()
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

    from apps.rh.services.afastamentos import afastamento_no_dia, horas_cobertas_por_afastamento

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
        # Afastamento parcial (por horas) só reduz a jornada esperada na fração
        # coberta — o restante do dia continua sujeito ao cálculo normal (dívida
        # se não bateu, extra se trabalhou além do esperado). Afastamento de dia
        # inteiro não mexe aqui: continua zerado por completo mais abaixo.
        if afastamento is not None and not afastamento.dia_inteiro and esperado is not None:
            esperado = max(esperado - horas_cobertas_por_afastamento(afastamento, esperado), Decimal("0"))
        # Dia útil sem NENHUMA batida (e sem afastamento de dia inteiro cobrindo o
        # dia): não é "falta uma batida" (esqueceu de bater a saída), é ausência
        # total — vira dívida no banco de horas (igual a um atraso do dia inteiro,
        # ou só da fração não coberta por um afastamento parcial) até o gestor
        # lançar atestado/afastamento (zera abaixo) ou preencher os horários reais
        # na Jornada (recalcula normal). Só se aplica a dias PASSADOS — hoje e o
        # futuro ainda podem ser batidos, não são dívida.
        sem_registro = (
            pode_bater_ponto
            and dia < hoje and n == 0 and not folga
            and (afastamento is None or not afastamento.dia_inteiro)
            and bool(esperado and esperado > 0)
        )

        # Fim de semana, folga da escala, sem escala definida ou já coberto por
        # um afastamento, sem nenhuma batida: não apura saldo (fica 0 abaixo),
        # mas o dia ainda entra em `dias` — o espelho de ponto (PDF) e o
        # relatório mensal precisam listar TODOS os dias do período, não só os
        # com batida (sábado/domingo/feriado/atestado têm que aparecer, com o
        # motivo na coluna OBS).
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
        # Só vale para afastamento de DIA INTEIRO — parcial já teve a fração
        # coberta descontada de `esperado` acima, então o saldo aqui já reflete
        # só a parte não coberta (não zera de novo).
        if afastamento is not None and afastamento.remunerado and afastamento.dia_inteiro:
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
            "n_batidas": n,
            "esperado_batidas": esperado_batidas,
            "completo": pareado and not parcial,
            "sem_registro": sem_registro,
            "abono": abono,
            "afastamento": afastamento,
            "feriado": dia in feriados(dia.year),
        })
        dia += timedelta(days=1)

    return {"dias": dias, "saldo_total": saldo_total.quantize(Decimal("0.01"))}


def dia_resolvido(d: dict) -> bool:
    """True quando o dia já foi decidido pelo gestor e não sobra nada pra
    corrigir — abono manual, ou afastamento de DIA INTEIRO (atestado, férias,
    folga, falta) cobrindo o dia todo. Nesses casos uma batida perdida/ímpar
    (ex.: um clique acidental num dia de atestado) não deve mais aparecer como
    pendência: o abono/afastamento já é a resposta final pro dia."""
    af = d.get("afastamento")
    return bool(d["abono"]) or (af is not None and af.dia_inteiro)


def obs_do_dia(d: dict) -> str:
    """Texto da coluna OBS do espelho de ponto/relatório a partir de um item de
    `banco_de_horas()['dias']`: feriado, afastamento (com horário se parcial),
    batida faltando, ausência sem registro, abono, folga — o que precisar de
    atenção de quem está conferindo. Dia da semana fica em coluna própria, não
    entra aqui."""
    partes: list[str] = []
    if d["feriado"]:
        partes.append("Feriado")
    af = d.get("afastamento")
    if af is not None:
        rotulo = af.get_tipo_display()
        if not af.dia_inteiro and af.hora_inicio and af.hora_fim:
            rotulo += f" ({af.hora_inicio:%H:%M}–{af.hora_fim:%H:%M})"
        if not af.remunerado:
            rotulo += " não remunerado"
        partes.append(rotulo)

    if d["abono"]:
        # Abono já é a palavra final sobre o dia — não mistura com "falta"/
        # "sem registro" (senão fica dizendo que falta algo que já foi decidido).
        partes.append(f"Abonado: {d['abono'].motivo}")
    elif not dia_resolvido(d):
        if d["sem_registro"]:
            partes.append("Sem registro — falta")
        elif d["batidas"] and not d["pareado"] and d["data"] < timezone.localdate():
            # Hoje ainda pode fechar o par mais tarde — só cobra de dia já
            # encerrado (ontem pra trás).
            partes.append("Falta batida")
        elif d["parcial"]:
            if d["n_batidas"] < d["esperado_batidas"]:
                partes.append("Não bateu o almoço")
            else:
                partes.append("Batidas extras no dia (mais que o esperado)")
    if not partes and d["folga"] and not d["batidas"]:
        partes.append("Folga")
    return " · ".join(partes)


def saldo_acumulado(colaborador, ate: date) -> Decimal:
    """Saldo do banco de horas acumulado desde o início do controle de ponto
    (`ParametrosPonto.data_inicio`) até `ate`, inclusive.

    Banco de horas não é pago (ver `ponto_relatorio.html`) — é compensado depois.
    Por isso o saldo de um mês tem que somar com o do mês seguinte, igual um
    extrato bancário: nunca reseta a zero na virada do mês. Os totais "do
    período/mês" continuam existindo nas telas (Jornada, Relatório) para dar o
    detalhe do que mudou naquela janela, mas o saldo que importa pro
    colaborador é este, acumulado."""
    inicio = ParametrosPonto.get().data_inicio
    if inicio > ate:
        return Decimal("0")
    return banco_de_horas(colaborador, inicio, ate)["saldo_total"]
