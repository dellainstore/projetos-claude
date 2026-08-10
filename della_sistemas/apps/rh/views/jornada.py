"""Jornada de Ponto (gestor): grid horizontal por dia, edição em massa e exclusão."""

import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.rh.models import AbonoPonto, BatidaPonto, Colaborador, LocalEmpresa
from apps.rh.services.afastamentos import dias_afastados
from apps.rh.services.calendario import feriados
from apps.rh.services.notificacoes import gerar_pendencias_do_dia
from apps.rh.services.ponto import banco_de_horas, formatar_horas_hm, obs_do_dia, saldo_acumulado
from apps.rh.services.utils import dia_semana_abrev, parse_int

# Colunas do grid: (tipo, prefixo do campo no form)
COLUNAS = [
    ("entrada", "e"),
    ("saida_almoco", "sa"),
    ("volta_almoco", "va"),
    ("saida", "s"),
]
_PREFIXO_POR_TIPO = {tipo: pref for tipo, pref in COLUNAS}


def _colaboradores_jornada(inativos: bool = False):
    """Ativos: escala + ponto ligado + vínculo com alguma loja (sem loja não bate
    ponto, não faz sentido aparecer). Inativos: perderam o vínculo (saíram, tiveram
    a loja/escala removida etc.) mas têm batidas no histórico — ficam disponíveis
    só para consulta/relatório, sem sumir do sistema."""
    ativos_qs = (
        Colaborador.objects.filter(ativo=True, registra_ponto=True, escala__isnull=False)
        .exclude(lojas_ponto__isnull=True)
        .distinct()
    )
    if not inativos:
        return list(ativos_qs.order_by("nome"))
    ids_ativos = set(ativos_qs.values_list("id", flat=True))
    return list(
        Colaborador.objects.filter(batidas__isnull=False)
        .exclude(id__in=ids_ativos)
        .distinct().order_by("nome")
    )


def _aware(d: date, t: time):
    return timezone.make_aware(datetime.combine(d, t))


def _parse_hora(valor: str) -> time | None:
    try:
        h, m = valor.split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def _periodo(request, hoje):
    """Resolve o período do filtro: mês (padrão) ou personalizado.

    Nunca deixa `inicio` cair antes de `ParametrosPonto.data_inicio` — não tem
    batida nem apuração antes disso (ver `dia_incompleto`/`banco_de_horas`),
    então não faz sentido o filtro oferecer ou aceitar um período anterior."""
    from apps.rh.models import ParametrosPonto
    inicio_controle = ParametrosPonto.get().data_inicio

    modo = request.GET.get("modo", "mes")
    if modo == "custom":
        try:
            inicio = date.fromisoformat(request.GET.get("inicio", ""))
            fim = date.fromisoformat(request.GET.get("fim", ""))
        except ValueError:
            inicio = fim = hoje
        if fim < inicio:
            inicio, fim = fim, inicio
        inicio = max(inicio, inicio_controle)
        fim = max(fim, inicio)
        # Limita a 62 dias para não montar um grid gigante.
        if (fim - inicio).days > 62:
            fim = inicio + timedelta(days=62)
        ano, mes = inicio.year, inicio.month
        return modo, inicio, fim, ano, mes
    from apps.rh.services.utils import parse_competencia
    ano, mes = parse_competencia(request, hoje)
    inicio = date(ano, mes, 1)
    if inicio < inicio_controle:
        ano, mes = inicio_controle.year, inicio_controle.month
        inicio = date(ano, mes, 1)
    elif inicio > date(hoje.year, hoje.month, 1):
        # Ainda não tem mês "ativo" na frente do atual (sem dado nenhum lá).
        ano, mes = hoje.year, hoje.month
        inicio = date(ano, mes, 1)
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
    return "mes", inicio, fim, ano, mes


def _mes_anterior_seguinte(ano: int, mes: int, inicio_controle: date, hoje: date) -> tuple[str | None, str | None]:
    """Competência ('AAAA-MM') do mês anterior/seguinte ao (ano, mes) dado, pra
    navegação por setinhas — None quando não há (já no primeiro mês do
    controle de ponto, ou ainda não chegou o próximo mês)."""
    anterior = None
    if (ano, mes) > (inicio_controle.year, inicio_controle.month):
        am, aa = (12, ano - 1) if mes == 1 else (mes - 1, ano)
        anterior = f"{aa}-{am:02d}"
    seguinte = None
    if (ano, mes) < (hoje.year, hoje.month):
        sm, sa = (1, ano + 1) if mes == 12 else (mes + 1, ano)
        seguinte = f"{sa}-{sm:02d}"
    return anterior, seguinte


def _dividir_por_mes(inicio: date, fim: date) -> list[tuple[date, date]]:
    """Quebra [inicio, fim] em pedaços por mês-calendário, pro espelho em PDF
    render uma página por mês (nunca amontoa 2 meses na mesma página)."""
    partes = []
    cursor = inicio
    while cursor <= fim:
        ultimo_dia_mes = calendar.monthrange(cursor.year, cursor.month)[1]
        fim_mes = min(date(cursor.year, cursor.month, ultimo_dia_mes), fim)
        partes.append((cursor, fim_mes))
        cursor = fim_mes + timedelta(days=1)
    return partes


def _voltar_qs(request, colaborador_id):
    modo = request.POST.get("modo", "mes")
    if modo == "custom":
        return (f"{reverse('rh:jornada')}?colaborador={colaborador_id}&modo=custom"
                f"&inicio={request.POST.get('inicio', '')}&fim={request.POST.get('fim', '')}")
    return (f"{reverse('rh:jornada')}?colaborador={colaborador_id}"
            f"&ano={request.POST.get('ano', '')}&mes={request.POST.get('mes', '')}")


@perm_required("rh.ponto_gerir")
def view_jornada(request: HttpRequest) -> HttpResponse:
    from apps.rh.models import ParametrosPonto
    hoje = timezone.localdate()
    inicio_controle = ParametrosPonto.get().data_inicio
    status = request.GET.get("status", "ativos")
    colaboradores = _colaboradores_jornada(inativos=(status == "inativos"))

    colab_id = parse_int(request.GET.get("colaborador"), 0)
    colaborador = next((c for c in colaboradores if c.id == colab_id), None)
    if colaborador is None and colaboradores:
        colaborador = colaboradores[0]

    modo, inicio, fim, ano, mes = _periodo(request, hoje)
    mes_anterior, mes_seguinte = _mes_anterior_seguinte(ano, mes, inicio_controle, hoje)

    from apps.metas.services.relatorio import MESES_PT
    linhas = []
    saldo_total = None
    saldo_periodo = None
    iso_dias = []
    lojas = []
    if colaborador:
        bh = banco_de_horas(colaborador, inicio, fim)
        banco = {d["data"]: d for d in bh["dias"]}
        # Saldo do banco de horas é acumulado (não reseta por mês) — o total em
        # destaque é o saldo real até o fim do período filtrado; o saldo "só
        # deste período" fica como detalhe complementar.
        saldo_periodo = bh["saldo_total"]
        saldo_total = saldo_acumulado(colaborador, fim)
        afast = dias_afastados(colaborador, inicio, fim)
        # Lojas disponíveis para o seletor manual: as do colaborador, ou todas ativas.
        lojas = list(colaborador.lojas_ponto.filter(ativo=True).order_by("nome"))
        if not lojas:
            lojas = list(LocalEmpresa.objects.filter(ativo=True).order_by("nome"))
        loja_padrao = lojas[0].id if len(lojas) == 1 else ""
        # Mapa de batidas por dia/tipo + loja predominante do dia.
        batidas = (
            BatidaPonto.objects.filter(colaborador=colaborador, momento__date__gte=inicio, momento__date__lte=fim)
        )
        por_dia_tipo: dict[tuple, BatidaPonto] = {}
        loja_do_dia: dict[date, int] = {}
        for b in batidas:
            d = timezone.localtime(b.momento).date()
            por_dia_tipo.setdefault((d, b.tipo), b)
            if b.loja_id and d not in loja_do_dia:
                loja_do_dia[d] = b.loja_id

        d = inicio
        while d <= fim:
            iso_dias.append(d.isoformat())
            slots = []
            for tipo, pref in COLUNAS:
                b = por_dia_tipo.get((d, tipo))
                hora = timezone.localtime(b.momento).strftime("%H:%M") if b else ""
                slots.append({"pref": pref, "hora": hora})
            info = banco.get(d, {})
            linhas.append({
                "data": d,
                "iso": d.isoformat(),
                "fds": d.weekday() >= 5,
                "fds_nome": "Sábado" if d.weekday() == 5 else ("Domingo" if d.weekday() == 6 else None),
                "feriado": d in feriados(d.year),
                "slots": slots,
                "loja_id": loja_do_dia.get(d, loja_padrao),
                "afastamento": afast.get(d),
                "horas": info.get("horas"),
                "saldo": info.get("saldo"),
                "folga": info.get("folga"),
                "pareado": info.get("pareado", True),
                "parcial": info.get("parcial"),
                "sem_registro": info.get("sem_registro"),
                "abono": info.get("abono"),
                "tem_batida": d in {dd for (dd, _t) in por_dia_tipo},
            })
            d += timedelta(days=1)

    return render(request, "rh/jornada.html", {
        "colaboradores": colaboradores,
        "colaborador": colaborador,
        "hoje": hoje,
        "linhas": linhas,
        "iso_dias": ",".join(iso_dias),
        "saldo_total": saldo_total,
        "saldo_periodo": saldo_periodo,
        "colunas": COLUNAS,
        "lojas": lojas,
        "modo": modo,
        "inicio": inicio,
        "fim": fim,
        "ano": ano,
        "mes": mes,
        "mes_nome": MESES_PT.get(mes, ""),
        "competencia": f"{ano}-{mes:02d}",
        "mes_anterior": mes_anterior,
        "mes_seguinte": mes_seguinte,
        "inicio_controle": inicio_controle,
        "status": status,
    })


@perm_required("rh.ponto_jornada_ver")
def view_minha_jornada(request: HttpRequest) -> HttpResponse:
    """Consulta (somente leitura) da própria jornada de ponto.

    Sempre travada no colaborador do usuário logado — NUNCA lê `colaborador`
    da query string, então não existe caminho pra ver o ponto de outra
    pessoa por aqui (diferente de `view_jornada`, que é do gestor e navega
    entre todos). Sem nenhuma ação de edição (salvar/excluir/abonar/PDF) —
    isso continua sendo só no gestor; correção de batida continua sendo só
    via 'Minhas Correções' (`rh:correcoes`)."""
    from apps.rh.models import ParametrosPonto
    colaborador = getattr(request.user, "colaborador", None)
    hoje = timezone.localdate()
    if colaborador is None:
        messages.error(request, "Seu usuário não está vinculado a um colaborador.")
        return render(request, "rh/minha_jornada.html", {"colaborador": None})

    # Jornada/saldo só fazem sentido pra quem de fato bate ponto (registra_ponto
    # + pelo menos uma loja vinculada, mesma regra de `dia_incompleto`/
    # `_colaboradores_jornada`). Sem isso, mostra aviso em vez de uma tabela
    # cheia de "sem registro" pra alguém que nunca teve como bater.
    tem_ponto = (
        colaborador.ativo and colaborador.registra_ponto
        and colaborador.lojas_ponto.filter(ativo=True).exists()
    )
    if not tem_ponto:
        return render(request, "rh/minha_jornada.html", {
            "colaborador": colaborador, "sem_vinculo_ponto": True,
        })

    inicio_controle = ParametrosPonto.get().data_inicio
    from apps.rh.services.utils import parse_competencia
    ano, mes = parse_competencia(request, hoje)
    inicio = date(ano, mes, 1)
    if inicio < inicio_controle:
        ano, mes = inicio_controle.year, inicio_controle.month
    elif inicio > date(hoje.year, hoje.month, 1):
        ano, mes = hoje.year, hoje.month
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
    mes_anterior, mes_seguinte = _mes_anterior_seguinte(ano, mes, inicio_controle, hoje)

    from apps.metas.services.relatorio import MESES_PT
    bh = banco_de_horas(colaborador, inicio, fim)
    dias = [
        {
            "info": d,
            "obs": obs_do_dia(d),
            "dia_semana": dia_semana_abrev(d["data"]),
            "batidas": {b.tipo: timezone.localtime(b.momento).strftime("%H:%M") for b in d["batidas"]},
        }
        for d in bh["dias"]
    ]

    return render(request, "rh/minha_jornada.html", {
        "colaborador": colaborador,
        "dias": dias,
        "hoje": hoje,
        "ano": ano,
        "mes": mes,
        "mes_nome": MESES_PT.get(mes, ""),
        "competencia": f"{ano}-{mes:02d}",
        "mes_anterior": mes_anterior,
        "mes_seguinte": mes_seguinte,
        "saldo_periodo": bh["saldo_total"],
        "saldo_acumulado_total": saldo_acumulado(colaborador, fim),
    })


@perm_required("rh.ponto_gerir")
@require_POST
def view_jornada_salvar(request: HttpRequest) -> HttpResponse:
    """Salva todo o grid de uma vez: cria/atualiza/exclui batidas conforme os campos."""
    colaborador = get_object_or_404(Colaborador, pk=parse_int(request.POST.get("colaborador"), 0))
    iso_dias = [s for s in request.POST.get("dias", "").split(",") if s]

    from apps.rh.services.afastamentos import afastamento_no_dia

    dias_tocados: set[date] = set()
    for iso in iso_dias:
        try:
            dia = date.fromisoformat(iso)
        except ValueError:
            continue
        # Dia com afastamento de DIA INTEIRO (folga, atestado, falta...) é
        # bloqueado no front-end (campos disabled) — reforça aqui: nunca
        # criar/alterar batida nesse dia, mesmo que o POST chegue preenchido.
        # Afastamento parcial (por horas) não bloqueia — o gestor pode lançar
        # normalmente as batidas do período não coberto.
        af = afastamento_no_dia(colaborador, dia)
        if af is not None and af.dia_inteiro:
            continue
        loja_raw = request.POST.get(f"loja_{iso}", "").strip()
        loja_id = int(loja_raw) if loja_raw.isdigit() else None
        for tipo, pref in COLUNAS:
            valor = request.POST.get(f"{pref}_{iso}", "").strip()
            hora = _parse_hora(valor) if valor else None
            existente = BatidaPonto.objects.filter(
                colaborador=colaborador, momento__date=dia, tipo=tipo
            ).first()
            if hora is None:
                if existente:
                    existente.delete()
                    dias_tocados.add(dia)
                continue
            momento = _aware(dia, hora)
            if existente:
                campos = []
                if existente.momento != momento:
                    existente.momento = momento
                    existente.origem = "manual"
                    existente.ajustado_por = request.user
                    campos += ["momento", "origem", "ajustado_por"]
                # Só define a loja em batida manual sem loja — não sobrescreve a
                # loja real de uma batida feita no app (mesmo em dias com 2 lojas).
                if loja_id and existente.loja_id is None:
                    existente.loja_id = loja_id
                    campos.append("loja")
                if campos:
                    existente.save(update_fields=campos)
                    dias_tocados.add(dia)
            else:
                BatidaPonto.objects.create(
                    colaborador=colaborador, momento=momento, tipo=tipo, loja_id=loja_id,
                    dentro_raio=True, origem="manual", ajustado_por=request.user,
                )
                dias_tocados.add(dia)

    for dia in dias_tocados:
        gerar_pendencias_do_dia(dia)
    messages.success(request, "Pontos salvos." if dias_tocados else "Nada a alterar.")
    return redirect(_voltar_qs(request, colaborador.id))


@perm_required("rh.ponto_gerir")
@require_POST
def view_dia_excluir(request: HttpRequest) -> HttpResponse:
    """Exclui todas as batidas de um dia."""
    colaborador = get_object_or_404(Colaborador, pk=parse_int(request.POST.get("colaborador"), 0))
    try:
        dia = date.fromisoformat(request.POST.get("data", ""))
    except ValueError:
        messages.error(request, "Data inválida.")
        return redirect(_voltar_qs(request, colaborador.id))
    n, _ = BatidaPonto.objects.filter(colaborador=colaborador, momento__date=dia).delete()
    # Limpa a pendência, a proposta de correção e um eventual abono do dia (saem
    # das Aprovações/Registros — não fazem mais sentido sem as batidas originais).
    from apps.rh.models import CorrecaoPonto, NotificacaoPonto
    CorrecaoPonto.objects.filter(colaborador=colaborador, data=dia, status="pendente").delete()
    NotificacaoPonto.objects.filter(colaborador=colaborador, data=dia).delete()
    AbonoPonto.objects.filter(colaborador=colaborador, data=dia).delete()
    messages.success(request, f"{n} batida(s) de {dia:%d/%m} excluída(s).")
    return redirect(_voltar_qs(request, colaborador.id))


@perm_required("rh.ponto_gerir")
@require_POST
def view_dia_abonar(request: HttpRequest) -> HttpResponse:
    """Abona o saldo (positivo ou negativo) de um dia: zera no banco de horas,
    registrando motivo e quem abonou. Não mexe nas batidas do dia."""
    colaborador = get_object_or_404(Colaborador, pk=parse_int(request.POST.get("colaborador"), 0))
    motivo = request.POST.get("motivo", "").strip()
    try:
        dia = date.fromisoformat(request.POST.get("data", ""))
    except ValueError:
        messages.error(request, "Data inválida.")
        return redirect(_voltar_qs(request, colaborador.id))
    if not motivo:
        messages.error(request, "Informe o motivo do abono.")
        return redirect(_voltar_qs(request, colaborador.id))

    bh = banco_de_horas(colaborador, dia, dia)
    info = bh["dias"][0] if bh["dias"] else None
    saldo_atual = info["saldo"] if info else Decimal("0")
    if not saldo_atual:
        messages.error(request, f"O dia {dia:%d/%m} não tem saldo a abonar.")
        return redirect(_voltar_qs(request, colaborador.id))

    AbonoPonto.objects.update_or_create(
        colaborador=colaborador, data=dia,
        defaults={"saldo_abonado": saldo_atual, "motivo": motivo, "abonado_por": request.user},
    )
    # Dia abonado não deve mais aparecer para a colaboradora corrigir — resolve
    # a pendência existente na hora, sem esperar o cron da meia-noite.
    gerar_pendencias_do_dia(dia)
    messages.success(request, f"Saldo de {dia:%d/%m} abonado.")
    return redirect(_voltar_qs(request, colaborador.id))


@perm_required("rh.ponto_gerir")
@require_POST
def view_dia_abono_excluir(request: HttpRequest) -> HttpResponse:
    """Remove o abono de um dia — o saldo volta a contar no banco de horas."""
    colaborador = get_object_or_404(Colaborador, pk=parse_int(request.POST.get("colaborador"), 0))
    try:
        dia = date.fromisoformat(request.POST.get("data", ""))
    except ValueError:
        messages.error(request, "Data inválida.")
        return redirect(_voltar_qs(request, colaborador.id))
    n, _ = AbonoPonto.objects.filter(colaborador=colaborador, data=dia).delete()
    if n:
        # Sem o abono, o dia volta a valer a regra normal — reabre a pendência
        # de correção se ainda faltar batida.
        gerar_pendencias_do_dia(dia)
        messages.success(request, f"Abono de {dia:%d/%m} removido.")
    return redirect(_voltar_qs(request, colaborador.id))


@perm_required("rh.ponto_gerir")
def view_jornada_pdf(request: HttpRequest) -> HttpResponse:
    """Espelho de ponto em PDF do período — de um colaborador ou de todos
    (ativos/inativos). Uma página por mês-calendário (nunca amontoa 2 meses
    juntos); se o período pedido cobrir mais de um mês, o colaborador ganha
    mais páginas, cada uma com sua própria tabela e saldo."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from apps.rh.services.ponto import dia_resolvido
    from apps.rh.services.utils import nome_exibicao

    hoje = timezone.localdate()
    status = request.GET.get("status", "ativos")
    disponiveis = _colaboradores_jornada(inativos=(status == "inativos"))

    todos = request.GET.get("todos") == "1"
    if todos:
        alvo = disponiveis
    else:
        colab_id = parse_int(request.GET.get("colaborador"), 0)
        colaborador = next((c for c in disponiveis if c.id == colab_id), None)
        alvo = [colaborador] if colaborador else []

    modo, inicio, fim, ano, mes = _periodo(request, hoje)

    buffer = io.BytesIO()
    # Margens bem enxutas pra caber o mês inteiro (até 31 linhas + cabeçalho +
    # resumo) numa página só, em vez de vazar pra uma 2ª página por pouco.
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), title="Espelho de Ponto",
        leftMargin=0.7 * cm, rightMargin=0.7 * cm, topMargin=0.6 * cm, bottomMargin=0.6 * cm,
    )
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle(
        "TituloEspelho", parent=styles["Title"], fontSize=12, leading=13, alignment=TA_CENTER,
        spaceAfter=1,
    )
    nome_style = ParagraphStyle(
        "NomeEspelho", parent=styles["Normal"], fontSize=10, leading=12,
        alignment=TA_CENTER, fontName="Helvetica-Bold",
    )
    periodo_style = ParagraphStyle(
        "PeriodoEspelho", parent=styles["Normal"], fontSize=7.5, leading=9,
        alignment=TA_CENTER, textColor=colors.HexColor("#666666"),
    )
    cel_style = ParagraphStyle(
        "CelEspelho", parent=styles["Normal"], fontSize=7.2, leading=8.4, alignment=TA_CENTER,
    )
    obs_style = ParagraphStyle("ObsEspelho", parent=cel_style, alignment=TA_LEFT)
    resumo_style = ParagraphStyle(
        "ResumoEspelho", parent=cel_style, alignment=TA_LEFT, fontName="Helvetica-Bold",
    )

    # Cores iguais às da tela (Jornada/app): azul = saldo positivo, vermelho =
    # negativo. Fundo da linha sinaliza o que precisa de atenção: vermelho
    # claro = falta batida/sem registro, azul claro = atestado/afastamento,
    # cinza = sábado/domingo/feriado (sempre destacado, batendo ponto ou não
    # nesse dia) — cinza em vez de dourado pra não confundir com o cabeçalho/
    # resumo da tabela, que já usam a cor dourada da marca.
    COR_POSITIVO = "#2563eb"
    COR_NEGATIVO = "#dc2626"
    BG_FALTA = colors.HexColor("#f7c6c6")
    BG_AFASTAMENTO = colors.HexColor("#c9dbfa")
    BG_FDS = colors.HexColor("#c7c7c7")
    BG_RESUMO = colors.HexColor("#efe1c4")
    BG_RESUMO_TOTAL = colors.HexColor("#e2cc98")

    cabecalho = [
        "Dia", "Dia sem.", "Entrada", "Saída\nalmoço", "Volta\nalmoço", "Saída",
        "Horas", "OBS", "Saldo",
    ]
    col_widths = [1.4 * cm, 1.3 * cm, 1.8 * cm, 1.9 * cm, 1.9 * cm, 1.8 * cm, 1.6 * cm, 8.5 * cm, 1.7 * cm]
    elementos = []

    if not alvo:
        elementos.append(Paragraph("Nenhum colaborador para gerar.", styles["Normal"]))

    primeira_pagina = True
    for c in alvo:
        for m_ini, m_fim in _dividir_por_mes(inicio, fim):
            if not primeira_pagina:
                elementos.append(PageBreak())
            primeira_pagina = False

            bh = banco_de_horas(c, m_ini, m_fim)
            elementos.append(Paragraph("Espelho de Ponto", titulo_style))
            elementos.append(Paragraph(nome_exibicao(c.nome), nome_style))
            elementos.append(Paragraph(
                f"Período: {m_ini:%d/%m/%Y} a {m_fim:%d/%m/%Y} (emitido em {hoje:%d/%m/%Y})", periodo_style,
            ))
            elementos.append(Spacer(1, 0.12 * cm))

            linhas = [cabecalho]
            linhas_destaque: list[tuple] = []  # comandos extra de BACKGROUND por linha
            for idx, d in enumerate(bh["dias"], start=1):
                por_tipo = {b.tipo: timezone.localtime(b.momento).strftime("%H:%M") for b in d["batidas"]}
                saldo = d["saldo"]
                cor_saldo = COR_NEGATIVO if saldo < 0 else (COR_POSITIVO if saldo > 0 else "#000000")
                saldo_cel = Paragraph(f'<font color="{cor_saldo}">{formatar_horas_hm(saldo)}</font>', cel_style)
                obs_txt = obs_do_dia(d)
                obs_cel = Paragraph(obs_txt, obs_style) if obs_txt else ""
                linhas.append([
                    d["data"].strftime("%d/%m"),
                    dia_semana_abrev(d["data"]),
                    por_tipo.get("entrada", ""),
                    por_tipo.get("saida_almoco", ""),
                    por_tipo.get("volta_almoco", ""),
                    por_tipo.get("saida", ""),
                    formatar_horas_hm(d["horas"]),
                    obs_cel,
                    saldo_cel,
                ])
                # Abonado ou coberto por afastamento de dia inteiro = já
                # resolvido, nunca pinta de vermelho mesmo com batida ímpar
                # perdida no meio (ex.: clique acidental num dia de atestado).
                # Hoje ainda pode fechar o par mais tarde, não conta como falta.
                resolvido = dia_resolvido(d)
                batida_faltando = not resolvido and (
                    d["sem_registro"] or (d["batidas"] and not d["pareado"] and d["data"] < hoje)
                )
                if batida_faltando:
                    linhas_destaque.append(("BACKGROUND", (0, idx), (-1, idx), BG_FALTA))
                elif d["afastamento"] is not None:
                    linhas_destaque.append(("BACKGROUND", (0, idx), (-1, idx), BG_AFASTAMENTO))
                elif d["data"].weekday() >= 5 or d["feriado"]:
                    linhas_destaque.append(("BACKGROUND", (0, idx), (-1, idx), BG_FDS))

            # Resumo embutido na própria tabela (não em parágrafos soltos
            # depois) — assim nunca sobra uma página só com essas duas linhas
            # quando a tabela de dias já lota a página anterior.
            idx_periodo = len(linhas)
            cor_periodo = (COR_NEGATIVO if bh["saldo_total"] < 0
                            else (COR_POSITIVO if bh["saldo_total"] > 0 else "#000000"))
            linhas.append([
                "Saldo do período", "", "", "", "", "", "", "",
                Paragraph(f'<font color="{cor_periodo}">{formatar_horas_hm(bh["saldo_total"])}</font>', resumo_style),
            ])
            idx_acumulado = len(linhas)
            saldo_acum = saldo_acumulado(c, m_fim)
            cor_acum = COR_NEGATIVO if saldo_acum < 0 else (COR_POSITIVO if saldo_acum > 0 else "#000000")
            linhas.append([
                f"Saldo acumulado do banco de horas até {m_fim:%d/%m/%Y}", "", "", "", "", "", "", "",
                Paragraph(f'<font color="{cor_acum}">{formatar_horas_hm(saldo_acum)}</font>', resumo_style),
            ])

            tabela = Table(linhas, repeatRows=1, colWidths=col_widths)
            tabela.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c9a96e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7.2),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("ALIGN", (7, 1), (7, -1), "LEFT"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#faf8f5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                *linhas_destaque,
                ("SPAN", (0, idx_periodo), (7, idx_periodo)),
                ("SPAN", (0, idx_acumulado), (7, idx_acumulado)),
                ("ALIGN", (0, idx_periodo), (7, idx_acumulado), "RIGHT"),
                ("LINEABOVE", (0, idx_periodo), (-1, idx_periodo), 0.8, colors.HexColor("#c9a96e")),
                ("BACKGROUND", (0, idx_periodo), (-1, idx_periodo), BG_RESUMO),
                ("BACKGROUND", (0, idx_acumulado), (-1, idx_acumulado), BG_RESUMO_TOTAL),
                ("TOPPADDING", (0, idx_periodo), (-1, idx_acumulado), 2.5),
                ("BOTTOMPADDING", (0, idx_periodo), (-1, idx_acumulado), 2.5),
            ]))
            elementos.append(tabela)

    doc.build(elementos)
    pdf = buffer.getvalue()
    buffer.close()
    resp = HttpResponse(pdf, content_type="application/pdf")
    nome_arquivo = "Todos" if todos else nome_exibicao(alvo[0].nome if alvo else "Ponto")
    resp["Content-Disposition"] = f'attachment; filename="Espelho de Ponto {nome_arquivo} ({hoje:%d-%m-%Y}).pdf"'
    return resp
