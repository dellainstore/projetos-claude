"""Signals do app pedidos."""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='pedidos.Pedido', dispatch_uid='pedidos_sync_carrinho_abandonado')
def sincronizar_carrinho_abandonado(sender, instance, **kwargs):
    """Mantem `CarrinhoAbandonado.recuperado` em dia com o status do pedido.

    O status do pedido muda em varios lugares (checkout com cartao aprovado,
    webhook PagBank do PIX, action do admin, webhook do Bling). Um signal
    garante que todos esses caminhos recuperem/desrecuperem o carrinho, sem
    precisar lembrar de chamar a funcao em cada um deles.
    """
    from apps.pedidos.services.carrinho_abandonado import sincronizar_recuperacao

    sincronizar_recuperacao(instance)
