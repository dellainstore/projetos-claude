"""
Management command para emitir cupons de aniversário aos clientes que fazem
aniversário na data de referência (hoje, por padrão).

Uso:
    python manage.py emitir_cupons_aniversario --settings=core.settings.production

Parâmetros opcionais:
    --dry-run               Apenas exibe o que seria emitido, sem criar nada nem enviar e-mail
    --data-base YYYY-MM-DD  Força uma data de referência (útil para testes / reprocessamento)

Cron sugerido (diário às 8h):
    0 8 * * * cd /var/www/della-sistemas/projetos-claude/site_della && ./venv/bin/python manage.py emitir_cupons_aniversario --settings=core.settings.production >> logs/cupons_aniversario.log 2>&1

Comportamento se NÃO houver template de cupom ativo com `origem='aniversario'`
e `dias_validade_pos_emissao` preenchido: o command sai cedo com log informativo,
sem nenhum efeito colateral. Ou seja, o cron pode ficar agendado mesmo antes de o
admin cadastrar o template — quando cadastrar, os disparos começam automaticamente.
"""

import calendar
import logging
from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Emite cupons de aniversário aos clientes cujo aniversário é hoje (ou na data informada).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Apenas exibe quem receberia o cupom, sem criar nada nem enviar e-mail.',
        )
        parser.add_argument(
            '--data-base', type=str, default='',
            help='Força a data de referência no formato YYYY-MM-DD (padrão: hoje).',
        )

    def handle(self, *args, **options):
        from django.utils import timezone
        from django.contrib.auth import get_user_model
        from apps.pedidos.models import Cupom, CupomEmitido
        from apps.pedidos.emails import enviar_email_cupom_aniversario

        Cliente = get_user_model()

        dry_run = options['dry_run']
        data_base_arg = (options.get('data_base') or '').strip()

        if data_base_arg:
            try:
                data_base = datetime.strptime(data_base_arg, '%Y-%m-%d').date()
            except ValueError:
                raise CommandError('Parâmetro --data-base inválido. Use YYYY-MM-DD.')
        else:
            data_base = timezone.now().date()

        ano_atual = data_base.year

        # 1) Template ativo é pré-requisito. Sem template, sai cedo.
        template = (Cupom.objects
                    .filter(origem='aniversario', ativo=True, dias_validade_pos_emissao__isnull=False)
                    .order_by('-id')
                    .first())
        if not template:
            msg = 'Sem template de aniversário ativo. Nada a fazer.'
            self.stdout.write(self.style.WARNING(msg))
            logger.info(msg)
            return

        # 2) Determina (dia, mes) a buscar — com tratamento de 29/02 em ano não bissexto.
        # Se a data base é 28/02 e o ano não é bissexto, também emitimos para nascidos em 29/02
        # (assim ninguém perde o cupom no ano).
        dias_meses = [(data_base.month, data_base.day)]
        if data_base.month == 2 and data_base.day == 28 and not calendar.isleap(ano_atual):
            dias_meses.append((2, 29))

        # 3) Busca aniversariantes: clientes ativos, com data_nascimento preenchida,
        # cujo mês+dia bate com algum dos pares (cobre o 29/02 também).
        from django.db.models import Q
        filtro = Q()
        for mes, dia in dias_meses:
            filtro |= Q(data_nascimento__month=mes, data_nascimento__day=dia)

        # Idempotência por ano calendário: exclui quem já recebeu cupom de aniversário neste ano.
        candidatos_qs = (Cliente.objects
                         .filter(filtro)
                         .filter(is_active=True, data_nascimento__isnull=False)
                         .exclude(cupons_emitidos__cupom_template__origem='aniversario',
                                  cupons_emitidos__emitido_em__year=ano_atual))

        total = candidatos_qs.count()
        self.stdout.write(
            f'Aniversariantes elegíveis em {data_base.strftime("%d/%m/%Y")}: {total}'
        )

        if total == 0:
            msg = f'Nenhum aniversariante encontrado para {data_base.strftime("%d/%m/%Y")}.'
            self.stdout.write(msg)
            logger.info(msg)
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('-- DRY RUN: nenhum cupom será criado --'))

        enviados = 0
        erros = 0

        for cliente in candidatos_qs.iterator():
            if dry_run:
                self.stdout.write(
                    f'  [DRY] {cliente.email} — nascido em {cliente.data_nascimento.strftime("%d/%m/%Y")}'
                )
                continue

            try:
                cupom = CupomEmitido.objects.create(
                    cupom_template=template,
                    email=cliente.email,
                    cliente=cliente,
                )
                ok = enviar_email_cupom_aniversario(cupom)
                if ok:
                    enviados += 1
                    self.stdout.write(self.style.SUCCESS(f'  ✓ {cliente.email} → {cupom.codigo}'))
                else:
                    erros += 1
                    self.stdout.write(self.style.ERROR(f'  ✗ {cliente.email} — cupom criado, falha no envio'))
            except Exception as exc:
                erros += 1
                logger.exception('Falha ao emitir cupom de aniversário para %s', cliente.email)
                self.stdout.write(self.style.ERROR(f'  ✗ {cliente.email} — {exc}'))

        if dry_run:
            self.stdout.write(self.style.WARNING(f'-- Fim do DRY RUN ({total} candidatos) --'))
        else:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(
                f'Resumo: {enviados} enviados, {erros} com erro, total {total} candidatos.'
            ))
            logger.info('Emissão cupons aniversário %s: %d enviados, %d erros (de %d candidatos)',
                        data_base.isoformat(), enviados, erros, total)
