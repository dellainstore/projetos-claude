"""Google Places API (New) — precisao de numero de porta igual o Google Maps.

So entra em uso quando GOOGLE_PLACES_API_KEY estiver configurada no .env;
sem chave, o autocomplete cai pro Nominatim (services/geocoding.py)
automaticamente — ver solicitar.py.

NAO usar a Places API legada (v1 /maps/api/place/...) — o projeto do D'ELLA
so tem a "Places API (New)" habilitada (confirmado via teste real: a legada
devolve REQUEST_DENIED "not enabled for your project").
"""
import os

import requests

TIMEOUT = 8
API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
BASE_URL = "https://places.googleapis.com/v1"

# Vies de regiao pro autocomplete: centro aproximado da Grande Sao Paulo,
# raio generoso (50km) cobrindo tambem Campinas.
_BIAS_LAT = -23.55
_BIAS_LNG = -46.90
_BIAS_RAIO_M = 50000.0


def configurada() -> bool:
    return bool(API_KEY)


def buscar_enderecos(query: str) -> list[dict]:
    """POST /v1/places:autocomplete. Retorna [{description, place_id}]."""
    query = (query or "").strip()
    if len(query) < 5:
        return []
    payload = {
        "input": query,
        "languageCode": "pt-BR",
        "includedRegionCodes": ["br"],
        "locationBias": {
            "circle": {
                "center": {"latitude": _BIAS_LAT, "longitude": _BIAS_LNG},
                "radius": _BIAS_RAIO_M,
            }
        },
    }
    resp = requests.post(
        f"{BASE_URL}/places:autocomplete",
        json=payload,
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": API_KEY},
        timeout=TIMEOUT,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Google Places autocomplete {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    candidatos = []
    for s in data.get("suggestions", []):
        pred = s.get("placePrediction")
        if not pred:
            continue
        candidatos.append({
            "description": pred.get("text", {}).get("text", ""),
            "place_id": pred.get("placeId", ""),
        })
    return candidatos


def detalhes_place(place_id: str) -> dict | None:
    """GET /v1/places/{placeId} — devolve lat/lng exatos (com numero, quando
    existir) + endereco curto montado a partir dos addressComponents."""
    resp = requests.get(
        f"{BASE_URL}/places/{place_id}",
        headers={
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": "location,formattedAddress,addressComponents",
        },
        timeout=TIMEOUT,
    )
    if resp.status_code >= 400:
        return None
    resultado = resp.json()
    loc = resultado.get("location", {})

    componentes = {}
    for c in resultado.get("addressComponents", []):
        for tipo in c.get("types", []):
            componentes.setdefault(tipo, c.get("longText", ""))

    partes = []
    rua = componentes.get("route", "")
    numero = componentes.get("street_number", "")
    if rua:
        partes.append(f"{rua}, {numero}" if numero else rua)
    bairro = componentes.get("sublocality_level_1") or componentes.get("sublocality") or componentes.get("neighborhood")
    if bairro:
        partes.append(bairro)
    cidade = componentes.get("administrative_area_level_2") or componentes.get("locality")
    if cidade:
        partes.append(cidade)

    return {
        "endereco": ", ".join(partes) or resultado.get("formattedAddress", ""),
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
        "tem_numero": bool(numero),
    }
