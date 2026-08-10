"""
Token assinado que autoriza avaliar UM pedido especifico sem exigir login.

Criado para clientes que compram como convidadas (checkout sem criar conta,
Pedido.cliente = None) -- ate 2026-08-10 o e-mail de avaliacao pos-entrega
mandava qualquer cliente para /conta/entrar/, e quem comprou sem conta nunca
consegue logar la (nao existe Cliente com esse e-mail). Caso real: Camila
Dantas, pedido 2026-0018, bloqueada pelo Axes apos 6 tentativas -- nao era
ataque, era cliente sem conta tentando entrar numa tela que nunca ia aceitar.

O token nao concede login nem acesso a conta -- so libera o formulario de
avaliacao daquele pedido especifico, e expira.
"""
from datetime import timedelta

from django.core import signing

_SALT = 'pedidos.avaliacao'
MAX_AGE_DIAS = 90


def gerar_token_avaliacao(pedido) -> str:
    """Token assinado (HMAC via SECRET_KEY) para o link de avaliacao do
    pedido. Nao guarda nada no banco -- validado so por assinatura + prazo."""
    return signing.TimestampSigner(salt=_SALT).sign(pedido.numero)


def validar_token_avaliacao(numero: str, token: str) -> bool:
    """True se o token for valido para ESTE numero de pedido e ainda estiver
    dentro do prazo (MAX_AGE_DIAS). Nunca levanta excecao."""
    if not token or not numero:
        return False
    try:
        valor = signing.TimestampSigner(salt=_SALT).unsign(
            token, max_age=timedelta(days=MAX_AGE_DIAS),
        )
    except (signing.BadSignature, signing.SignatureExpired):
        return False
    return valor == numero
