"""Marca como bot (is_bot=True) sessoes historicas com comportamento nao-humano.

Os bots que falsificam User-Agent de navegador passaram pelo filtro de UA e
ficaram gravados como trafego "Direto". Este comando reclassifica retroativamente
pelos mesmos sinais comportamentais usados na coleta:

  1. Volume de paginas absurdo numa unica sessao (scraper).
  2. Rajada de sessoes criadas no mesmo minuto (farm de bot rotacionando sessao).

Nao apaga nada: so liga a flag is_bot. O painel della_sistemas passa a ignorar
essas sessoes. Para reverter, rode com --reverter (desliga a flag no periodo).

Exemplos:
  python manage.py marcar_bots_historico --dry-run --settings=core.settings.production
  python manage.py marcar_bots_historico --desde 2026-06-28 --settings=core.settings.production
"""

from datetime import datetime

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.models.functions import TruncMinute
from django.utils import timezone

from apps.analytics.models import SessaoAnalytics
from apps.analytics.services import LIMIAR_PAGINAS_BOT

# Quantas sessoes no mesmo minuto ja caracterizam rajada de bot. Calibrado sobre
# o trafego real (rajada observada: 37 sessoes no mesmo minuto as 01:29).
LIMIAR_RAJADA_MINUTO = 10


class Command(BaseCommand):
    help = 'Reclassifica sessoes historicas com comportamento de bot (is_bot=True)'

    def add_arguments(self, parser):
        parser.add_argument('--desde', type=str, default='2026-06-28',
                            help='Data inicial YYYY-MM-DD (padrao: 2026-06-28, o corte)')
        parser.add_argument('--ate', type=str, default='',
                            help='Data final YYYY-MM-DD (padrao: agora)')
        parser.add_argument('--paginas', type=int, default=LIMIAR_PAGINAS_BOT,
                            help=f'Limiar de paginas por sessao (padrao: {LIMIAR_PAGINAS_BOT})')
        parser.add_argument('--rajada', type=int, default=LIMIAR_RAJADA_MINUTO,
                            help=f'Sessoes/minuto para rajada (padrao: {LIMIAR_RAJADA_MINUTO})')
        parser.add_argument('--dry-run', action='store_true',
                            help='So mostra o que faria, sem gravar')
        parser.add_argument('--reverter', action='store_true',
                            help='Desliga is_bot no periodo (desfaz a marcacao)')

    def handle(self, *args, **opts):
        tz = timezone.get_current_timezone()
        inicio = timezone.make_aware(datetime.strptime(opts['desde'], '%Y-%m-%d'), tz)
        if opts['ate']:
            fim = timezone.make_aware(
                datetime.strptime(opts['ate'], '%Y-%m-%d').replace(hour=23, minute=59, second=59), tz
            )
        else:
            fim = timezone.now()

        no_periodo = SessaoAnalytics.objects.filter(iniciada_em__range=(inicio, fim))
        self.stdout.write(f'Periodo: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y %H:%M} '
                          f'({no_periodo.count()} sessoes)')

        if opts['reverter']:
            qs = no_periodo.filter(is_bot=True)
            n = qs.count()
            if opts['dry_run']:
                self.stdout.write(self.style.WARNING(f'[dry-run] reverteria {n} sessoes para is_bot=False'))
            else:
                qs.update(is_bot=False)
                self.stdout.write(self.style.SUCCESS(f'Revertidas {n} sessoes (is_bot=False)'))
            return

        candidatas = no_periodo.filter(is_bot=False)

        # 1) Volume de paginas
        por_volume = set(
            candidatas.filter(total_paginas__gte=opts['paginas'])
            .values_list('id', flat=True)
        )

        # 2) Rajada no mesmo minuto
        from datetime import timedelta
        minutos_bot = [
            r['m'] for r in (
                candidatas.annotate(m=TruncMinute('iniciada_em'))
                .values('m').annotate(t=Count('id'))
                .filter(t__gte=opts['rajada'])
            )
        ]
        por_rajada = set()
        for m in minutos_bot:
            # Filtra por intervalo [m, m+1min) -- comparar igualdade com o datetime
            # truncado falha por diferenca de fuso/precisao no Postgres.
            ids = candidatas.filter(
                iniciada_em__gte=m, iniciada_em__lt=m + timedelta(minutes=1)
            ).values_list('id', flat=True)
            por_rajada.update(ids)

        alvo = por_volume | por_rajada
        self.stdout.write(f'  Por volume (>= {opts["paginas"]} paginas): {len(por_volume)} sessoes')
        self.stdout.write(f'  Por rajada (>= {opts["rajada"]}/minuto): {len(por_rajada)} sessoes '
                          f'em {len(minutos_bot)} minuto(s)')
        self.stdout.write(f'  Total a marcar: {len(alvo)} sessoes')

        if not alvo:
            self.stdout.write(self.style.SUCCESS('Nada a marcar.'))
            return

        if opts['dry_run']:
            amostra = SessaoAnalytics.objects.filter(id__in=list(alvo)).order_by('-total_paginas')[:10]
            self.stdout.write('  Amostra:')
            for s in amostra:
                self.stdout.write(f'    sessao {s.id}: {s.total_paginas} paginas | '
                                  f'{s.dispositivo} | {timezone.localtime(s.iniciada_em):%d/%m %H:%M}')
            self.stdout.write(self.style.WARNING('[dry-run] nada gravado. Rode sem --dry-run para aplicar.'))
            return

        n = SessaoAnalytics.objects.filter(id__in=list(alvo)).update(is_bot=True)
        self.stdout.write(self.style.SUCCESS(f'Marcadas {n} sessoes como bot (is_bot=True).'))
