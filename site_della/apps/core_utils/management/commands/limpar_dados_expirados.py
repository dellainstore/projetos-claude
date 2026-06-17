from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Remove dados expirados ou obsoletos conforme política de retenção LGPD.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Apenas mostra o que seria removido.')

    def handle(self, *args, **options):
        dry = options['dry_run']
        prefixo = '[DRY-RUN] ' if dry else ''
        agora = timezone.now()

        # 1. Códigos OTP de admin expirados
        from apps.usuarios.models import AdminCodigo
        codigos_expirados = AdminCodigo.objects.filter(expira_em__lt=agora)
        qtd = codigos_expirados.count()
        self.stdout.write(f'{prefixo}AdminCodigo expirados: {qtd}')
        if not dry and qtd:
            codigos_expirados.delete()

        # 2. Carrinhos abandonados com mais de 90 dias sem recuperação
        from apps.pedidos.models import CarrinhoAbandonado
        limite_carrinho = agora - timezone.timedelta(days=90)
        carrinhos_velhos = CarrinhoAbandonado.objects.filter(
            atualizado_em__lt=limite_carrinho,
            recuperado=False,
        )
        qtd = carrinhos_velhos.count()
        self.stdout.write(f'{prefixo}CarrinhosAbandonados >90 dias: {qtd}')
        if not dry and qtd:
            carrinhos_velhos.delete()

        # 3. Sessões Django expiradas (via django.contrib.sessions)
        try:
            from django.contrib.sessions.backends.db import SessionStore
            from django.contrib.sessions.models import Session
            sessoes_expiradas = Session.objects.filter(expire_date__lt=agora)
            qtd = sessoes_expiradas.count()
            self.stdout.write(f'{prefixo}Sessões expiradas: {qtd}')
            if not dry and qtd:
                sessoes_expiradas.delete()
        except Exception:
            pass

        self.stdout.write(self.style.SUCCESS(f'{prefixo}Limpeza concluída.'))
