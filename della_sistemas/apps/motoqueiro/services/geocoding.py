"""Busca de endereço via Nominatim (OpenStreetMap) — gratis, sem chave.

Usado pro autocomplete de endereco na tela de Solicitar Corrida: o usuario
digita, o front dispara essa busca com um pequeno atraso (debounce) e mostra
os candidatos pra ele escolher o certo (evita "endereco nao encontrado" por
digitacao levemente diferente do que o Nominatim reconhece).

Limite da politica de uso do Nominatim: 1 req/s, nada de autocomplete
"por tecla" sem atraso — por isso o gatilho no HTMX tem delay de 500ms e
exige pelo menos alguns caracteres antes de buscar.
"""
import requests

TIMEOUT = 8

# Caixa cobrindo Grande Sao Paulo + Campinas (mesma area do mercado Lalamove
# "BR SAO - Sao Paulo & Campinas") — evita sugestao de endereco de outro
# estado/cidade distante quando o texto digitado bate com algum lugar
# homonimo em outro lugar do Brasil. Formato Nominatim: "min_lon,max_lat,
# max_lon,min_lat". bounded=1 filtra estrito (nao so prioriza, exclui fora).
_VIEWBOX_SP = "-47.35,-22.75,-46.25,-24.10"


def _endereco_curto(address: dict) -> str:
    """Monta 'Rua X, 123, Bairro, Cidade' a partir do address estruturado do
    Nominatim — sem CEP/regiao/pais/estado e sem bairro duplicado."""
    partes = []
    rua = address.get("road", "")
    numero = address.get("house_number", "")
    if rua:
        partes.append(f"{rua}, {numero}" if numero else rua)
    bairro = address.get("suburb") or address.get("neighbourhood") or address.get("city_district")
    if bairro:
        partes.append(bairro)
    cidade = address.get("city") or address.get("town") or address.get("municipality")
    if cidade:
        partes.append(cidade)
    return ", ".join(partes)


def buscar_enderecos(query: str, limit: int = 5) -> list[dict]:
    """Fallback gratuito (Nominatim/OpenStreetMap). ATENCAO: varias ruas no
    Brasil nao tem numero de porta cadastrado no OSM — nesses casos o
    resultado cai no meio da rua, sem precisao de numero. Preferir
    google_places.buscar_enderecos() quando GOOGLE_PLACES_API_KEY estiver
    configurada (ver services/google_places.py)."""
    query = (query or "").strip()
    if len(query) < 5:
        return []
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": query, "format": "json", "limit": limit, "countrycodes": "br", "addressdetails": 1,
            "viewbox": _VIEWBOX_SP, "bounded": 1,
        },
        headers={"User-Agent": "della-sistemas-motoqueiro/1.0"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    candidatos = []
    for r in resp.json():
        address = r.get("address", {})
        candidatos.append({
            "display_name": _endereco_curto(address) or r.get("display_name", ""),
            "lat": r.get("lat"),
            "lon": r.get("lon"),
            "tem_numero": bool(address.get("house_number")),
        })
    return candidatos
