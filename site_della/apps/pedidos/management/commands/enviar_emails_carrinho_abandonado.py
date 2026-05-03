"""
Management command para enviar e-mails de recuperação de carrinho abandonado.

Uso:
    python manage.py enviar_emails_carrinho_abandonado --settings=core.settings.production

Parâmetros opcionais:
    --horas       Quantas horas de inatividade para considerar abandonado (padrão: 1)
    --max-horas   Não envia para carrinhos mais velhos que N horas (padrão: 48)
    --dry-run     Apenas exibe o que seria enviado, sem enviar
"""

import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Envia e-mails de lembrete para clientes com carrinho abandonado'

    def add_arguments(self, parser):
        parser.add_argument(
            '--horas', type=int, default=1,
            help='Horas de inatividade para considerar o carrinho abandonado (padrão: 1)',
        )
        parser.add_argument(
            '--max-horas', type=int, default=48,
            help='Não envia para carrinhos mais velhos que N horas (padrão: 48)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Apenas exibe o que seria enviado, sem enviar e-mails',
        )

    def handle(self, *args, **options):
        from apps.pedidos.models import CarrinhoAbandonado
        from apps.pedidos.emails import enviar_email_carrinho_abandonado

        horas     = options['horas']
        max_horas = options['max_horas']
        dry_run   = options['dry_run']

        agora     = timezone.now()
        limite_min = agora - timedelta(hours=max_horas)
        limite_max = agora - timedelta(hours=horas)

        candidatos = CarrinhoAbandonado.objects.filter(
            recuperado=False,
            email_enviado=False,
            atualizado_em__gte=limite_min,
            atualizado_em__lte=limite_max,
        ).select_related('cliente')

        total = candidatos.count()
        self.stdout.write(
            f'Carrinhos abandonados elegíveis: {total} '
            f'(entre {horas}h e {max_horas}h de inatividade)'
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('-- DRY RUN: nenhum e-mail será enviado --'))

        enviados = 0
        erros    = 0

        for ca in candidatos:
            if dry_run:
                self.stdout.write(
                    f'  [DRY] {ca.email} — {ca.quantidade_itens} item(s) — R$ {ca.total}'
                )
                continue

            ok = enviar_email_carrinho_abandonado(ca)
            if ok:
                enviados += 1
                self.stdout.write(f'  ✓ E-mail enviado: {ca.email}')
            else:
                erros += 1
                self.stdout.write(self.style.ERROR(f'  ✗ Falha ao enviar: {ca.email}'))

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Concluído: {enviados} enviado(s), {erros} erro(s).'
                )
            )
