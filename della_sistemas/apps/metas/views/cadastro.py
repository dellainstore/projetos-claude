from datetime import date

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.metas.models import Funcionario, MetaFuncionario, MetaCanal
from apps.metas.services.relatorio import MESES_PT


# ── Funcionários ───────────────────────────────────────────────────────────────

@perm_required("metas.cadastrar")
def view_funcionarios(request: HttpRequest) -> HttpResponse:
    funcionarios = Funcionario.objects.order_by("ativo", "-id")
    return render(request, "metas/cadastro/funcionarios.html", {
        "funcionarios": funcionarios,
    })


@perm_required("metas.cadastrar")
def view_funcionario_form(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    obj = get_object_or_404(Funcionario, pk=pk) if pk else None

    if request.method == "POST":
        nome = request.POST.get("nome", "").strip()
        nome_bling = request.POST.get("nome_bling", "").strip().upper()
        ativo = request.POST.get("ativo") == "on"

        if not nome or not nome_bling:
            messages.error(request, "Nome e Nome no Bling são obrigatórios.")
        elif (
            Funcionario.objects.filter(nome_bling=nome_bling)
            .exclude(pk=pk or 0)
            .exists()
        ):
            messages.error(request, f'Já existe uma funcionária com o nome Bling "{nome_bling}".')
        else:
            if obj:
                obj.nome = nome
                obj.nome_bling = nome_bling
                obj.ativo = ativo
                obj.save()
                messages.success(request, f'Funcionária "{nome}" atualizada.')
            else:
                Funcionario.objects.create(nome=nome, nome_bling=nome_bling, ativo=ativo)
                messages.success(request, f'Funcionária "{nome}" cadastrada.')
            return redirect("metas:cadastro_funcionarios")

    return render(request, "metas/cadastro/funcionario_form.html", {"obj": obj})


@perm_required("metas.cadastrar")
@require_POST
def view_funcionario_desativar(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Funcionario, pk=pk)
    obj.ativo = not obj.ativo
    obj.save()
    status = "ativada" if obj.ativo else "desativada"
    messages.success(request, f'Funcionária "{obj.nome}" {status}.')
    return redirect("metas:cadastro_funcionarios")


# ── Metas Individual ───────────────────────────────────────────────────────────

@perm_required("metas.cadastrar")
def view_metas_individual(request: HttpRequest) -> HttpResponse:
    hoje = date.today()
    try:
        ano = int(request.GET.get("ano", hoje.year))
        mes = int(request.GET.get("mes", hoje.month))
    except (ValueError, TypeError):
        ano, mes = hoje.year, hoje.month

    funcionarios = list(Funcionario.objects.filter(ativo=True).order_by("nome"))
    metas_existentes = {
        m.funcionario_id: m
        for m in MetaFuncionario.objects.filter(ano=ano, mes=mes)
    }

    if request.method == "POST":
        salvo = 0
        for func in funcionarios:
            raw = request.POST.get(f"meta_{func.id}", "").strip().replace(",", ".")
            if not raw:
                continue
            try:
                valor = float(raw)
                if valor < 0:
                    continue
            except ValueError:
                messages.error(request, f"Valor inválido para {func.nome}: {raw!r}")
                continue

            MetaFuncionario.objects.update_or_create(
                funcionario=func,
                ano=ano,
                mes=mes,
                defaults={"valor": valor},
            )
            salvo += 1

        if salvo:
            messages.success(request, f"{salvo} meta(s) salva(s) para {MESES_PT[mes]}/{ano}.")
        return redirect(f"{request.path}?ano={ano}&mes={mes}")

    # Montar lista para o template
    linhas = []
    for func in funcionarios:
        meta_obj = metas_existentes.get(func.id)
        linhas.append({
            "func": func,
            "valor_atual": meta_obj.valor if meta_obj else "",
        })

    return render(request, "metas/cadastro/metas_individual.html", {
        "linhas": linhas,
        "ano": ano,
        "mes": mes,
        "mes_nome": MESES_PT.get(mes, ""),
        "anos": list(range(2026, hoje.year + 2)),
        "meses": [(i, MESES_PT[i]) for i in range(1, 13)],
    })


# ── Metas Canal ────────────────────────────────────────────────────────────────

@perm_required("metas.cadastrar")
def view_metas_canal(request: HttpRequest) -> HttpResponse:
    hoje = date.today()
    try:
        ano = int(request.GET.get("ano", hoje.year))
        mes = int(request.GET.get("mes", hoje.month))
    except (ValueError, TypeError):
        ano, mes = hoje.year, hoje.month

    canais_config = MetaCanal.CANAL_CHOICES  # [("show_room_sp", "Show Room SP"), ...]

    metas_existentes = {
        m.canal: m for m in MetaCanal.objects.filter(ano=ano, mes=mes)
    }

    if request.method == "POST":
        salvo = 0
        for canal_key, canal_label in canais_config:
            raw = request.POST.get(f"meta_{canal_key}", "").strip().replace(",", ".")
            if not raw:
                MetaCanal.objects.filter(canal=canal_key, ano=ano, mes=mes).delete()
                continue
            try:
                valor = float(raw)
                if valor < 0:
                    continue
            except ValueError:
                messages.error(request, f"Valor inválido para {canal_label}: {raw!r}")
                continue

            MetaCanal.objects.update_or_create(
                canal=canal_key,
                ano=ano,
                mes=mes,
                defaults={"valor": valor},
            )
            salvo += 1

        messages.success(request, f"Metas de canal salvas para {MESES_PT[mes]}/{ano}.")
        return redirect(f"{request.path}?ano={ano}&mes={mes}")

    linhas = []
    for canal_key, canal_label in canais_config:
        meta_obj = metas_existentes.get(canal_key)
        linhas.append({
            "canal_key": canal_key,
            "canal_label": canal_label,
            "valor_atual": meta_obj.valor if meta_obj else "",
        })

    return render(request, "metas/cadastro/metas_canal.html", {
        "linhas": linhas,
        "ano": ano,
        "mes": mes,
        "mes_nome": MESES_PT.get(mes, ""),
        "anos": list(range(2026, hoje.year + 2)),
        "meses": [(i, MESES_PT[i]) for i in range(1, 13)],
    })
