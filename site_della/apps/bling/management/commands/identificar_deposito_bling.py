"""
Management command — lista os depósitos do Bling com ID e nome.

Uso:
    python manage.py identificar_deposito_bling --settings=core.settings.production

Após rodar, copie o ID do "Show Room - Della" e adicione no .env:
    BLING_DEPOSITO_ID=XXXXXXXXXX
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Lista depósitos do Bling com ID e nome para identificar o Show Room - Della.'

    def handle(self, *args, **options):
        from apps.bling.api import BlingAPI, BlingAPIError
        from django.conf import settings as django_settings

        deposito_atual = str(getattr(django_settings, 'BLING_DEPOSITO_ID', '') or '').strip()

        try:
            api = BlingAPI()
            depositos = api.listar_depositos()
        except BlingAPIError as exc:
            if exc.status_code == 403:
                self.stderr.write(self.style.ERROR(
                    'Sem permissão para acessar depósitos (403).\n'
                    'Passos:\n'
                    '  1. Acesse developer.bling.com.br → seu app → Permissões\n'
                    '  2. Adicione o módulo "Depósitos" (leitura)\n'
                    '  3. Salve e acesse /bling/autorizar/ para re-autorizar\n'
                    '  4. Rode este comando novamente'
                ))
            else:
                self.stderr.write(self.style.ERROR(f'Erro Bling: {exc}'))
            return
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'Erro inesperado: {exc}'))
            return

        if not depositos:
            self.stdout.write('Nenhum depósito encontrado.')
            return

        self.stdout.write(f'\n{"ID":<15} {"Padrão":<8} Nome')
        self.stdout.write('-' * 55)
        for d in depositos:
            dep_id   = str(d.get('id', ''))
            nome     = d.get('descricao', '') or d.get('nome', '')
            padrao   = '✓ SIM' if d.get('padrao') or d.get('descricao', '').lower() == deposito_atual else ''

            marcador = ''
            if dep_id == deposito_atual:
                marcador = ' ← CONFIGURADO'

            linha = f'{dep_id:<15} {padrao:<8} {nome}{marcador}'
            if dep_id == deposito_atual:
                self.stdout.write(self.style.SUCCESS(linha))
            else:
                self.stdout.write(linha)

        self.stdout.write('')
        if deposito_atual:
            self.stdout.write(f'BLING_DEPOSITO_ID atual: {deposito_atual}')
        else:
            self.stdout.write(self.style.WARNING(
                'BLING_DEPOSITO_ID não configurado.\n'
                'Copie o ID do "Show Room - Della" acima e adicione no .env:\n'
                '  BLING_DEPOSITO_ID=XXXXXXXXXX'
            ))
