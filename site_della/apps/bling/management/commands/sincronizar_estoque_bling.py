"""
Management command — sincroniza estoque das variações marcadas com usa_sync_bling=True.

Uso:
    python manage.py sincronizar_estoque_bling --settings=core.settings.production
    python manage.py sincronizar_estoque_bling --variacao-id 42 55 --settings=core.settings.production
    python manage.py sincronizar_estoque_bling --dry-run --settings=core.settings.production
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Sincroniza estoque (saldoVirtualDisponivel) do Bling para variações com sync ativo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--variacao-id',
            nargs='+',
            type=int,
            metavar='ID',
            help='Sincroniza apenas as variações com esses IDs (ignora usa_sync_bling=False).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Consulta o Bling mas não salva nada no banco.',
        )

    def handle(self, *args, **options):
        from apps.produtos.models import Variacao
        from apps.bling.api import BlingAPI, BlingAPIError

        dry_run = options['dry_run']
        ids = options.get('variacao_id')

        from django.conf import settings as django_settings
        deposito_id = str(getattr(django_settings, 'BLING_DEPOSITO_ID', '') or '').strip()
        if deposito_id:
            self.stdout.write(f'Depósito: {deposito_id} (Show Room - D\'ella)')
        else:
            self.stdout.write(self.style.WARNING(
                'BLING_DEPOSITO_ID não configurado — somando todos os depósitos.'
            ))

        if ids:
            variacoes = Variacao.objects.filter(pk__in=ids, ativa=True)
            self.stdout.write(f'Modo: IDs específicos ({len(ids)} solicitados)')
        else:
            variacoes = Variacao.objects.filter(usa_sync_bling=True, ativa=True)
            self.stdout.write(f'Modo: todas com sync ativo ({variacoes.count()} variações)')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN ativo — nenhuma alteração será salva.'))

        try:
            api = BlingAPI()
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'Não foi possível conectar ao Bling: {exc}'))
            return

        atualizadas = sem_id = iguais = erros = 0

        for var in variacoes:
            label = f'Variação {var.pk} ({var})'

            if not var.bling_variacao_id:
                self.stdout.write(f'  SKIP  {label} — sem bling_variacao_id')
                sem_id += 1
                continue

            try:
                data = api.consultar_estoque_produto(var.bling_variacao_id)
                items = data.get('data') or []
                depositos_produto = (items[0].get('depositos') or []) if items else []
                if deposito_id:
                    depositos_filtrados = [
                        d for d in depositos_produto
                        if str(d.get('id', '')) == deposito_id
                    ]
                    if not depositos_filtrados:
                        self.stderr.write(
                            self.style.WARNING(
                                f'  AVISO {label} — depósito {deposito_id} não encontrado. '
                                f'IDs disponíveis: {[d.get("id") for d in depositos_produto]}'
                            )
                        )
                else:
                    depositos_filtrados = depositos_produto
                saldo = max(0, int(sum(
                    d.get('saldoVirtual', 0) or 0
                    for d in depositos_filtrados
                )))

                if var.estoque == saldo:
                    self.stdout.write(f'  =     {label} — estoque já correto: {saldo}')
                    iguais += 1
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  OK    {label} — {var.estoque} → {saldo}'
                        )
                    )
                    if not dry_run:
                        Variacao.objects.filter(pk=var.pk).update(estoque=saldo)
                    atualizadas += 1

            except BlingAPIError as exc:
                self.stderr.write(
                    self.style.ERROR(f'  ERRO  {label} (bling_id={var.bling_variacao_id}): {exc}')
                )
                erros += 1
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f'  ERRO  {label}: {exc}'))
                erros += 1

        sufixo = ' (dry-run)' if dry_run else ''
        self.stdout.write(
            f'\nConcluído{sufixo}: '
            f'{atualizadas} atualizadas, {iguais} inalteradas, '
            f'{sem_id} sem ID, {erros} erros.'
        )
