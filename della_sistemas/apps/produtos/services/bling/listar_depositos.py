import requests
from apps.produtos.services.bling.api import _headers
from apps.produtos.services.config import BLING_BASE_URL

url = f"{BLING_BASE_URL}/depositos"
resp = requests.get(url, headers=_headers(), timeout=30)
resp.raise_for_status()
print(resp.json())
