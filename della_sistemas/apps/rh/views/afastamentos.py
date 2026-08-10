"""Afastamentos: faltas, atestados e folgas + histórico com filtros.

Férias NÃO entram aqui — são lançadas no módulo Férias.
"""

from datetime import date, time, timedelta

from django.contrib import messages
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.rh.models import Afastamento, AfastamentoAnexo, Colaborador
from apps.rh.services.afastamentos import converter_anexo_para_webp
from apps.rh.services.utils import parse_int


def _parse_data(valor: str | None):
    """ISO 'AAAA-MM-DD' → date (ou None)."""
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _parse_hora(valor: str | None) -> time | None:
    try:
        h, m = valor.split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


@perm_required("rh.gerir")
def view_afastamentos(request: HttpRequest, editar_pk: int | None = None) -> HttpResponse:
    colaboradores = list(Colaborador.objects.filter(ativo=True).order_by("nome"))

    editando = None
    anexos_editando = []
    if editar_pk:
        editando = get_object_or_404(Afastamento.objects.select_related("colaborador"), pk=editar_pk)
        if editando.anexo:
            anexos_editando.append({
                "url": reverse("rh:afastamento_anexo", args=[editando.pk]),
                "label": "Anexo 1",
            })
        for i, anx in enumerate(editando.anexos.all(), start=len(anexos_editando) + 1):
            anexos_editando.append({
                "url": reverse("rh:afastamento_anexo_item", args=[anx.pk]),
                "label": f"Anexo {i}",
            })

    # Filtros do histórico.
    f_colab = parse_int(request.GET.get("colaborador"), 0)
    periodo = request.GET.get("periodo", "30")  # 7 | 30 | custom | tudo
    hoje = date.today()
    qs = Afastamento.objects.select_related("colaborador", "criado_por").all()
    if f_colab:
        qs = qs.filter(colaborador_id=f_colab)
    inicio = fim = None
    if periodo == "7":
        inicio = hoje - timedelta(days=7)
    elif periodo == "30":
        inicio = hoje - timedelta(days=30)
    elif periodo == "custom":
        inicio = _parse_data(request.GET.get("inicio"))
        fim = _parse_data(request.GET.get("fim"))
    if inicio:
        qs = qs.filter(data_fim__gte=inicio)
    if fim:
        qs = qs.filter(data_inicio__lte=fim)

    return render(request, "rh/afastamentos.html", {
        "colaboradores": colaboradores,
        "tipos": Afastamento.FORM_TIPO_CHOICES,
        "afastamentos": list(qs[:200]),
        "editando": editando,
        "anexos_editando": anexos_editando,
        "f_colab": f_colab,
        "periodo": periodo,
        "inicio": request.GET.get("inicio", ""),
        "fim": request.GET.get("fim", ""),
    })


@perm_required("rh.gerir")
def view_afastamento_editar(request: HttpRequest, pk: int) -> HttpResponse:
    return view_afastamentos(request, editar_pk=pk)


def _ler_form(request) -> tuple:
    """Lê e valida os campos comuns.

    Retorna (colaborador, tipo, di, df, dia_inteiro, hora_inicio, hora_fim, erro)."""
    colaborador = Colaborador.objects.filter(pk=parse_int(request.POST.get("colaborador"), 0)).first()
    tipo = request.POST.get("tipo", "")
    di = _parse_data(request.POST.get("data_inicio"))
    df = _parse_data(request.POST.get("data_fim")) or di
    if colaborador is None or tipo not in dict(Afastamento.FORM_TIPO_CHOICES) or di is None:
        return None, None, None, None, None, None, None, "Informe colaborador, tipo e a data do afastamento."
    if df < di:
        di, df = df, di

    dia_inteiro = request.POST.get("cobertura", "dia") != "horas"
    hora_inicio = hora_fim = None
    if not dia_inteiro:
        hora_inicio = _parse_hora(request.POST.get("hora_inicio"))
        hora_fim = _parse_hora(request.POST.get("hora_fim"))
        if not hora_inicio or not hora_fim or hora_fim <= hora_inicio:
            return None, None, None, None, None, None, None, \
                "Para afastamento por horas, informe início e fim, com o fim depois do início."

    return colaborador, tipo, di, df, dia_inteiro, hora_inicio, hora_fim, None


def _salvar_anexos(af: Afastamento, arquivos) -> None:
    """Converte e salva cada arquivo enviado como um AfastamentoAnexo do afastamento
    (permite mais de uma foto no mesmo lançamento — ex.: atestado de 2 dias)."""
    for arquivo in arquivos:
        conteudo, nome = converter_anexo_para_webp(arquivo)
        anexo = AfastamentoAnexo(afastamento=af)
        anexo.arquivo.save(nome, conteudo, save=True)


@perm_required("rh.gerir")
@require_POST
def view_afastamento_novo(request: HttpRequest) -> HttpResponse:
    colaborador, tipo, di, df, dia_inteiro, hora_inicio, hora_fim, erro = _ler_form(request)
    if erro:
        messages.error(request, erro)
        return redirect("rh:afastamentos")

    af = Afastamento.objects.create(
        colaborador=colaborador, tipo=tipo, data_inicio=di, data_fim=df,
        dia_inteiro=dia_inteiro, hora_inicio=hora_inicio, hora_fim=hora_fim,
        remunerado=request.POST.get("remunerado") == "on",
        observacao=request.POST.get("observacao", "").strip(),
        criado_por=request.user,
    )

    _salvar_anexos(af, request.FILES.getlist("anexos"))

    # O afastamento pode ter sido lançado depois que o dia já gerou pendência de
    # ponto (cron da noite anterior) — reprocessa os dias cobertos para resolver
    # a pendência agora que o dia está justificado.
    from apps.rh.services.notificacoes import gerar_pendencias_do_dia
    dia = di
    while dia <= df:
        gerar_pendencias_do_dia(dia)
        dia += timedelta(days=1)

    if dia_inteiro:
        cobertura = f"{af.dias} dia(s)"
    else:
        cobertura = f"{hora_inicio:%H:%M}–{hora_fim:%H:%M}"
    messages.success(request, f"{af.get_tipo_display()} lançado para {colaborador.nome} ({cobertura}).")
    return redirect(f"/rh/afastamentos/?colaborador={colaborador.id}&periodo=30")


@perm_required("rh.gerir")
@require_POST
def view_afastamento_salvar(request: HttpRequest, pk: int) -> HttpResponse:
    """Edição de um afastamento existente (super admin / quem gere o RH)."""
    af = get_object_or_404(Afastamento, pk=pk)
    colaborador, tipo, di, df, dia_inteiro, hora_inicio, hora_fim, erro = _ler_form(request)
    if erro:
        messages.error(request, erro)
        return redirect("rh:afastamento_editar", pk=pk)

    af.colaborador = colaborador
    af.tipo = tipo
    af.data_inicio = di
    af.data_fim = df
    af.dia_inteiro = dia_inteiro
    af.hora_inicio = hora_inicio
    af.hora_fim = hora_fim
    af.remunerado = request.POST.get("remunerado") == "on"
    af.observacao = request.POST.get("observacao", "").strip()
    af.save()

    _salvar_anexos(af, request.FILES.getlist("anexos"))

    from apps.rh.services.notificacoes import gerar_pendencias_do_dia
    dia = di
    while dia <= df:
        gerar_pendencias_do_dia(dia)
        dia += timedelta(days=1)

    messages.success(request, f"Afastamento de {colaborador.nome} atualizado.")
    return redirect("rh:afastamentos")


@perm_required("rh.gerir")
def view_afastamento_anexo(request: HttpRequest, pk: int) -> HttpResponse:
    """Serve o anexo legado (campo único) só para quem tem permissão de RH / super admin."""
    af = get_object_or_404(Afastamento, pk=pk)
    if not af.anexo:
        raise Http404
    return FileResponse(af.anexo.open("rb"))


@perm_required("rh.gerir")
def view_afastamento_anexo_item(request: HttpRequest, pk: int) -> HttpResponse:
    """Serve um dos anexos extras (quando há mais de uma foto no lançamento)."""
    anexo = get_object_or_404(AfastamentoAnexo, pk=pk)
    return FileResponse(anexo.arquivo.open("rb"))


@perm_required("rh.gerir")
@require_POST
def view_afastamento_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    af = get_object_or_404(Afastamento, pk=pk)
    af.delete()
    messages.success(request, "Afastamento removido.")
    return redirect("rh:afastamentos")
