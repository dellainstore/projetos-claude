"""
Assinatura HMAC do valor de frete apresentado ao cliente (Fase 7 - Monitoramento 5xx).

O valor de frete escolhido no checkout (valor_frete/opcao_frete/prazo_frete)
vem de campos hidden preenchidos por JS a partir da resposta de calcular_frete
e enviados de volta no POST. Sem assinatura, o navegador (DevTools) pode
alterar esse valor antes do envio. O token e gerado no momento em que as
opcoes de frete sao calculadas e verificado no checkout: se bater com o que
foi submetido, o valor e confiavel; se nao bater (ausente, expirado,
adulterado), o servidor recalcula o frete na hora em vez de bloquear o
pedido — nunca derruba o checkout por causa disso, so nao confia cegamente
num valor que nao pode verificar.
"""
import hashlib
import hmac
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings

_VALIDADE_S = 60 * 60 * 2  # 2h — tempo generoso para o cliente terminar o checkout


def _norm_preco(preco) -> str:
    """Normaliza pra 2 casas decimais — evita '18.9' vs '18.90' quebrar a assinatura."""
    try:
        return str(Decimal(str(preco)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        return str(preco)


def _payload(cep: str, opcao_id: str, preco: str, prazo, exp: int) -> str:
    try:
        prazo_norm = int(prazo)
    except (ValueError, TypeError):
        prazo_norm = prazo
    return f'{cep}|{opcao_id}|{_norm_preco(preco)}|{prazo_norm}|{exp}'


def assinar(cep: str, opcao_id: str, preco: str, prazo) -> str:
    exp = int(time.time()) + _VALIDADE_S
    assinatura = hmac.new(
        settings.SECRET_KEY.encode(), _payload(cep, opcao_id, preco, prazo, exp).encode(), hashlib.sha256
    ).hexdigest()[:32]
    return f'{exp}.{assinatura}'


def validar(token: str, cep: str, opcao_id: str, preco: str, prazo) -> bool:
    if not token or '.' not in token:
        return False
    try:
        exp_str, assinatura = token.split('.', 1)
        exp = int(exp_str)
    except (ValueError, TypeError):
        return False
    if exp < int(time.time()):
        return False
    esperado = hmac.new(
        settings.SECRET_KEY.encode(), _payload(cep, opcao_id, preco, prazo, exp).encode(), hashlib.sha256
    ).hexdigest()[:32]
    return hmac.compare_digest(esperado, assinatura)
