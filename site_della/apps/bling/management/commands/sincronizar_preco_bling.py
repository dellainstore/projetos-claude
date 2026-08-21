"""
Management command — sincroniza preço (varejo) das variações marcadas com
usa_sync_preco_bling=True.

Uso:
    python manage.py sincronizar_preco_bling --settings=core.settings.production
    python manage.py sincronizar_preco_bling --variacao-id 42 55 --settings=core.settings.production
    python manage.py sincronizar_preco_bling --dry-run --settings=core.settings.production
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Sincroniza preço varejo do Bling para variações com sync de preço ativo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--variacao-id',
            nargs='+',
            type=int,
            metavar='ID',
            help='Sincroniza apenas as variações com esses IDs (ignora usa_sync_preco_bling=False).',
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

        if ids:
            variacoes = Variacao.objects.filter(pk__in=ids, ativa=True)
            self.stdout.write(f'Modo: IDs específicos ({len(ids)} solicitados)')
        else:
            variacoes = Variacao.objects.filter(usa_sync_preco_bling=True, ativa=True)
            self.stdout.write(f'Modo: todas com sync de preço ativo ({variacoes.count()} variações)')

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
                data = api.consultar_produto(var.bling_variacao_id).get('data') or {}
                preco_bling = data.get('preco')
                if preco_bling is None:
                    self.stderr.write(self.style.WARNING(f'  AVISO {label} — Bling sem preço cadastrado'))
                    erros += 1
                    continue
                preco_bling = round(float(preco_bling), 2)
                preco_atual = float(var.preco) if var.preco is not None else None

                if preco_atual is not None and abs(preco_atual - preco_bling) < 0.005:
                    self.stdout.write(f'  =     {label} — preço já correto: {preco_bling}')
                    iguais += 1
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  OK    {label} — {var.preco} → {preco_bling}'
                        )
                    )
                    if not dry_run:
                        Variacao.objects.filter(pk=var.pk).update(preco=preco_bling)
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
