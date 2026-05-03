import json
from pathlib import Path

import requests
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Cria uma ordem PIX no PagSeguro/PagBank e exporta request/response reais para homologação.'

    def add_arguments(self, parser):
        parser.add_argument('pedido_numero', help='Número do pedido a usar como base, ex: DI-2026-ABC123')
        parser.add_argument(
            '--arquivo',
            default='',
            help='Caminho opcional do JSON de saída. Padrão: logs/pagseguro_pix_<pedido>.json',
        )

    def handle(self, *args, **options):
        from apps.pedidos.models import Pedido
        from apps.pagamentos.services.pagseguro import (
            _base_url,
            _headers,
            montar_payload_ordem_pix,
        )

        pedido_numero = options['pedido_numero'].strip()
        try:
            pedido = Pedido.objects.get(numero=pedido_numero)
        except Pedido.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'Pedido não encontrado: {pedido_numero}'))
            return

        payload = montar_payload_ordem_pix(pedido)
        url = f'{_base_url()}/orders'

        try:
            response = requests.post(url, json=payload, headers=_headers(), timeout=30)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'Falha ao chamar a API PagSeguro: {exc}'))
            return

        try:
            response_json = response.json() if response.text else {}
        except ValueError:
            response_json = {'raw_text': response.text}

        if not response.ok:
            self.stderr.write(
                self.style.ERROR(
                    f'PagSeguro respondeu HTTP {response.status_code}: {json.dumps(response_json, ensure_ascii=False)[:500]}'
                )
            )
            return

        order_id = response_json.get('id', '')
        if order_id:
            pedido.gateway = 'pagseguro'
            pedido.gateway_id = order_id
            pedido.save(update_fields=['gateway', 'gateway_id'])

        export = {
            'ambiente': 'sandbox' if 'sandbox.' in _base_url() else 'production',
            'metodo_pagamento': 'PIX',
            'endpoint': 'POST /orders',
            'pedido_numero': pedido.numero,
            'request': payload,
            'response': response_json,
        }

        base_dir = Path(pedido._meta.app_config.path).resolve().parents[2]
        arquivo = options['arquivo'].strip()
        if arquivo:
            destino = Path(arquivo).expanduser()
        else:
            destino = base_dir / 'logs' / f'pagseguro_pix_{pedido.numero}.json'

        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding='utf-8')

        self.stdout.write(self.style.SUCCESS(f'Log exportado em: {destino}'))
        self.stdout.write(f'Order ID: {order_id or "(sem id)"}')
