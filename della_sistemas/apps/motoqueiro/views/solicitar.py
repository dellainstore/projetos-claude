from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.rh.models import Colaborador

from ..models import MovimentoSaldoLalamove, SolicitacaoEntrega, SolicitacaoEntregaEvento
from ..services import google_places, lalamove
from ..services.geocoding import buscar_enderecos


def _colaborador_do_pedido(request: HttpRequest) -> Colaborador | None:
    """Quem esta pedindo. Só quem tem `solicitar_para_outros` (gestor/
    superadmin) pode lançar em nome de outro colaborador; os demais só em
    nome de si mesmo (via login vinculado, mesmo padrão de bater ponto)."""
    if request.user.pode_solicitar_motoqueiro_para_outros:
        colaborador_id = request.POST.get("colaborador_id") or request.GET.get("colaborador_id")
        if colaborador_id:
            return Colaborador.objects.filter(pk=colaborador_id, ativo=True).first()
    return getattr(request.user, "colaborador", None)


@perm_required("motoqueiro.solicitar")
def view_solicitar(request: HttpRequest) -> HttpResponse:
    colaborador = _colaborador_do_pedido(request)
    pode_escolher = request.user.pode_solicitar_motoqueiro_para_outros
    ctx = {
        "colaborador": colaborador,
        "colaboradores": Colaborador.objects.filter(ativo=True).order_by("nome") if pode_escolher else None,
    }
    if not colaborador:
        messages.warning(
            request,
            "Seu usuário não está vinculado a um colaborador do RH — fale com o superadmin "
            "para vincular antes de solicitar uma corrida."
        )
    return render(request, "motoqueiro/solicitar.html", ctx)


@perm_required("motoqueiro.solicitar")
def htmx_autocomplete(request: HttpRequest) -> HttpResponse:
    """Sugestoes de endereco conforme digita (debounce de 500ms no front).
    Usa Google Places (numero exato, igual Google Maps) quando
    GOOGLE_PLACES_API_KEY estiver configurada; sem chave, cai pro Nominatim
    (gratis, mas sem numero de porta em varias ruas do Brasil)."""
    campo = request.GET.get("campo", "retirada")
    query = request.GET.get("q") or request.GET.get(f"endereco_{campo}", "")

    if google_places.configurada():
        try:
            candidatos = google_places.buscar_enderecos(query)
        except Exception:
            candidatos = []
        return render(request, "motoqueiro/_autocomplete_google.html", {"campo": campo, "candidatos": candidatos})

    try:
        candidatos = buscar_enderecos(query)
    except Exception:
        candidatos = []
    return render(request, "motoqueiro/_autocomplete_endereco.html", {"campo": campo, "candidatos": candidatos})


@perm_required("motoqueiro.solicitar")
def htmx_place_details(request: HttpRequest) -> HttpResponse:
    """So usado no modo Google: resolve o place_id escolhido em lat/lng
    exatos (JSON simples, consumido via fetch() no JS da tela)."""
    place_id = request.GET.get("place_id", "")
    if not place_id:
        return JsonResponse({"ok": False}, status=400)
    try:
        detalhes = google_places.detalhes_place(place_id)
    except Exception:
        detalhes = None
    if not detalhes:
        return JsonResponse({"ok": False}, status=404)
    return JsonResponse({"ok": True, **detalhes})


@perm_required("motoqueiro.solicitar")
def htmx_cotar(request: HttpRequest) -> HttpResponse:
    """Passo 1: so cota (nao cria nada no Lalamove ainda, nao cobra). Exige
    que o endereco tenha sido escolhido no autocomplete (lat/lng preenchidos
    pelo JS) — sem isso o Lalamove recusa endereco ambiguo."""
    endereco_retirada = request.POST.get("endereco_retirada", "").strip()
    endereco_entrega = request.POST.get("endereco_entrega", "").strip()
    complemento_retirada = request.POST.get("complemento_retirada", "").strip()
    complemento_entrega = request.POST.get("complemento_entrega", "").strip()
    lat_retirada = request.POST.get("lat_retirada", "")
    lng_retirada = request.POST.get("lng_retirada", "")
    lat_entrega = request.POST.get("lat_entrega", "")
    lng_entrega = request.POST.get("lng_entrega", "")

    if not endereco_retirada or not endereco_entrega:
        return render(request, "motoqueiro/_solicitar_erro.html", {"erro": "Informe os dois endereços."})
    if not (lat_retirada and lng_retirada and lat_entrega and lng_entrega):
        return render(request, "motoqueiro/_solicitar_erro.html", {
            "erro": "Escolha o endereço na lista de sugestões que aparece enquanto você digita (clique em uma opção)."
        })

    # O Lalamove NAO tem campo proprio pra bloco/apto/andar (testado: rejeita
    # qualquer campo extra no stop) — o jeito aceito e' embutir no texto do
    # endereco, que e' o que o motoboy le como destino/retirada.
    endereco_lalamove_retirada = f"{endereco_retirada} - {complemento_retirada}" if complemento_retirada else endereco_retirada
    endereco_lalamove_entrega = f"{endereco_entrega} - {complemento_entrega}" if complemento_entrega else endereco_entrega

    # Cota cada veiculo do Lalamove separadamente — a API nao devolve varios
    # precos numa chamada so, e cada tipo (LalaGo sem bau / LalaPro com bau)
    # e uma cotacao propria com seu proprio quotationId. Nao existe opcao de
    # "Prioridade"/"Agrupado" na API de parceiro (testado e confirmado: o
    # Lalamove recusa e lista so WAITING_TIME_*/RETURN/THERMAL_BAG_1 como
    # specialRequests validos) — so da pra oferecer o preco Regular mesmo.
    VEICULOS_LALAMOVE = [
        ("LALAGO", "Lalamove — LalaGo (moto, sem baú)"),
        ("LALAPRO", "Lalamove — LalaPro (moto com baú)"),
    ]
    cotacoes = []
    erros = []
    for service_type, label in VEICULOS_LALAMOVE:
        try:
            resp = lalamove.criar_cotacao(
                endereco_retirada=endereco_lalamove_retirada, lat_retirada=float(lat_retirada), lng_retirada=float(lng_retirada),
                endereco_entrega=endereco_lalamove_entrega, lat_entrega=float(lat_entrega), lng_entrega=float(lng_entrega),
                service_type=service_type,
            )
        except lalamove.LalamoveError as e:
            erros.append(f"{label}: {e.status_code} — {e.body[:200]}")
            continue
        except Exception as e:
            erros.append(f"{label}: {e}")
            continue

        dados = resp.get("data", {})
        stops = dados.get("stops", [])
        cotacoes.append({
            "plataforma": "lalamove",
            "veiculo": service_type,
            "label": label,
            "quotation_id": dados.get("quotationId"),
            "preco": dados.get("priceBreakdown", {}).get("total"),
            "moeda": dados.get("priceBreakdown", {}).get("currency", "BRL"),
            "stop_id_retirada": stops[0]["stopId"] if len(stops) > 0 else "",
            "stop_id_entrega": stops[1]["stopId"] if len(stops) > 1 else "",
        })

    if not cotacoes:
        return render(request, "motoqueiro/_solicitar_erro.html", {"erro": "Nenhuma cotação disponível. " + " | ".join(erros)})

    mais_barata_id = min(cotacoes, key=lambda c: float(c["preco"] or 0))["quotation_id"]

    ctx = {
        "cotacoes": cotacoes,
        "mais_barata_id": mais_barata_id,
        "erros": erros,
        "endereco_retirada": endereco_retirada,
        "endereco_entrega": endereco_entrega,
        "complemento_retirada": complemento_retirada,
        "complemento_entrega": complemento_entrega,
        "lat_retirada": lat_retirada, "lng_retirada": lng_retirada,
        "lat_entrega": lat_entrega, "lng_entrega": lng_entrega,
    }
    return render(request, "motoqueiro/_solicitar_cotacoes.html", ctx)


@perm_required("motoqueiro.solicitar")
def htmx_confirmar(request: HttpRequest) -> HttpResponse:
    """Passo 2: confirma de verdade — CRIA o pedido no Lalamove (cobra) e só
    então grava o registro local. Nome de remetente/destinatário e a
    finalidade (comercial/produção) só são pedidos aqui, depois que a
    cotação já foi escolhida."""
    colaborador = _colaborador_do_pedido(request)
    if not colaborador:
        return render(request, "motoqueiro/_solicitar_erro.html", {"erro": "Colaborador não identificado."})

    quotation_id = request.POST.get("quotation_id", "")
    stop_id_retirada = request.POST.get("stop_id_retirada", "")
    stop_id_entrega = request.POST.get("stop_id_entrega", "")
    endereco_retirada = request.POST.get("endereco_retirada", "").strip()
    endereco_entrega = request.POST.get("endereco_entrega", "").strip()
    complemento_retirada = request.POST.get("complemento_retirada", "").strip()
    complemento_entrega = request.POST.get("complemento_entrega", "").strip()
    remetente = request.POST.get("remetente", "").strip()
    remetente_telefone = request.POST.get("remetente_telefone", "").strip()
    destinatario = request.POST.get("destinatario", "").strip()
    destinatario_telefone = request.POST.get("destinatario_telefone", "").strip()
    observacao = request.POST.get("observacao", "").strip()
    preco = request.POST.get("preco", "0")
    finalidade = request.POST.get("finalidade", "")
    veiculo_label = request.POST.get("veiculo_label", "")

    if not all([quotation_id, stop_id_retirada, stop_id_entrega, remetente, destinatario]):
        return render(request, "motoqueiro/_solicitar_erro.html", {"erro": "Faltam dados obrigatórios (remetente/destinatário)."})
    if finalidade not in dict(SolicitacaoEntrega.FINALIDADE_CHOICES):
        return render(request, "motoqueiro/_solicitar_erro.html", {"erro": "Escolha se o frete é comercial (venda) ou de produção."})

    try:
        resp = lalamove.criar_pedido(
            quotation_id=quotation_id,
            stop_id_retirada=stop_id_retirada, stop_id_entrega=stop_id_entrega,
            remetente=remetente, remetente_telefone=remetente_telefone,
            destinatario=destinatario, destinatario_telefone=destinatario_telefone,
            observacao=observacao,
        )
    except lalamove.LalamoveError as e:
        return render(request, "motoqueiro/_solicitar_erro.html", {"erro": f"Lalamove recusou o pedido ({e.status_code}): {e.body[:300]}"})
    except Exception as e:
        return render(request, "motoqueiro/_solicitar_erro.html", {"erro": f"Erro inesperado ao confirmar: {e}"})

    dados = resp.get("data", {})
    order_id = dados.get("orderId", "")

    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    solicitacao = SolicitacaoEntrega.objects.create(
        colaborador=colaborador,
        solicitado_por=request.user,
        plataforma=SolicitacaoEntrega.PLATAFORMA_LALAMOVE,
        veiculo=veiculo_label,
        status=SolicitacaoEntrega.STATUS_AGUARDANDO_COLETA,
        finalidade=finalidade,
        endereco_retirada=endereco_retirada,
        endereco_entrega=endereco_entrega,
        complemento_retirada=complemento_retirada,
        complemento_entrega=complemento_entrega,
        lat_retirada=_f(request.POST.get("lat_retirada")),
        lng_retirada=_f(request.POST.get("lng_retirada")),
        lat_entrega=_f(request.POST.get("lat_entrega")),
        lng_entrega=_f(request.POST.get("lng_entrega")),
        remetente=remetente,
        destinatario=destinatario,
        valor=Decimal(str(preco or "0")),
        observacao=observacao,
        lalamove_order_id=order_id,
        lalamove_quotation_id=quotation_id,
        lalamove_status_raw=dados.get("status", ""),
        # Nome exato do campo nao confirmado ao vivo ainda (evitamos criar
        # pedido real so pra testar) — checa as variantes mais prováveis
        # da doc da Lalamove v3. Se vier vazio na primeira corrida real,
        # olhar o payload cru salvo no SolicitacaoEntregaEvento pra corrigir.
        lalamove_share_link=(dados.get("shareLink") or dados.get("trackingUrl") or dados.get("share_link") or ""),
    )
    SolicitacaoEntregaEvento.objects.create(
        solicitacao=solicitacao,
        status_novo=solicitacao.status,
        status_raw=dados.get("status", ""),
        origem="manual",
        payload=dados,
    )
    # Debito automatico da carteira Lalamove — a API deles nao expoe saldo
    # (testado: sem endpoint), entao controlamos por ledger local. Toda
    # corrida real confirmada pelo sistema abate daqui sozinha; lancamentos
    # manuais (recarga ou saida fora do sistema) ficam na tela de Saldo.
    MovimentoSaldoLalamove.objects.create(
        tipo=MovimentoSaldoLalamove.TIPO_DEBITO,
        origem=MovimentoSaldoLalamove.ORIGEM_CORRIDA,
        valor=solicitacao.valor,
        descricao=f"Corrida #{solicitacao.id} — {veiculo_label} — {colaborador.nome}",
        solicitacao=solicitacao,
        lancado_por=request.user,
    )
    return render(request, "motoqueiro/_solicitar_sucesso.html", {"solicitacao": solicitacao})
