"""
Cancela pedidos em "Aguardando Pagamento" com mais de 2 dias sem pagamento.

Uso:
    python manage.py cancelar_pedidos_expirados --settings=core.settings.production

Recomendação: rodar via cron a cada hora:
    0 * * * * /var/www/della-sistemas/projetos-claude/site_della/venv/bin/python \
              /var/www/della-sistemas/projetos-claude/site_della/manage.py \
              cancelar_pedidos_expirados --settings=core.settings.production
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cancela pedidos aguardando pagamento há mais de 2 dias.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dias',
            type=int,
            default=2,
            help='Dias sem pagamento antes de cancelar (padrão: 2).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra o que seria cancelado sem fazer alterações.',
        )

    def handle(self, *args, **options):
        from apps.pedidos.models import Pedido, HistoricoPedido

        dias   = options['dias']
        dry    = options['dry_run']
        limite = timezone.now() - timedelta(days=dias)

        expirados = Pedido.objects.filter(
            status='aguardando_pagamento',
            criado_em__lte=limite,
        )

        total = expirados.count()
        if total == 0:
            self.stdout.write('Nenhum pedido expirado encontrado.')
            return

        if dry:
            self.stdout.write(f'[DRY-RUN] {total} pedido(s) seriam cancelados:')
            for p in expirados:
                self.stdout.write(f'  - {p.numero} (criado em {p.criado_em:%d/%m/%Y %H:%M})')
            return

        cancelados = 0
        for pedido in expirados:
            try:
                HistoricoPedido.objects.create(
                    pedido=pedido,
                    status_anterior='aguardando_pagamento',
                    status_novo='cancelado',
                    observacao=f'Cancelado automaticamente após {dias} dias sem pagamento.',
                )
                pedido.status = 'cancelado'
                pedido.save(update_fields=['status', 'atualizado_em'])
                cancelados += 1
                logger.info('Pedido %s cancelado automaticamente.', pedido.numero)

                # Restaura estoque no site
                try:
                    from apps.bling.services import restaurar_estoque_pedido
                    restaurar_estoque_pedido(pedido)
                except Exception as exc_e:
                    logger.error('Erro ao restaurar estoque do pedido %s: %s', pedido.numero, exc_e)

                # Cancela no Bling (libera reserva de estoque)
                try:
                    from apps.bling.services import atualizar_situacao_bling, SITUACAO_CANCELADO
                    atualizar_situacao_bling(pedido, SITUACAO_CANCELADO)
                except Exception as exc_b:
                    logger.error('Bling: erro ao cancelar pedido %s: %s', pedido.numero, exc_b)

            except Exception as exc:
                logger.error('Erro ao cancelar pedido %s: %s', pedido.numero, exc)

        msg = f'{cancelados} pedido(s) cancelado(s) por falta de pagamento ({dias} dias).'
        self.stdout.write(self.style.SUCCESS(msg))
        logger.info(msg)
