"""
Signals do app produtos.

Empurra o produto pro catalogo da Meta em tempo real (ver
apps/produtos/services/meta_catalog.py) assim que um Produto ou uma de suas
Variacao e salvo ou removida. O feed diario (/feed-meta.xml) continua
rodando como rede de seguranca (cobre mudanca de categoria, exclusao de
produto e qualquer chamada que tenha falhado).
"""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.produtos.services.meta_catalog import enviar_atualizacao_produto_meta

logger = logging.getLogger(__name__)


@receiver(post_save, sender='produtos.Produto', dispatch_uid='meta_catalog_produto_save')
def _push_produto_ao_salvar(sender, instance, **kwargs):
    enviar_atualizacao_produto_meta(instance)


@receiver(post_save, sender='produtos.Variacao', dispatch_uid='meta_catalog_variacao_save')
def _push_produto_ao_salvar_variacao(sender, instance, **kwargs):
    if instance.produto_id:
        enviar_atualizacao_produto_meta(instance.produto)


@receiver(post_delete, sender='produtos.Variacao', dispatch_uid='meta_catalog_variacao_delete')
def _push_produto_ao_remover_variacao(sender, instance, **kwargs):
    if instance.produto_id:
        enviar_atualizacao_produto_meta(instance.produto)
