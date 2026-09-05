from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required

from ..models import MovimentoSaldoLalamove


@perm_required("motoqueiro.gerir_saldo")
def view_saldo(request: HttpRequest) -> HttpResponse:
    movimentos = MovimentoSaldoLalamove.objects.select_related("lancado_por", "solicitacao")[:200]
    saldo = MovimentoSaldoLalamove.saldo_atual()
    ctx = {
        "saldo_atual": saldo,
        "saldo_lalamove": saldo,
        "movimentos": movimentos,
    }
    return render(request, "motoqueiro/saldo.html", ctx)


@perm_required("motoqueiro.gerir_saldo")
@require_POST
def view_saldo_lancar(request: HttpRequest) -> HttpResponse:
    tipo = request.POST.get("tipo", "")
    valor_raw = request.POST.get("valor", "").replace(",", ".").strip()
    descricao = request.POST.get("descricao", "").strip()

    if tipo not in dict(MovimentoSaldoLalamove.TIPO_CHOICES):
        messages.error(request, "Escolha se é crédito (incluí saldo) ou débito (saiu manualmente).")
        return redirect("motoqueiro:saldo")

    try:
        valor = Decimal(valor_raw)
        if valor <= 0:
            raise InvalidOperation
    except (InvalidOperation, TypeError):
        messages.error(request, "Informe um valor válido, maior que zero.")
        return redirect("motoqueiro:saldo")

    MovimentoSaldoLalamove.objects.create(
        tipo=tipo,
        origem=MovimentoSaldoLalamove.ORIGEM_MANUAL,
        valor=valor,
        descricao=descricao,
        lancado_por=request.user,
    )
    verbo = "Crédito de" if tipo == MovimentoSaldoLalamove.TIPO_CREDITO else "Débito de"
    messages.success(request, f"{verbo} R$ {valor} lançado. Novo saldo: R$ {MovimentoSaldoLalamove.saldo_atual()}.")
    return redirect("motoqueiro:saldo")
