from django.core.management.base import BaseCommand

from apps.motoqueiro.services.monitoramento import checar_monitoramentos_ativos


class Command(BaseCommand):
    help = (
        "Consulta a Lalamove pros monitoramentos de cotação ativos "
        "(Financeiro > Motoqueiro > Monitoramento) e avisa no Telegram quando "
        "acha o preço-alvo ou quando o horário definido na criação expira sem achar. "
        "Rodar via cron a cada 20 min."
    )

    def handle(self, *args, **options):
        resultado = checar_monitoramentos_ativos()
        self.stdout.write(self.style.SUCCESS(
            f"{resultado['verificados']} monitoramento(s) verificado(s) — "
            f"{resultado['encontrados']} encontrado(s), {resultado['expirados']} expirado(s)."
        ))
