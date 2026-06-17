"""
Marca como 'entregue' pedidos no status 'enviado' em dois casos:

1. Correios confirmou entrega (correios_entregue_em preenchido) há mais de DIAS_APOS_CORREIOS dias (padrão: 7).
2. Fallback: sem confirmação dos Correios, mas enviado há mais de DIAS_FALLBACK dias (padrão: 30).

Uso:
    python manage.py marcar_entrega_automatica --settings=core.settings.production
    python manage.py marcar_entrega_automatica --dias-correios 7 --dias-fallback 30 --dry-run
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Auto-marca como 'entregue' pedidos 7 dias após confirmação Correios, ou 30 dias após envio (fallback)."

    def add_arguments(self, parser):
        parser.add_argument('--dias-correios', type=int, default=7,
                            help='Dias após confirmação de entrega pelos Correios (padrão: 7).')
        parser.add_argument('--dias-fallback', type=int, default=30,
                            help='Dias após envio para marcar como entregue se Correios não confirmou (padrão: 30).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Mostra o que seria feito sem alterar nada.')

    def handle(self, *args, **options):
        from apps.pedidos.emails import enviar_confirmacao_entrega
        from apps.pedidos.models import HistoricoPedido, Pedido

        dias_correios = options['dias_correios']
        dias_fallback = options['dias_fallback']
        dry = options['dry_run']
        prefixo = '[DRY-RUN] ' if dry else ''
        agora = timezone.now()

        cutoff_correios = agora - timedelta(days=dias_correios)
        cutoff_fallback = agora - timedelta(days=dias_fallback)

        pendentes = []

        for p in Pedido.objects.filter(status='enviado', retirada_loja=False):
            # Correios ja confirmou entrega → marcado imediatamente pelo cron rastrear_pedidos_correios.
            # Este fallback cobre apenas pedidos sem confirmacao dos Correios apos DIAS_FALLBACK dias.
            if not p.correios_entregue_em:
                data_envio = p.data_envio
                if data_envio and data_envio <= cutoff_fallback:
                    motivo = f'fallback: {dias_fallback} dias após envio sem confirmacao dos Correios'
                    passados = (agora - data_envio).days
                    pendentes.append((p, motivo, passados))

        if not pendentes:
            self.stdout.write('Nenhum pedido elegível para entrega automática.')
            return

        self.stdout.write(f'{prefixo}{len(pendentes)} pedido(s) {"seriam" if dry else "serão"} marcados como entregues:')
        for p, motivo, passados in pendentes:
            self.stdout.write(f'  {p.numero} — {motivo} ({passados} dia(s))')
            if dry:
                continue

            HistoricoPedido.objects.create(
                pedido=p,
                status_anterior=p.status,
                status_novo='entregue',
                observacao=f'Entrega automática — {motivo}.',
            )
            p.status = 'entregue'
            p.save(update_fields=['status', 'atualizado_em'])

            ok = enviar_confirmacao_entrega(p)
            if not ok:
                import logging
                logging.getLogger(__name__).error('Falha ao enviar e-mail de entrega para pedido %s', p.numero)

        if dry:
            self.stdout.write(self.style.WARNING('DRY-RUN: nenhum pedido foi alterado.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'OK: {len(pendentes)} pedido(s) marcado(s) como entregue.'))
