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
from apps.rh.services.ponto import banco_de_horas, formatar_horas_hm
from apps.rh.services.utils import competencia_opcoes, parse_int

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
    """Resolve o período do filtro: mês (padrão) ou personalizado."""
    modo = request.GET.get("modo", "mes")
    if modo == "custom":
        try:
            inicio = date.fromisoformat(request.GET.get("inicio", ""))
            fim = date.fromisoformat(request.GET.get("fim", ""))
        except ValueError:
            inicio = fim = hoje
        if fim < inicio:
            inicio, fim = fim, inicio
        # Limita a 62 dias para não montar um grid gigante.
        if (fim - inicio).days > 62:
            fim = inicio + timedelta(days=62)
        ano, mes = inicio.year, inicio.month
        return modo, inicio, fim, ano, mes
    from apps.rh.services.utils import parse_competencia
    ano, mes = parse_competencia(request, hoje)
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
    return "mes", inicio, fim, ano, mes


def _voltar_qs(request, colaborador_id):
    modo = request.POST.get("modo", "mes")
    if modo == "custom":
        return (f"{reverse('rh:jornada')}?colaborador={colaborador_id}&modo=custom"
                f"&inicio={request.POST.get('inicio', '')}&fim={request.POST.get('fim', '')}")
    return (f"{reverse('rh:jornada')}?colaborador={colaborador_id}"
            f"&ano={request.POST.get('ano', '')}&mes={request.POST.get('mes', '')}")


@perm_required("rh.ponto_gerir")
def view_jornada(request: HttpRequest) -> HttpResponse:
    hoje = timezone.localdate()
    status = request.GET.get("status", "ativos")
    colaboradores = _colaboradores_jornada(inativos=(status == "inativos"))

    colab_id = parse_int(request.GET.get("colaborador"), 0)
    colaborador = next((c for c in colaboradores if c.id == colab_id), None)
    if colaborador is None and colaboradores:
        colaborador = colaboradores[0]

    modo, inicio, fim, ano, mes = _periodo(request, hoje)

    from apps.metas.services.relatorio import MESES_PT
    linhas = []
    saldo_total = None
    iso_dias = []
    lojas = []
    if colaborador:
        bh = banco_de_horas(colaborador, inicio, fim)
        banco = {d["data"]: d for d in bh["dias"]}
        saldo_total = bh["saldo_total"]
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
        "colunas": COLUNAS,
        "lojas": lojas,
        "modo": modo,
        "inicio": inicio,
        "fim": fim,
        "ano": ano,
        "mes": mes,
        "mes_nome": MESES_PT.get(mes, ""),
        "competencia": f"{ano}-{mes:02d}",
        "meses_opcoes": competencia_opcoes(hoje),
        "status": status,
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
        # Dia com afastamento (folga, atestado, falta...) é bloqueado no
        # front-end (campos disabled) — reforça aqui: nunca criar/alterar
        # batida nesse dia, mesmo que o POST chegue preenchido.
        if afastamento_no_dia(colaborador, dia) is not None:
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
        messages.success(request, f"Abono de {dia:%d/%m} removido.")
    return redirect(_voltar_qs(request, colaborador.id))


@perm_required("rh.ponto_gerir")
def view_jornada_pdf(request: HttpRequest) -> HttpResponse:
    """Espelho de ponto em PDF do período — de um colaborador ou de todos (ativos/inativos)."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), title="Espelho de Ponto")
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle(
        "TituloEspelho", parent=styles["Title"], fontSize=15, leading=18, alignment=TA_CENTER,
    )
    nome_style = ParagraphStyle(
        "NomeEspelho", parent=styles["Normal"], fontSize=12, leading=15,
        alignment=TA_CENTER, fontName="Helvetica-Bold",
    )
    periodo_style = ParagraphStyle(
        "PeriodoEspelho", parent=styles["Normal"], fontSize=9, leading=12,
        alignment=TA_CENTER, textColor=colors.HexColor("#666666"),
    )
    saldo_style = ParagraphStyle(
        "SaldoEspelho", parent=styles["Heading3"], alignment=TA_CENTER,
    )
    cabecalho = ["Dia", "Entrada", "Saída almoço", "Volta almoço", "Saída", "Horas", "Saldo"]
    elementos = []

    if not alvo:
        elementos.append(Paragraph("Nenhum colaborador para gerar.", styles["Normal"]))

    for i, c in enumerate(alvo):
        if i > 0:
            elementos.append(PageBreak())
        bh = banco_de_horas(c, inicio, fim)
        elementos.append(Paragraph("Espelho de Ponto", titulo_style))
        elementos.append(Paragraph(nome_exibicao(c.nome), nome_style))
        elementos.append(Paragraph(
            f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} (emitido em {hoje:%d/%m/%Y})", periodo_style,
        ))
        elementos.append(Spacer(1, 0.4 * cm))
        linhas = [cabecalho]
        for d in bh["dias"]:
            por_tipo = {b.tipo: timezone.localtime(b.momento).strftime("%H:%M") for b in d["batidas"]}
            linhas.append([
                d["data"].strftime("%d/%m"),
                por_tipo.get("entrada", ""),
                por_tipo.get("saida_almoco", ""),
                por_tipo.get("volta_almoco", ""),
                por_tipo.get("saida", ""),
                formatar_horas_hm(d["horas"]),
                formatar_horas_hm(d["saldo"]),
            ])
        if len(linhas) == 1:
            elementos.append(Paragraph("Nenhuma batida no período.", styles["Normal"]))
        else:
            tabela = Table(linhas, repeatRows=1)
            tabela.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c9a96e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#faf8f5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            elementos.append(tabela)
        elementos.append(Spacer(1, 0.3 * cm))
        elementos.append(Paragraph(f"Saldo do período: {formatar_horas_hm(bh['saldo_total'])} h", saldo_style))

    doc.build(elementos)
    pdf = buffer.getvalue()
    buffer.close()
    resp = HttpResponse(pdf, content_type="application/pdf")
    nome_arquivo = "Todos" if todos else nome_exibicao(alvo[0].nome if alvo else "Ponto")
    resp["Content-Disposition"] = f'attachment; filename="Espelho de Ponto {nome_arquivo} ({hoje:%d-%m-%Y}).pdf"'
    return resp
