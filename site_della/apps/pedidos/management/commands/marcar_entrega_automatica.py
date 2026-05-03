"""
Marca como 'entregue' pedidos com status 'enviado' há mais de N dias (padrão 7).

Uso:
    python manage.py marcar_entrega_automatica --settings=core.settings.production
    python manage.py marcar_entrega_automatica --dias 10 --dry-run

Cron sugerido (1x/dia, ex: 03:00):
    0 3 * * *  cd /var/www/della-sistemas/projetos-claude/site_della && \\
               venv/bin/python manage.py marcar_entrega_automatica \\
               --settings=core.settings.production
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Auto-marca como 'entregue' pedidos enviados há mais de N dias sem confirmação do cliente."

    def add_arguments(self, parser):
        parser.add_argument('--dias', type=int, default=7,
                            help='Dias após o envio para marcar como entregue (padrão: 7).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Mostra o que seria feito sem alterar nada.')

    def handle(self, *args, **options):
        from apps.pedidos.models import Pedido, HistoricoPedido

        dias = options['dias']
        dry  = options['dry_run']
        cutoff = timezone.now() - timedelta(days=dias)

        pendentes = []
        for p in Pedido.objects.filter(status='enviado'):
            data = p.data_envio
            if data and data <= cutoff:
                pendentes.append((p, data))

        if not pendentes:
            self.stdout.write(f'Nenhum pedido enviado há mais de {dias} dias.')
            return

        prefixo = '[DRY-RUN] ' if dry else ''
        self.stdout.write(f'{prefixo}{len(pendentes)} pedido(s) {"seriam" if dry else "serão"} marcados como entregues:')
        for p, data in pendentes:
            passados = (timezone.now() - data).days
            self.stdout.write(f'  {p.numero} — enviado há {passados} dia(s)')
            if dry:
                continue
            HistoricoPedido.objects.create(
                pedido=p,
                status_anterior=p.status,
                status_novo='entregue',
                observacao=f'Entrega automática após {passados} dia(s) do envio (sem confirmação manual).',
            )
            p.status = 'entregue'
            p.save(update_fields=['status', 'atualizado_em'])

        if dry:
            self.stdout.write(self.style.WARNING('DRY-RUN: nenhum pedido foi alterado.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'OK: {len(pendentes)} pedido(s) marcado(s) como entregue.'))
