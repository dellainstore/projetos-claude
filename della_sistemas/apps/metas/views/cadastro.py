from datetime import date

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect

from apps.core.decorators import perm_required
from apps.metas.models import MetaFuncionario, MetaCanal
from apps.metas.services.relatorio import MESES_PT
from apps.rh.models import Colaborador


def _fmt_brl_input(valor) -> str:
    """Formata Decimal/float como string BRL sem símbolo para input: 50.000,00"""
    try:
        f = float(valor)
        if f == 0:
            return ""
        s = f"{f:,.2f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return ""


def _parse_brl_input(raw: str) -> str:
    """Converte valor digitado no formato BRL (50.000,00 ou 50000,00 ou 50000.00)
    para string com ponto decimal para conversão em float."""
    raw = raw.strip()
    if not raw:
        return ""
    if "," in raw and "." in raw:
        # Formato BRL: 50.000,00 → remove ponto de milhar, troca vírgula por ponto
        return raw.replace(".", "").replace(",", ".")
    if "," in raw:
        return raw.replace(",", ".")
    return raw


def _colaboradores_vendedores():
    """Vendedores com meta individual: ativos, com ID Bling e canal_meta_individual
    definido. Cris e outros sem canal fixo não aparecem aqui."""
    return list(
        Colaborador.objects.filter(
            ativo=True,
            bling_vendedor_id__isnull=False,
        ).exclude(canal_meta_individual="").order_by("nome")
    )


# ── Metas Individual ───────────────────────────────────────────────────────────

def _competencia_opcoes(hoje: date) -> list[tuple[str, str]]:
    """Opções do seletor unificado mês/ano: 'AAAA-MM' → 'Jun/2026'."""
    return [
        (f"{ano}-{mes:02d}", f"{MESES_PT[mes]}/{ano}")
        for ano in range(2026, hoje.year + 2)
        for mes in range(1, 13)
    ]


def _parse_competencia(request, hoje: date) -> tuple[int, int]:
    # Lê de POST (campos ocultos do form) e de GET (querystring/seletor). No POST
    # os campos ocultos garantem que salva no mês exibido, independente da URL.
    fonte = request.POST if request.method == "POST" else request.GET
    raw = fonte.get("competencia", "")
    if raw and "-" in raw:
        a, _, m = raw.partition("-")
        if a.isdigit() and m.isdigit():
            return int(a), int(m)
    try:
        return int(fonte.get("ano", hoje.year)), int(fonte.get("mes", hoje.month))
    except (ValueError, TypeError):
        return hoje.year, hoje.month


@perm_required("metas.cadastrar")
def view_metas_individual(request: HttpRequest) -> HttpResponse:
    hoje = date.today()
    ano, mes = _parse_competencia(request, hoje)

    colaboradores = _colaboradores_vendedores()
    metas_existentes = {
        m.colaborador_id: m
        for m in MetaFuncionario.objects.filter(ano=ano, mes=mes)
    }

    if request.method == "POST":
        salvo = 0
        for colab in colaboradores:
            raw = request.POST.get(f"meta_{colab.id}", "").strip()
            raw = _parse_brl_input(raw)
            if not raw:
                # Campo vazio: remove a meta do mês, se houver.
                MetaFuncionario.objects.filter(colaborador=colab, ano=ano, mes=mes).delete()
                continue
            try:
                valor = float(raw)
                if valor < 0:
                    continue
            except ValueError:
                messages.error(request, f"Valor inválido para {colab.nome}: {raw!r}")
                continue

            MetaFuncionario.objects.update_or_create(
                colaborador=colab,
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
    for colab in colaboradores:
        meta_obj = metas_existentes.get(colab.id)
        linhas.append({
            "func": colab,
            "valor_atual": _fmt_brl_input(meta_obj.valor) if meta_obj else "",
        })

    return render(request, "metas/cadastro/metas_individual.html", {
        "linhas": linhas,
        "ano": ano,
        "mes": mes,
        "mes_nome": MESES_PT.get(mes, ""),
        "competencia": f"{ano}-{mes:02d}",
        "meses_opcoes": _competencia_opcoes(hoje),
    })


# ── Metas Canal ────────────────────────────────────────────────────────────────

@perm_required("metas.cadastrar")
def view_metas_canal(request: HttpRequest) -> HttpResponse:
    from apps.metas.services.relatorio import (
        CANAIS_PUXAM_INDIVIDUAL,
        meta_individual_somada_por_canal,
        usa_metas_individuais,
    )

    hoje = date.today()
    ano, mes = _parse_competencia(request, hoje)

    canais_config = MetaCanal.CANAL_CHOICES  # [("show_room_sp", "Show Room SP"), ...]
    individual_mode = usa_metas_individuais(ano, mes)

    metas_existentes = {
        m.canal: m for m in MetaCanal.objects.filter(ano=ano, mes=mes)
    }

    if request.method == "POST":
        for canal_key, canal_label in canais_config:
            # Show Room e Anacã são automáticos (puxam das metas individuais): não
            # se salva à mão. Só Atacado e Site/Instagram são editáveis.
            if individual_mode and canal_key in CANAIS_PUXAM_INDIVIDUAL:
                continue
            raw = _parse_brl_input(request.POST.get(f"meta_{canal_key}", "").strip())
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

        messages.success(request, f"Metas de canal salvas para {MESES_PT[mes]}/{ano}.")
        return redirect(f"{request.path}?ano={ano}&mes={mes}")

    # Soma automática das metas individuais por loja (Show Room x Anacã).
    soma_individual = {"show_room_sp": 0, "anaca": 0}
    if individual_mode:
        colabs = _colaboradores_vendedores()
        metas_ind = list(MetaFuncionario.objects.filter(ano=ano, mes=mes))
        soma_individual = meta_individual_somada_por_canal(colabs, metas_ind)

    linhas = []
    for canal_key, canal_label in canais_config:
        auto = individual_mode and canal_key in CANAIS_PUXAM_INDIVIDUAL
        meta_obj = metas_existentes.get(canal_key)
        linhas.append({
            "canal_key": canal_key,
            "canal_label": canal_label,
            "auto": auto,
            "valor_auto": soma_individual.get(canal_key, 0) if auto else None,
            "valor_atual": _fmt_brl_input(meta_obj.valor) if meta_obj else "",
        })

    return render(request, "metas/cadastro/metas_canal.html", {
        "linhas": linhas,
        "ano": ano,
        "mes": mes,
        "mes_nome": MESES_PT.get(mes, ""),
        "competencia": f"{ano}-{mes:02d}",
        "meses_opcoes": _competencia_opcoes(hoje),
    })
