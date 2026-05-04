from django.core.management.base import BaseCommand
from apps.usuarios.models import Cliente
from apps.core_utils.sanitize import sanitize_name


class Command(BaseCommand):
    help = 'Normaliza nome e sobrenome de todos os clientes: primeira letra maiúscula, partículas (de, da, e…) minúsculas.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra o que seria alterado sem gravar no banco.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        clientes = Cliente.objects.all().order_by('id')
        total = clientes.count()
        alterados = 0

        for cliente in clientes:
            novo_nome = sanitize_name(cliente.nome)
            novo_sobrenome = sanitize_name(cliente.sobrenome)

            if novo_nome == cliente.nome and novo_sobrenome == cliente.sobrenome:
                continue

            alterados += 1
            if dry_run:
                self.stdout.write(
                    f'  [{cliente.pk}] {cliente.nome!r} → {novo_nome!r} | '
                    f'{cliente.sobrenome!r} → {novo_sobrenome!r}'
                )
            else:
                Cliente.objects.filter(pk=cliente.pk).update(
                    nome=novo_nome,
                    sobrenome=novo_sobrenome,
                )

        modo = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'{modo}Concluído: {alterados} de {total} clientes {"seriam " if dry_run else ""}atualizados.'
            )
        )
