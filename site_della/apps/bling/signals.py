"""
Signals da integração Bling.

Dispara sync de estoque imediatamente quando uma `Variacao` tem o checkbox
`usa_sync_bling` ativado (transição False → True) OU quando a variação é
reativada (ativo: False → True) com `usa_sync_bling` já marcado.
Sem isso, o estoque só sincronizaria na próxima janela do cron (até 1h).
"""

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(pre_save, sender='produtos.Variacao')
def _capturar_estado_anterior_sync(sender, instance, **kwargs):
    """Guarda `usa_sync_bling` e `ativo` antes do save para comparar no post_save."""
    if instance.pk:
        try:
            anterior = sender.objects.only('usa_sync_bling', 'ativo').get(pk=instance.pk)
            instance._sync_anterior = anterior.usa_sync_bling
            instance._ativo_anterior = anterior.ativo
        except sender.DoesNotExist:
            instance._sync_anterior = False
            instance._ativo_anterior = False
    else:
        instance._sync_anterior = False
        instance._ativo_anterior = False


@receiver(post_save, sender='produtos.Variacao')
def _sincronizar_estoque_ao_ativar(sender, instance, created, **kwargs):
    """Dispara sync imediato quando usa_sync_bling vira True OU variação é reativada com sync ligado."""
    sync_ativou = (
        not getattr(instance, '_sync_anterior', False)
        and instance.usa_sync_bling
    )
    variacao_reativada = (
        not getattr(instance, '_ativo_anterior', True)
        and instance.ativo
        and instance.usa_sync_bling
    )
    if not (sync_ativou or variacao_reativada):
        return

    motivo = 'sync ativado' if sync_ativou else 'variacao reativada'

    if not instance.bling_variacao_id:
        logger.info(
            'Variação %s: %s mas sem bling_variacao_id — sync ignorado',
            instance.pk, motivo,
        )
        return

    try:
        from apps.bling.services import sincronizar_estoque_bling
        resultado = sincronizar_estoque_bling([instance])
        logger.info(
            'Variação %s: sync imediato (%s) — %s',
            instance.pk, motivo, resultado,
        )
    except Exception as exc:
        logger.warning(
            'Variação %s: sync inicial pós-ativação falhou (cron resolverá depois): %s',
            instance.pk, exc,
        )
