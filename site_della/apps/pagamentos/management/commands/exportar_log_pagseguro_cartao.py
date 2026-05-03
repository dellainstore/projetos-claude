import json
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Exporta um log de homologação do PagSeguro para um pedido pago com cartão.'

    def add_arguments(self, parser):
        parser.add_argument('pedido_numero', help='Número do pedido, ex: DI-2026-ABC123')
        parser.add_argument(
            '--arquivo',
            default='',
            help='Caminho opcional do JSON de saída. Padrão: logs/pagseguro_cartao_<pedido>.json',
        )

    def handle(self, *args, **options):
        from apps.pedidos.models import Pedido
        from apps.pagamentos.services.pagseguro import _base_url, consultar_ordem, montar_payload_ordem_cartao

        pedido_numero = options['pedido_numero'].strip()
        try:
            pedido = Pedido.objects.get(numero=pedido_numero)
        except Pedido.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'Pedido não encontrado: {pedido_numero}'))
            return

        if pedido.forma_pagamento != 'cartao_credito':
            self.stderr.write(self.style.ERROR(f'O pedido {pedido_numero} não é de cartão de crédito.'))
            return

        if not pedido.gateway_id:
            self.stderr.write(self.style.ERROR(f'O pedido {pedido_numero} não possui gateway_id.'))
            return

        response_json = consultar_ordem(pedido.gateway_id)
        if not response_json:
            self.stderr.write(self.style.ERROR(f'Não foi possível consultar a ordem {pedido.gateway_id} no PagSeguro.'))
            return

        payload = montar_payload_ordem_cartao(
            pedido,
            encrypted_card='[REDACTED_ENCRYPTED_CARD]',
            parcelas=pedido.parcelas or 1,
        )

        export = {
            'ambiente': 'sandbox' if 'sandbox.' in _base_url() else 'production',
            'metodo_pagamento': 'CREDIT_CARD',
            'endpoint': 'POST /orders',
            'pedido_numero': pedido.numero,
            'request': payload,
            'response': response_json,
        }

        base_dir = Path(pedido._meta.app_config.path).resolve().parents[2]
        arquivo = options['arquivo'].strip()
        destino = Path(arquivo).expanduser() if arquivo else base_dir / 'logs' / f'pagseguro_cartao_{pedido.numero}.json'
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding='utf-8')

        self.stdout.write(self.style.SUCCESS(f'Log exportado em: {destino}'))
        self.stdout.write(f'Order ID: {pedido.gateway_id}')
