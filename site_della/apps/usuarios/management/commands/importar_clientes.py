"""
Management command para importar clientes do site antigo.

Formato esperado do CSV (com cabeçalho):
nome,email,telefone,cpf,data_nascimento,cep,logradouro,numero,complemento,bairro,cidade,estado

- data_nascimento: DD/MM/AAAA ou AAAA-MM-DD (ambos aceitos)
- cpf: com ou sem formatação (000.000.000-00 ou 00000000000)
- cep: com ou sem traço

Uso:
    python manage.py importar_clientes clientes.csv --settings=core.settings.production
    python manage.py importar_clientes clientes.csv --dry-run  # apenas simula, não salva
"""

import csv
import re
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from apps.usuarios.models import Cliente, Endereco
from apps.core_utils.sanitize import sanitize_phone


class Command(BaseCommand):
    help = 'Importa clientes do site antigo via CSV'

    def add_arguments(self, parser):
        parser.add_argument('arquivo', type=str, help='Caminho para o arquivo CSV')
        parser.add_argument('--dry-run', action='store_true', help='Simula sem salvar no banco')

    def handle(self, *args, **options):
        arquivo = options['arquivo']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('=== MODO DRY-RUN: nenhum dado será salvo ===\n'))

        criados = 0
        ja_existia = 0
        erros = 0

        # Detecta encoding e delimitador automaticamente
        encoding = self._detectar_encoding(arquivo)
        delimitador = self._detectar_delimitador(arquivo, encoding)
        self.stdout.write(f'  Encoding: {encoding} | Delimitador: "{delimitador}"\n')

        try:
            with open(arquivo, newline='', encoding=encoding) as f:
                reader = csv.DictReader(f, delimiter=delimitador)
                for i, row in enumerate(reader, start=2):  # linha 2 = primeira de dados
                    resultado = self._processar_linha(i, row, dry_run)
                    if resultado == 'criado':
                        criados += 1
                    elif resultado == 'existia':
                        ja_existia += 1
                    else:
                        erros += 1
        except FileNotFoundError:
            raise CommandError(f'Arquivo não encontrado: {arquivo}')
        except Exception as e:
            raise CommandError(f'Erro ao ler o arquivo: {e}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'✔ Criados:     {criados}'))
        self.stdout.write(self.style.WARNING(f'— Já existiam: {ja_existia}'))
        if erros:
            self.stdout.write(self.style.ERROR(f'✖ Erros:       {erros}'))

    def _detectar_encoding(self, arquivo):
        for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
            try:
                with open(arquivo, encoding=enc) as f:
                    f.read()
                return enc
            except UnicodeDecodeError:
                continue
        return 'latin-1'

    def _detectar_delimitador(self, arquivo, encoding):
        with open(arquivo, encoding=encoding) as f:
            primeira_linha = f.readline()
        return ';' if primeira_linha.count(';') > primeira_linha.count(',') else ','

    def _processar_linha(self, linha, row, dry_run):
        email = (row.get('email') or '').strip().lower()
        nome_completo = (row.get('nome') or '').strip()
        telefone = (row.get('telefone') or '').strip()
        cpf_raw = (row.get('cpf') or '').strip()
        data_nasc_raw = (row.get('data_nascimento') or '').strip()
        cep = re.sub(r'\D', '', (row.get('cep') or '').strip())
        logradouro = (row.get('logradouro') or '').strip()
        numero = (row.get('numero') or '').strip()
        complemento = (row.get('complemento') or '').strip()
        bairro = (row.get('bairro') or '').strip()
        cidade = (row.get('cidade') or '').strip()
        estado = (row.get('estado') or '').strip().upper()[:2]

        if not email:
            self.stdout.write(self.style.ERROR(f'  Linha {linha}: e-mail vazio — ignorada'))
            return 'erro'

        # CPF: remove formatação
        cpf = re.sub(r'\D', '', cpf_raw)

        # Data de nascimento
        data_nascimento = None
        if data_nasc_raw:
            # Remove parte horária se presente (ex: "05/15/1981 00:00:00")
            data_nasc_raw = data_nasc_raw.split(' ')[0].strip()
            for fmt in ('%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
                try:
                    data_nascimento = datetime.strptime(data_nasc_raw, fmt).date()
                    break
                except ValueError:
                    continue
            if data_nascimento is None:
                self.stdout.write(self.style.WARNING(
                    f'  Linha {linha}: data_nascimento "{data_nasc_raw}" não reconhecida — ignorada'
                ))

        # Verifica se e-mail já existe
        if Cliente.objects.filter(email=email).exists():
            self.stdout.write(f'  Linha {linha}: {email} já existe — ignorado')
            return 'existia'

        # Divide nome completo
        partes = nome_completo.split()
        nome = partes[0] if partes else 'Cliente'
        sobrenome = ' '.join(partes[1:]) if len(partes) > 1 else ''

        # Telefone sanitizado
        tel_sanitizado = sanitize_phone(telefone) if telefone else ''

        if dry_run:
            self.stdout.write(
                f'  [DRY] Linha {linha}: criaria {email} ({nome} {sobrenome})'
            )
            return 'criado'

        try:
            cliente = Cliente(
                email=email,
                nome=nome,
                sobrenome=sobrenome,
                cpf=cpf,
                telefone=tel_sanitizado,
                data_nascimento=data_nascimento,
                precisa_ativar=True,
            )
            cliente.set_unusable_password()
            cliente.save()

            # Endereço
            if cep and logradouro and cidade and estado:
                Endereco.objects.create(
                    cliente=cliente,
                    cep=cep,
                    logradouro=logradouro,
                    numero=numero or 'S/N',
                    complemento=complemento,
                    bairro=bairro,
                    cidade=cidade,
                    estado=estado,
                    principal=True,
                )

            self.stdout.write(self.style.SUCCESS(f'  ✔ Linha {linha}: {email} criado'))
            return 'criado'

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✖ Linha {linha}: {email} — erro: {e}'))
            return 'erro'
