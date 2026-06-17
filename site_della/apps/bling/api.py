"""
Bling API v3 — cliente HTTP.

Referência: https://developer.bling.com.br/referencia
"""

import logging
import time

import requests

from .oauth import get_valid_access_token

logger = logging.getLogger(__name__)

BASE_URL = 'https://api.bling.com.br/Api/v3'
RETRY_STATUS_CODES = {429}
RETRY_DELAYS_SECONDS = (0.6, 1.2, 2.0)


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

    def _request(self, method: str, endpoint: str, *, retry: bool = True, **kwargs) -> dict:
        url = f'{BASE_URL}{endpoint}'
        last_resp = None
        # retry=False: executa apenas 1 tentativa (contexto webhook — worker tem timeout de 30s)
        max_tentativas = len(RETRY_DELAYS_SECONDS) if retry else 0

        for tentativa in range(max_tentativas + 1):
            resp = requests.request(method, url, headers=self._headers(), timeout=20, **kwargs)
            last_resp = resp

            if resp.status_code not in RETRY_STATUS_CODES or tentativa == max_tentativas:
                break

            atraso = RETRY_DELAYS_SECONDS[tentativa]
            logger.warning(
                'Bling API %s em %s %s; retry em %.1fs (%s/%s)',
                resp.status_code,
                method,
                endpoint,
                atraso,
                tentativa + 1,
                len(RETRY_DELAYS_SECONDS),
            )
            time.sleep(atraso)

        try:
            data = last_resp.json()
        except ValueError:
            data = {'raw': last_resp.text}

        if not last_resp.ok:
            raise BlingAPIError(last_resp.status_code, data)
        return data

    # ── Pedidos de Venda ──────────────────────────────────────────────────────

    def criar_pedido_venda(self, payload: dict) -> dict:
        """POST /pedidos/vendas — cria o pedido no Bling."""
        return self._request('POST', '/pedidos/vendas', json=payload)

    def consultar_pedido_venda(self, bling_id: str, retry: bool = True) -> dict:
        """GET /pedidos/vendas/{id} — consulta status do pedido."""
        return self._request('GET', f'/pedidos/vendas/{bling_id}', retry=retry)

    def atualizar_situacao_pedido(self, bling_id: str, situacao_id: int) -> dict:
        """PATCH /pedidos/vendas/{id}/situacoes/{idSituacao} — altera situação."""
        return self._request('PATCH', f'/pedidos/vendas/{bling_id}/situacoes/{situacao_id}')

    def atualizar_pedido_venda(self, bling_id: str, payload: dict) -> dict:
        """PUT /pedidos/vendas/{id} — substitui o pedido (payload completo)."""
        return self._request('PUT', f'/pedidos/vendas/{bling_id}', json=payload)

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

    def consultar_estoque_produto(self, bling_produto_id: str, retry: bool = True) -> dict:
        """
        GET /estoques/saldos?idsProdutos[]={id} — retorna saldos de estoque por depósito.

        Estrutura da resposta:
            data[0].depositos[].id             → ID do depósito
            data[0].depositos[].saldoFisico    → estoque físico no depósito
            data[0].depositos[].saldoVirtual   → disponível para venda (físico − reservas Em andamento)

        Filtramos pelo BLING_DEPOSITO_ID (Show Room - D'ella) em services.py.
        """
        return self._request('GET', '/estoques/saldos', params={'idsProdutos[]': bling_produto_id}, retry=retry)

    def listar_depositos(self) -> list:
        """GET /depositos — lista todos os depósitos ativos. Requer escopo 'depositos'."""
        resp = self._request('GET', '/depositos', params={'situacao': 'A', 'limite': 100})
        return resp.get('data') or []

    def buscar_produto_por_sku(self, sku: str) -> 'dict | None':
        """
        GET /produtos?codigo={sku} — busca produto no Bling pelo código/SKU.
        Retorna o primeiro item encontrado ou None.
        """
        try:
            data = self._request('GET', '/produtos', params={'codigo': sku, 'limite': 5})
            items = data.get('data') or []
            for item in items:
                if item.get('codigo', '').strip() == sku.strip():
                    return item
        except BlingAPIError:
            pass
        return None

    # ── Logísticas ───────────────────────────────────────────────────────────

    def listar_logisticas(self, pagina: int = 1, limite: int = 100) -> dict:
        """GET /logisticas — lista logísticas configuradas na conta."""
        return self._request('GET', '/logisticas', params={'pagina': pagina, 'limite': limite})

    def consultar_logistica(self, logistica_id: int | str) -> dict:
        """GET /logisticas/{id} — consulta uma logística e seus serviços."""
        return self._request('GET', f'/logisticas/{logistica_id}')

    # ── Contatos ──────────────────────────────────────────────────────────────

    def criar_contato(self, payload: dict) -> dict:
        """POST /contatos — cria um novo contato no Bling."""
        return self._request('POST', '/contatos', json=payload)

    def consultar_contato(self, contato_id: int) -> dict:
        """GET /contatos/{id} — consulta dados completos de um contato."""
        return self._request('GET', f'/contatos/{contato_id}')

    def atualizar_contato(self, contato_id: int, payload: dict) -> dict:
        """PUT /contatos/{id} — atualiza dados de um contato existente."""
        return self._request('PUT', f'/contatos/{contato_id}', json=payload)

    def buscar_contato_por_cpf(self, cpf: str) -> 'int | None':
        """
        GET /contatos?criterio=3&pesquisa={cpf} — busca por CPF/CNPJ.

        O filtro não garante match exato: o Bling faz busca textual e pode
        retornar contatos cujos campos (nome/razão social) contenham a string.
        Por isso validamos cada resultado comparando o numeroDocumento real.
        """
        cpf_clean = ''.join(c for c in (cpf or '') if c.isdigit())
        if not cpf_clean:
            return None
        try:
            data = self._request('GET', '/contatos', params={
                'criterio': 3, 'pesquisa': cpf_clean, 'limite': 20,
            })
            for item in data.get('data', []) or []:
                doc = ''.join(c for c in (item.get('numeroDocumento') or '') if c.isdigit())
                if doc == cpf_clean:
                    return item.get('id')
        except BlingAPIError:
            pass
        return None

    def buscar_contato_por_telefone(self, telefone: str) -> 'int | None':
        """
        Busca contato por telefone. O Bling v3 nao expoe filtro direto por
        telefone; usa pesquisa geral e valida os campos telefone, celular e fax
        no retorno. Se nao encontrar match exato retorna None.
        """
        tel_clean = ''.join(c for c in (telefone or '') if c.isdigit())
        if not tel_clean or len(tel_clean) < 8:
            return None
        try:
            data = self._request('GET', '/contatos', params={
                'pesquisa': tel_clean, 'limite': 20,
            })
            for item in data.get('data', []) or []:
                tel = ''.join(c for c in (item.get('telefone') or '') if c.isdigit())
                cel = ''.join(c for c in (item.get('celular') or '') if c.isdigit())
                fax = ''.join(c for c in (item.get('fax') or '') if c.isdigit())
                if tel_clean in (tel, cel, fax):
                    return item.get('id')
        except BlingAPIError:
            pass
        return None
