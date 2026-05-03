"""
Remove registros antigos de BlingLog para retenção operacional mínima.

Uso:
    python manage.py limpar_bling_logs --settings=core.settings.production
    python manage.py limpar_bling_logs --dias 180 --dry-run --settings=core.settings.production

Sugestão de cron diário:
    30 2 * * * /var/www/della-sistemas/projetos-claude/site_della/venv/bin/python \
               /var/www/della-sistemas/projetos-claude/site_della/manage.py \
               limpar_bling_logs --dias 180 --settings=core.settings.production
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Apaga registros antigos de BlingLog conforme política de retenção.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dias',
            type=int,
            default=180,
            help='Apaga logs com mais de X dias (padrão: 180).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra quantos logs seriam removidos sem apagar nada.',
        )

    def handle(self, *args, **options):
        from apps.bling.models import BlingLog

        dias = options['dias']
        dry_run = options['dry_run']

        if dias < 1:
            self.stderr.write(self.style.ERROR('O valor de --dias deve ser maior ou igual a 1.'))
            return

        limite = timezone.now() - timedelta(days=dias)
        antigos = BlingLog.objects.filter(criado_em__lt=limite)
        total = antigos.count()

        if total == 0:
            self.stdout.write(f'Nenhum BlingLog com mais de {dias} dias encontrado.')
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[DRY-RUN] {total} BlingLog(s) seriam removidos '
                    f'(anteriores a {limite:%d/%m/%Y %H:%M}).'
                )
            )
            return

        removidos, detalhes = antigos.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'{total} BlingLog(s) removidos com retenção de {dias} dias '
                f'(delete retornou {removidos} objeto(s): {detalhes}).'
            )
        )
        logger.info(
            'Retenção BlingLog executada: %s registro(s) removido(s) com janela de %s dias.',
            total,
            dias,
        )
