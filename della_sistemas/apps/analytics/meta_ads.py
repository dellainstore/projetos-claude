"""Serviço do painel Site > Anúncios: le investimento e performance das
campanhas do Meta (Facebook/Instagram Ads) via Marketing API.

Só leitura — não cria, edita nem pausa nada no Meta. Reaproveita o mesmo
token de sistema usado no Conversions API do site_della (tem ads_read/
ads_management), guardado à parte aqui como META_ADS_TOKEN porque é um uso
diferente (ler campanhas, não mandar eventos de compra).

Unidade de análise é a CAMPANHA (pedido do dono em 2026-08-24 — a primeira
versão era por anúncio individual, mas ficou granular e lenta demais pro que
ele queria: acompanhar o desempenho geral de cada campanha).
"""

import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_BASE_URL = "https://graph.facebook.com"
_TIMEOUT = 15
_CACHE_TTL_CAMPANHAS = 180  # 3min: lista de campanhas muda pouco, evita bater na API a cada carregamento da tela

# actions/action_values do Meta trazem dezenas de action_type por evento.
# Para cada etapa do funil usamos o primeiro action_type da lista de
# prioridade que existir no payload (evita somar "omni_purchase" +
# "purchase", que se sobrepõem — são o mesmo evento contado de formas
# diferentes). omni_* é o número recomendado pelo próprio Meta (conta a
# compra web + qualquer canal que ele conseguiu casar); os outros são
# fallback pra contas/períodos que não têm o omni_* calculado.
_ACTION_TYPES_CARRINHO = ("omni_add_to_cart", "add_to_cart", "offsite_conversion.fb_pixel_add_to_cart")
_ACTION_TYPES_COMPRA   = ("omni_purchase", "purchase", "offsite_conversion.fb_pixel_purchase")


def configurado() -> bool:
    return bool(settings.META_ADS_ACCOUNT_ID and settings.META_ADS_TOKEN)


def _conta_id() -> str:
    conta = settings.META_ADS_ACCOUNT_ID
    return conta if conta.startswith("act_") else f"act_{conta}"


def _get(path: str, params: dict) -> dict | None:
    url = f"{_BASE_URL}/{settings.META_ADS_API_VERSION}/{path}"
    params = {**params, "access_token": settings.META_ADS_TOKEN}
    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        payload = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("meta_ads: falha de rede/parse em %s: %s", path, e)
        return None
    if resp.status_code != 200 or "error" in payload:
        logger.warning(
            "meta_ads: Graph API retornou erro em %s (status=%s): %s",
            path, resp.status_code, payload.get("error"),
        )
        return None
    return payload


def _extrair_valor_acao(lista: list[dict] | None, tipos: tuple[str, ...]) -> float:
    if not lista:
        return 0.0
    por_tipo = {item.get("action_type"): item.get("value") for item in lista}
    for tipo in tipos:
        if tipo in por_tipo:
            try:
                return float(por_tipo[tipo])
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def listar_campanhas() -> list[dict]:
    """Todas as campanhas da conta (ativas e inativas/pausadas/antigas).
    Não filtra por período: é a lista pro seletor, não os números.
    Cacheada alguns minutos — é a chamada mais lenta da tela e a lista quase
    não muda de um carregamento pro outro.

    `inicio` é a data de início da campanha no Meta (`start_time`), usada
    pra calcular o período padrão da tela: desde a campanha ativa mais
    antiga até hoje."""
    if not configurado():
        return []

    cacheado = cache.get("meta_ads_campanhas")
    if cacheado is not None:
        return cacheado

    payload = _get(
        f"{_conta_id()}/campaigns",
        {"fields": "id,name,effective_status,start_time,daily_budget", "limit": 500},
    )
    if not payload:
        return []

    from datetime import datetime

    resultado = []
    for c in payload.get("data", []):
        ativa = c.get("effective_status") == "ACTIVE"
        inicio = None
        if c.get("start_time"):
            try:
                inicio = datetime.fromisoformat(c["start_time"])
            except ValueError:
                inicio = None
        # daily_budget vem em centavos (ex.: "5500" = R$ 55,00). Campanhas
        # configuradas com orçamento vitalício (lifetime_budget) em vez de
        # diário não trazem este campo — ficam sem orçamento diário mesmo.
        orcamento_diario = None
        if c.get("daily_budget"):
            try:
                orcamento_diario = int(c["daily_budget"]) / 100
            except (TypeError, ValueError):
                orcamento_diario = None
        resultado.append({
            "id": c["id"],
            "nome": c.get("name") or "(sem nome)",
            "ativa": ativa,
            "status_label": "Ativa" if ativa else "Inativa",
            "inicio": inicio,
            "orcamento_diario": orcamento_diario,
        })
    resultado.sort(key=lambda c: (not c["ativa"], c["nome"].upper()))

    cache.set("meta_ads_campanhas", resultado, _CACHE_TTL_CAMPANHAS)
    return resultado


def orcamento_diario_medio(campanhas: list[dict], campaign_ids: list[str] | None) -> float | None:
    """Orçamento diário da(s) campanha(s) selecionada(s), pra exibir junto do
    resultado do período (pedido do dono em 2026-08-24 pra bater com o
    'Orçamento diário da campanha' que ele vê no próprio Meta).

    Com mais de uma campanha selecionada, usa a MÉDIA entre elas (pedido
    explícito) — não a soma, que não corresponde a nada que o Meta mostra.
    Campanhas com orçamento vitalício (sem orçamento diário) são ignoradas
    nessa média; se nenhuma das selecionadas tiver orçamento diário, retorna
    None.
    """
    if not campaign_ids:
        campaign_ids = [c["id"] for c in campanhas]
    valores = [
        c["orcamento_diario"] for c in campanhas
        if c["id"] in campaign_ids and c.get("orcamento_diario")
    ]
    if not valores:
        return None
    return sum(valores) / len(valores)


def funil_periodo(inicio, fim, campaign_ids: list[str] | None = None) -> dict:
    """Funil consolidado do período, na ordem em que o cliente realmente
    passa por ele: alcance → clique → adição ao carrinho → compra.

    `inicio`/`fim` em `None` = todo o histórico disponível
    (`date_preset=maximum` do próprio Meta) — é o padrão desta tela: mostrar
    o período inteiro da campanha, não só hoje/ontem.

    Quando `campaign_ids` tem mais de uma campanha, o alcance somado NÃO é a
    soma do alcance de cada campanha (uma mesma pessoa pode ter visto mais
    de uma) — por isso o filtro é feito dentro da própria chamada à API
    (`filtering` campaign.id IN [...]), deixando o Meta calcular o alcance
    único do grupo em vez de somarmos no Python.
    """
    if not configurado():
        return {"tem_dados": False}

    params = {
        "level": "account",
        # "clicks"/"cpc" (usados antes aqui) contam QUALQUER clique no
        # anúncio — curtida, comentário, expandir legenda etc. — não só o
        # clique que leva pro site. É por isso que "Cliques"/"Custo por
        # clique" nunca batiam com o que o dono via no Gerenciador de
        # Anúncios do Meta (conferido em 2026-08-24: sistema mostrava
        # cliques=1165/CPC=1,09 contra 1152/1,37 no Meta). O Gerenciador usa
        # por padrão "Cliques no link" = inline_link_clicks, com
        # cost_per_inline_link_click como custo por clique — troca abaixo
        # confirmada batendo exatamente (1,377294 ≈ 1,37) direto na API.
        "fields": "spend,reach,actions,action_values,inline_link_clicks,cost_per_inline_link_click",
    }
    if inicio is None or fim is None:
        params["date_preset"] = "maximum"
    else:
        params["time_range"] = '{"since":"%s","until":"%s"}' % (
            inicio.date().isoformat(), fim.date().isoformat(),
        )
    if campaign_ids:
        import json as _json
        params["filtering"] = _json.dumps([{"field": "campaign.id", "operator": "IN", "value": campaign_ids}])

    payload = _get(f"{_conta_id()}/insights", params)
    dados = (payload or {}).get("data", [])
    if not dados:
        return {"tem_dados": False}

    linha = dados[0]
    investido = float(linha.get("spend") or 0)
    alcance = int(linha.get("reach") or 0)
    cliques = int(float(linha.get("inline_link_clicks") or 0))
    custo_por_clique = float(linha.get("cost_per_inline_link_click") or 0)
    carrinho = int(_extrair_valor_acao(linha.get("actions"), _ACTION_TYPES_CARRINHO))
    compras = int(_extrair_valor_acao(linha.get("actions"), _ACTION_TYPES_COMPRA))
    valor_compras = _extrair_valor_acao(linha.get("action_values"), _ACTION_TYPES_COMPRA)
    # Card pedido em 2026-08-24 pra bater com "Custo por Compra" do Meta
    # (confirmado: spend ÷ compras = 178,57, igual ao que ele via lá).
    custo_por_compra = (investido / compras) if compras else None

    def _pct(valor, base):
        return round(valor / base * 100, 1) if base else 0.0

    # `pct_barra` é sempre em relação ao alcance (base 100%) — é o que dá a
    # forma de funil afunilando visualmente. `pct_texto`/`legenda` mostram a
    # taxa de conversão do PASSO ANTERIOR pro atual, que é o número que faz
    # sentido ler (ex: "quantos de quem colocou no carrinho comprou" — bem
    # diferente, e bem mais alto, do que "quantos de todo mundo alcançado
    # comprou", que fica sempre perto de zero e parece que nada funcionou).
    funil = [
        {"label": "Pessoas alcançadas", "valor": alcance,
         "pct_barra": 100.0, "pct_texto": 100.0, "legenda": ""},
        {"label": "Cliques no link", "valor": cliques,
         "pct_barra": _pct(cliques, alcance), "pct_texto": _pct(cliques, alcance),
         "legenda": "de quem foi alcançado"},
        {"label": "Adições ao carrinho", "valor": carrinho,
         "pct_barra": _pct(carrinho, alcance), "pct_texto": _pct(carrinho, cliques),
         "legenda": "de quem clicou"},
        {"label": "Compras", "valor": compras,
         "pct_barra": _pct(compras, alcance), "pct_texto": _pct(compras, carrinho),
         "legenda": "de quem colocou no carrinho"},
    ]

    retorno = (valor_compras / investido) if investido else None

    return {
        "tem_dados": True,
        "investido": investido,
        "alcance": alcance,
        "cliques": cliques,
        "custo_por_clique": custo_por_clique,
        "compras": compras,
        "custo_por_compra": custo_por_compra,
        "valor_compras": valor_compras,
        "retorno": retorno,
        "funil": funil,
    }
