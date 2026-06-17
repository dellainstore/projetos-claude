"""
Cron a cada 1h (:30) — consulta a API dos Correios e atualiza pedidos.

Grupo 1 — status pagamento_confirmado ou em_separacao com codigo_rastreio preenchido:
  - 'postado': Correios confirmou que o objeto foi postado → muda para 'enviado'

Grupo 2 — status enviado com codigo_rastreio preenchido:
  - 'saiu_entrega': envia e-mail "saiu para entrega" (uma única vez por pedido)
  - 'entregue':     muda status → entregue + envia e-mail de entrega + avalie
"""
import logging

from django.core.management.base import BaseCommand

from apps.pedidos.models import HistoricoPedido, Pedido
from apps.pedidos.services.correios import detectar_evento, rastrear_objeto

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Rastreia pedidos via API dos Correios e atualiza status/e-mails automaticamente.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Simula sem salvar nada nem enviar e-mails.',
        )

    def handle(self, *args, **options):
        dry = options['dry_run']
        prefixo = '[DRY-RUN] ' if dry else ''

        # Grupo 1: aguardando confirmação de postagem (ignora retirada na loja)
        aguardando = Pedido.objects.filter(
            status__in=['pagamento_confirmado', 'em_separacao'],
            codigo_rastreio__gt='',
            retirada_loja=False,
        )
        # Grupo 2: já marcados como enviado (ignora retirada na loja)
        enviados = Pedido.objects.filter(
            status='enviado',
            codigo_rastreio__gt='',
            retirada_loja=False,
        )

        total = aguardando.count() + enviados.count()
        self.stdout.write(f'{prefixo}Rastreando {total} pedido(s) '
                          f'({aguardando.count()} aguardando postagem, {enviados.count()} enviados)...')

        postados = entregues = saiu = erros = 0

        for pedido in aguardando:
            eventos = rastrear_objeto(pedido.codigo_rastreio)
            if eventos is None:
                erros += 1
                logger.warning('Erro ao rastrear pedido %s (código %s)', pedido.numero, pedido.codigo_rastreio)
                continue

            evento = detectar_evento(eventos)
            if evento in ('postado', 'saiu_entrega', 'entregue'):
                self.stdout.write(f'{prefixo}Pedido {pedido.numero} — POSTADO (→ enviado)')
                if not dry:
                    self._marcar_enviado(pedido)
                postados += 1

        for pedido in enviados:
            eventos = rastrear_objeto(pedido.codigo_rastreio)
            if eventos is None:
                erros += 1
                logger.warning('Erro ao rastrear pedido %s (código %s)', pedido.numero, pedido.codigo_rastreio)
                continue

            evento = detectar_evento(eventos)

            if evento == 'entregue' and not pedido.correios_entregue_em:
                self.stdout.write(f'{prefixo}Pedido {pedido.numero} — ENTREGUE')
                if not dry:
                    self._marcar_entregue_correios(pedido)
                entregues += 1

            elif evento == 'saiu_entrega' and not pedido.correios_email_saiu_entrega:
                self.stdout.write(f'{prefixo}Pedido {pedido.numero} — SAIU PARA ENTREGA')
                if not dry:
                    self._enviar_saiu_entrega(pedido)
                saiu += 1

        self.stdout.write(
            f'{prefixo}Concluído: {postados} marcados enviados, '
            f'{saiu} e-mails "saiu", {entregues} entregas Correios registradas (aguardam 7 dias), '
            f'{erros} erros.'
        )

    def _marcar_enviado(self, pedido):
        HistoricoPedido.objects.create(
            pedido=pedido,
            status_anterior=pedido.status,
            status_novo='enviado',
            observacao='Postagem confirmada automaticamente via API dos Correios.',
        )
        pedido.status = 'enviado'
        pedido.save(update_fields=['status', 'atualizado_em'])
        logger.info('Pedido %s marcado como enviado via Correios.', pedido.numero)
        from apps.pedidos.emails import enviar_notificacao_envio
        ok = enviar_notificacao_envio(pedido)
        if not ok:
            logger.error('Falha ao enviar e-mail de envio para pedido %s', pedido.numero)

    def _marcar_entregue_correios(self, pedido):
        """Correios confirmou entrega: muda para entregue imediatamente e envia e-mail."""
        from django.utils import timezone
        from apps.pedidos.emails import enviar_confirmacao_entrega
        pedido.correios_entregue_em = timezone.now()
        pedido.status = 'entregue'
        pedido.save(update_fields=['correios_entregue_em', 'status', 'atualizado_em'])
        HistoricoPedido.objects.create(
            pedido=pedido,
            status_anterior='enviado',
            status_novo='entregue',
            observacao='Entrega confirmada automaticamente via API dos Correios.',
        )
        logger.info('Pedido %s marcado como entregue via Correios.', pedido.numero)
        ok = enviar_confirmacao_entrega(pedido)
        if not ok:
            logger.error('Falha ao enviar e-mail de entrega para pedido %s', pedido.numero)

    def _enviar_saiu_entrega(self, pedido):
        from apps.pedidos.emails import enviar_saiu_para_entrega

        ok = enviar_saiu_para_entrega(pedido)
        if ok:
            pedido.correios_email_saiu_entrega = True
            pedido.save(update_fields=['correios_email_saiu_entrega', 'atualizado_em'])
        else:
            logger.error('Falha ao enviar e-mail "saiu para entrega" para pedido %s', pedido.numero)
