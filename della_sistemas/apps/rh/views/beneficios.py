from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.decorators import perm_required
from apps.metas.services.relatorio import MESES_PT
from apps.rh.models import BeneficioVT, Colaborador, LancamentoBeneficio, TipoBeneficio
from apps.rh.services.beneficios import dias_vt_sugeridos
from apps.rh.services.utils import competencia_opcoes, parse_competencia, parse_decimal, parse_int


def _ensure_vt_tipo() -> TipoBeneficio:
    """Garante que o tipo Vale-Transporte exista (especial: tela dias × valor)."""
    tipo, _ = TipoBeneficio.objects.get_or_create(
        eh_vt=True, defaults={"nome": "Vale-Transporte", "sigla": "VT"},
    )
    return tipo


@perm_required("rh.gerir")
def view_beneficios(request: HttpRequest) -> HttpResponse:
    hoje = date.today()
    vt = _ensure_vt_tipo()
    tipos = list(TipoBeneficio.objects.filter(ativo=True))

    ano, mes = parse_competencia(request, hoje)
    tipo_id = parse_int(request.GET.get("tipo"), vt.id)
    tipo = next((t for t in tipos if t.id == tipo_id), vt)

    # POST de salvamento dos valores do mês.
    if request.method == "POST" and request.POST.get("_acao") == "salvar":
        if tipo.eh_vt:
            colabs = Colaborador.objects.filter(ativo=True, recebe_vt=True)
            for c in colabs:
                dias = parse_int(request.POST.get(f"dias_{c.id}"), -1)
                valor_dia = parse_decimal(request.POST.get(f"valor_{c.id}", ""), c.vt_valor_dia)
                if dias < 0:
                    continue
                BeneficioVT.objects.update_or_create(
                    colaborador=c, ano=ano, mes=mes,
                    defaults={"dias": dias, "valor_dia": valor_dia},
                )
        else:
            for c in Colaborador.objects.filter(ativo=True):
                valor = parse_decimal(request.POST.get(f"valor_{c.id}", ""), Decimal("0"))
                if valor and valor > 0:
                    LancamentoBeneficio.objects.update_or_create(
                        colaborador=c, tipo=tipo, ano=ano, mes=mes,
                        defaults={"valor": valor},
                    )
                else:
                    LancamentoBeneficio.objects.filter(
                        colaborador=c, tipo=tipo, ano=ano, mes=mes,
                    ).delete()
        messages.success(request, f"{tipo.nome} salvo para {MESES_PT[mes]}/{ano}.")
        return redirect(f"{reverse('rh:beneficios')}?competencia={ano}-{mes:02d}&tipo={tipo.id}")

    # Monta as linhas conforme o tipo selecionado.
    linhas = []
    total_geral = Decimal("0")
    if tipo.eh_vt:
        existentes = {b.colaborador_id: b for b in BeneficioVT.objects.filter(ano=ano, mes=mes)}
        for c in Colaborador.objects.filter(ativo=True, recebe_vt=True).order_by("nome"):
            b = existentes.get(c.id)
            dias = b.dias if b else dias_vt_sugeridos(c, ano, mes)
            valor_dia = b.valor_dia if b else c.vt_valor_dia
            total = (Decimal(dias) * valor_dia).quantize(Decimal("0.01"))
            total_geral += total
            linhas.append({
                "colaborador": c, "dias": dias, "valor_dia": valor_dia,
                "total": total, "sugerido": b is None,
            })
    else:
        existentes = {l.colaborador_id: l for l in LancamentoBeneficio.objects.filter(tipo=tipo, ano=ano, mes=mes)}
        for c in Colaborador.objects.filter(ativo=True).order_by("nome"):
            l = existentes.get(c.id)
            valor = l.valor if l else Decimal("0")
            total_geral += valor
            linhas.append({"colaborador": c, "valor": valor, "vinculado": l is not None})

    return render(request, "rh/beneficios.html", {
        "linhas": linhas,
        "total_geral": total_geral.quantize(Decimal("0.01")),
        "ano": ano,
        "mes": mes,
        "mes_nome": MESES_PT.get(mes, ""),
        "competencia": f"{ano}-{mes:02d}",
        "meses_opcoes": competencia_opcoes(hoje),
        "tipos": tipos,
        "tipo": tipo,
    })


@perm_required("rh.gerir")
def view_beneficio_tipo_novo(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        nome = (request.POST.get("nome") or "").strip()
        sigla = (request.POST.get("sigla") or "").strip()
        if not nome:
            messages.error(request, "Informe o nome do benefício.")
        elif TipoBeneficio.objects.filter(nome__iexact=nome).exists():
            messages.info(request, f"O benefício “{nome}” já existe.")
        else:
            TipoBeneficio.objects.create(nome=nome, sigla=sigla)
            messages.success(request, f"Benefício “{nome}” criado.")
    return redirect("rh:beneficios")


@perm_required("rh.gerir")
def view_beneficio_tipo_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    tipo = get_object_or_404(TipoBeneficio, pk=pk)
    if tipo.eh_vt:
        messages.error(request, "O Vale-Transporte não pode ser desativado.")
    else:
        tipo.ativo = not tipo.ativo
        tipo.save(update_fields=["ativo"])
        messages.success(request, f"Benefício “{tipo.nome}” {'ativado' if tipo.ativo else 'desativado'}.")
    return redirect("rh:beneficios")
