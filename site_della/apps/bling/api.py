"""
Bling API v3 — cliente HTTP.

Referência: https://developer.bling.com.br/referencia
"""

import logging

import requests

from .oauth import get_valid_access_token

logger = logging.getLogger(__name__)

BASE_URL = 'https://api.bling.com.br/Api/v3'


class BlingAPIError(Exception):
    """Erro retornado pela API do Bling."""
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self.data = data
        descricao = data.get('error', {}).get('description', str(data))
        super().__init__(f'Bling API {status_code}: {descricao}')


class BlingAPI:
    """
    Cliente para a API do Bling v3.

    Uso:
        api = BlingAPI()
        api.criar_pedido_venda(pedido)
    """

    def __init__(self):
        self.access_token = get_valid_access_token()
        if not self.access_token:
            raise BlingAPIError(401, {'error': {'description': 'Token Bling não disponível.'}})

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type':  'application/json',
            'Accept':        'application/json',
        }

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        url = f'{BASE_URL}{endpoint}'
        resp = requests.request(method, url, headers=self._headers(), timeout=20, **kwargs)
        try:
            data = resp.json()
        except ValueError:
            data = {'raw': resp.text}

        if not resp.ok:
            raise BlingAPIError(resp.status_code, data)
        return data

    # ── Pedidos de Venda ──────────────────────────────────────────────────────

    def criar_pedido_venda(self, payload: dict) -> dict:
        """POST /pedidos/vendas — cria o pedido no Bling."""
        return self._request('POST', '/pedidos/vendas', json=payload)

    def consultar_pedido_venda(self, bling_id: str) -> dict:
        """GET /pedidos/vendas/{id} — consulta status do pedido."""
        return self._request('GET', f'/pedidos/vendas/{bling_id}')

    def atualizar_situacao_pedido(self, bling_id: str, situacao_id: int) -> dict:
        """PATCH /pedidos/vendas/{id}/situacoes/{idSituacao} — altera situação."""
        return self._request('PATCH', f'/pedidos/vendas/{bling_id}/situacoes/{situacao_id}')

    # ── NF-e ──────────────────────────────────────────────────────────────────

    def emitir_nfe_do_pedido(self, bling_pedido_id: str) -> dict:
        """
        POST /nfe?pedidoVendaId={id} — emite NF-e a partir de um pedido.
        Requer que a configuração fiscal esteja feita no painel do Bling.
        """
        return self._request('POST', '/nfe', params={'pedidoVendaId': bling_pedido_id})

    def consultar_nfe(self, nfe_id: str) -> dict:
        """GET /nfe/{id} — consulta situação da NF-e."""
        return self._request('GET', f'/nfe/{nfe_id}')

    def enviar_nfe_sefaz(self, nfe_id: str) -> dict:
        """POST /nfe/{id}/enviar — envia NF-e para SEFAZ."""
        return self._request('POST', f'/nfe/{nfe_id}/enviar')

    # ── Produtos / Estoque ────────────────────────────────────────────────────

    def listar_produtos(self, pagina: int = 1) -> dict:
        """GET /produtos — lista produtos do Bling (paginado)."""
        return self._request('GET', '/produtos', params={'pagina': pagina, 'limite': 100})

    def consultar_produto(self, bling_produto_id: str) -> dict:
        """GET /produtos/{id} — consulta produto do Bling."""
        return self._request('GET', f'/produtos/{bling_produto_id}')
