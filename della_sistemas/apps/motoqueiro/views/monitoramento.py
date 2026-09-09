from datetime import time as time_cls
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required

from ..models import MonitoramentoCotacao
from ..services import monitoramento as monitoramento_service


@perm_required("motoqueiro.monitorar")
def view_monitoramento(request: HttpRequest) -> HttpResponse:
    monitoramentos = MonitoramentoCotacao.objects.select_related("criado_por")[:100]
    ctx = {
        "monitoramentos": monitoramentos,
        "agora": timezone.now(),
    }
    return render(request, "motoqueiro/monitoramento.html", ctx)


@perm_required("motoqueiro.monitorar")
@require_POST
def view_criar(request: HttpRequest) -> HttpResponse:
    endereco_retirada = request.POST.get("endereco_retirada", "").strip()
    complemento_retirada = request.POST.get("complemento_retirada", "").strip()
    endereco_entrega = request.POST.get("endereco_entrega", "").strip()
    complemento_entrega = request.POST.get("complemento_entrega", "").strip()
    lat_retirada = request.POST.get("lat_retirada", "")
    lng_retirada = request.POST.get("lng_retirada", "")
    lat_entrega = request.POST.get("lat_entrega", "")
    lng_entrega = request.POST.get("lng_entrega", "")
    veiculo = request.POST.get("veiculo", MonitoramentoCotacao.VEICULO_QUALQUER)
    preco_alvo_raw = request.POST.get("preco_alvo", "").replace(",", ".").strip()
    parar_as_raw = request.POST.get("parar_as", "").strip()

    if not endereco_retirada or not endereco_entrega:
        messages.error(request, "Informe os dois endereços.")
        return redirect("motoqueiro:monitoramento")
    if not (lat_retirada and lng_retirada and lat_entrega and lng_entrega):
        messages.error(request, "Escolha o endereço na lista de sugestões que aparece enquanto você digita (clique em uma opção).")
        return redirect("motoqueiro:monitoramento")
    if veiculo not in dict(MonitoramentoCotacao.VEICULO_CHOICES):
        veiculo = MonitoramentoCotacao.VEICULO_QUALQUER

    try:
        preco_alvo = Decimal(preco_alvo_raw)
        if preco_alvo <= 0:
            raise InvalidOperation
    except (InvalidOperation, TypeError):
        messages.error(request, "Informe um preço-alvo válido, maior que zero.")
        return redirect("motoqueiro:monitoramento")

    # O <input type="time"> nunca deixa escolher outro dia — o horário
    # digitado é sempre combinado com a data de hoje. Se já passou (ex: são
    # 14h e a pessoa digitou 10h), recusa: não existe "amanhã às 10h" aqui,
    # o monitoramento sempre para no mesmo dia em que foi criado.
    try:
        hora, minuto = (int(p) for p in parar_as_raw.split(":")[:2])
        hora_limite = time_cls(hora, minuto)
    except (ValueError, TypeError):
        messages.error(request, "Informe até que horas (hoje) o monitoramento deve rodar.")
        return redirect("motoqueiro:monitoramento")

    agora = timezone.localtime()
    expira_em = agora.replace(hour=hora_limite.hour, minute=hora_limite.minute, second=0, microsecond=0)
    if expira_em <= agora:
        messages.error(request, "Esse horário já passou — escolha um horário ainda hoje, à frente do horário atual.")
        return redirect("motoqueiro:monitoramento")

    monitoramento_service.criar_monitoramento(
        criado_por=request.user,
        endereco_retirada=endereco_retirada, complemento_retirada=complemento_retirada,
        lat_retirada=float(lat_retirada), lng_retirada=float(lng_retirada),
        endereco_entrega=endereco_entrega, complemento_entrega=complemento_entrega,
        lat_entrega=float(lat_entrega), lng_entrega=float(lng_entrega),
        veiculo=veiculo, preco_alvo=preco_alvo, expira_em=expira_em,
    )
    messages.success(
        request,
        f"Monitoramento criado — avisamos no Telegram se achar até R$ {preco_alvo} "
        f"(ou quando parar sozinho às {hora_limite.strftime('%H:%M')} sem achar)."
    )
    return redirect("motoqueiro:monitoramento")


@perm_required("motoqueiro.monitorar")
@require_POST
def view_cancelar(request: HttpRequest, pk: int) -> HttpResponse:
    monitor = MonitoramentoCotacao.objects.filter(pk=pk, status=MonitoramentoCotacao.STATUS_ATIVO).first()
    if monitor:
        monitor.status = MonitoramentoCotacao.STATUS_CANCELADO
        monitor.cancelado_por = request.user
        monitor.save(update_fields=["status", "cancelado_por"])
        messages.success(request, "Monitoramento cancelado.")
    return redirect("motoqueiro:monitoramento")
