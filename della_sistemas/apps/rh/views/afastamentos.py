"""Afastamentos: faltas, atestados e folgas + histórico com filtros.

Férias NÃO entram aqui — são lançadas no módulo Férias.
"""

from datetime import date, timedelta

from django.contrib import messages
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.rh.models import Afastamento, Colaborador
from apps.rh.services.afastamentos import converter_anexo_para_webp
from apps.rh.services.utils import parse_int


def _parse_data(valor: str | None):
    """ISO 'AAAA-MM-DD' → date (ou None)."""
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


@perm_required("rh.gerir")
def view_afastamentos(request: HttpRequest, editar_pk: int | None = None) -> HttpResponse:
    colaboradores = list(Colaborador.objects.filter(ativo=True).order_by("nome"))

    editando = None
    if editar_pk:
        editando = get_object_or_404(Afastamento.objects.select_related("colaborador"), pk=editar_pk)

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
        "f_colab": f_colab,
        "periodo": periodo,
        "inicio": request.GET.get("inicio", ""),
        "fim": request.GET.get("fim", ""),
    })


@perm_required("rh.gerir")
def view_afastamento_editar(request: HttpRequest, pk: int) -> HttpResponse:
    return view_afastamentos(request, editar_pk=pk)


def _ler_form(request) -> tuple:
    """Lê e valida os campos comuns. Retorna (colaborador, tipo, di, df, erro)."""
    colaborador = Colaborador.objects.filter(pk=parse_int(request.POST.get("colaborador"), 0)).first()
    tipo = request.POST.get("tipo", "")
    di = _parse_data(request.POST.get("data_inicio"))
    df = _parse_data(request.POST.get("data_fim")) or di
    if colaborador is None or tipo not in dict(Afastamento.FORM_TIPO_CHOICES) or di is None:
        return None, None, None, None, "Informe colaborador, tipo e a data do afastamento."
    if df < di:
        di, df = df, di
    return colaborador, tipo, di, df, None


@perm_required("rh.gerir")
@require_POST
def view_afastamento_novo(request: HttpRequest) -> HttpResponse:
    colaborador, tipo, di, df, erro = _ler_form(request)
    if erro:
        messages.error(request, erro)
        return redirect("rh:afastamentos")

    af = Afastamento.objects.create(
        colaborador=colaborador, tipo=tipo, data_inicio=di, data_fim=df,
        remunerado=request.POST.get("remunerado") == "on",
        observacao=request.POST.get("observacao", "").strip(),
        criado_por=request.user,
    )

    arquivo = request.FILES.get("anexo")
    if arquivo:
        conteudo, nome = converter_anexo_para_webp(arquivo)
        af.anexo.save(nome, conteudo, save=True)

    messages.success(request, f"{af.get_tipo_display()} lançado para {colaborador.nome} ({af.dias} dia(s)).")
    return redirect(f"/rh/afastamentos/?colaborador={colaborador.id}&periodo=30")


@perm_required("rh.gerir")
@require_POST
def view_afastamento_salvar(request: HttpRequest, pk: int) -> HttpResponse:
    """Edição de um afastamento existente (super admin / quem gere o RH)."""
    af = get_object_or_404(Afastamento, pk=pk)
    colaborador, tipo, di, df, erro = _ler_form(request)
    if erro:
        messages.error(request, erro)
        return redirect("rh:afastamento_editar", pk=pk)

    af.colaborador = colaborador
    af.tipo = tipo
    af.data_inicio = di
    af.data_fim = df
    af.remunerado = request.POST.get("remunerado") == "on"
    af.observacao = request.POST.get("observacao", "").strip()
    af.save()

    arquivo = request.FILES.get("anexo")
    if arquivo:
        conteudo, nome = converter_anexo_para_webp(arquivo)
        af.anexo.save(nome, conteudo, save=True)

    messages.success(request, f"Afastamento de {colaborador.nome} atualizado.")
    return redirect("rh:afastamentos")


@perm_required("rh.gerir")
def view_afastamento_anexo(request: HttpRequest, pk: int) -> HttpResponse:
    """Serve o anexo (atestado) só para quem tem permissão de RH / super admin."""
    af = get_object_or_404(Afastamento, pk=pk)
    if not af.anexo:
        raise Http404
    return FileResponse(af.anexo.open("rb"))


@perm_required("rh.gerir")
@require_POST
def view_afastamento_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    af = get_object_or_404(Afastamento, pk=pk)
    af.delete()
    messages.success(request, "Afastamento removido.")
    return redirect("rh:afastamentos")
