"""
Envia todos os e-mails transacionais para um endereço de teste,
simulando um pedido real.

Uso:
    python manage.py enviar_emails_teste --email neto.giacomelli@outlook.com
    python manage.py enviar_emails_teste --email neto.giacomelli@outlook.com --pedido 2026-0001
    python manage.py enviar_emails_teste --email neto.giacomelli@outlook.com --tipo carrinho
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

SITE_URL = getattr(settings, 'SITE_URL', 'https://www.dellainstore.com')


class _CarrinhoFake:
    """Objeto que imita um CarrinhoAbandonado para renderização do template."""

    def __init__(self, email_destino):
        self.email = email_destino
        self.nome = "Neto"
        self.total = Decimal('350.00')
        self.itens_json = [
            {
                'nome': 'BODY BÁSICO ANACA',
                'variacao_desc': 'BRANCO POLAR / P',
                'quantidade': 1,
                'preco': '189.90',
                'subtotal': '189.90',
                'imagem': '',
            },
            {
                'nome': 'CALÇA WIDE LEG',
                'variacao_desc': 'PRETO / M',
                'quantidade': 1,
                'preco': '160.10',
                'subtotal': '160.10',
                'imagem': '',
            },
        ]

    @property
    def itens(self):
        return self.itens_json

    @property
    def quantidade_itens(self):
        return sum(i.get('quantidade', 1) for i in self.itens_json)

    def save(self, *args, **kwargs):
        pass  # fake — não persiste nada


class _PedidoFake:
    """Objeto que imita um Pedido real para renderização dos templates."""

    class _ItemFake:
        def __init__(self, nome, variacao_desc, quantidade, preco):
            self.nome_produto = nome
            self.variacao_desc = variacao_desc
            self.quantidade = quantidade
            self.preco_unitario = Decimal(str(preco))
            self.subtotal = self.preco_unitario * self.quantidade

    class _ItensFake:
        def __init__(self, itens):
            self._itens = itens

        def all(self):
            return self._itens

    def __init__(self, email_destino):
        self.numero = '2026-TESTE'
        self.nome_completo = "Neto Giacomelli"
        self.email = email_destino
        self.cpf = '00000000000'
        self.telefone = '11999999999'
        self.subtotal = Decimal('350.00')
        self.desconto = Decimal('0.00')
        self.frete = Decimal('25.90')
        self.total = Decimal('375.90')
        self.logradouro = 'Rua Exemplo'
        self.numero_entrega = '123'
        self.complemento = 'Apto 45'
        self.bairro = 'Jardim Paulista'
        self.cidade = 'São Paulo'
        self.estado = 'SP'
        self.cep_entrega = '01310100'
        self.codigo_rastreio = 'SQ000000000BR'
        self.transportadora = 'Correios'
        self.forma_pagamento = 'cartao_credito'
        self.parcelas = 2
        self.status = 'enviado'

        import datetime
        self.criado_em = __import__('django.utils.timezone', fromlist=['now']).now()

        self.itens = self._ItensFake([
            self._ItemFake('BODY BÁSICO ANACA', 'BRANCO POLAR / P', 1, '189.90'),
            self._ItemFake('CALÇA WIDE LEG', 'PRETO / M', 1, '160.10'),
        ])

    @property
    def link_rastreio(self):
        return f'https://www.linkcorreios.com.br/?id={self.codigo_rastreio}'


class Command(BaseCommand):
    help = 'Envia todos os e-mails transacionais para um endereço de teste.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='E-mail de destino para os testes.')
        parser.add_argument(
            '--pedido', default=None,
            help='Número de um pedido real (opcional). Se omitido, usa dados fictícios.',
        )
        parser.add_argument(
            '--tipo', default='todos',
            choices=['todos', 'confirmacao', 'pagamento', 'saiu_entrega', 'entregue', 'cancelamento', 'carrinho'],
            help='Qual e-mail enviar (padrão: todos).',
        )

    def handle(self, *args, **options):
        email = options['email']
        tipo = options['tipo']

        if options['pedido']:
            try:
                from apps.pedidos.models import Pedido
                pedido = Pedido.objects.get(numero=options['pedido'])
                pedido.email = email
                self.stdout.write(f'Usando pedido real {pedido.numero}')
            except Pedido.DoesNotExist:
                raise CommandError(f'Pedido {options["pedido"]} não encontrado.')
        else:
            pedido = _PedidoFake(email)
            self.stdout.write(f'Usando pedido fictício → {email}')

        from apps.pedidos.emails import (
            enviar_cancelamento,
            enviar_confirmacao_entrega,
            enviar_confirmacao_pagamento,
            enviar_confirmacao_pedido,
            enviar_email_carrinho_abandonado,
            enviar_saiu_para_entrega,
        )

        ca = _CarrinhoFake(email)

        envios = {
            'confirmacao':   ('Confirmação de pedido',           lambda: enviar_confirmacao_pedido(pedido)),
            'pagamento':     ('Pagamento confirmado / Em sep.',   lambda: enviar_confirmacao_pagamento(pedido)),
            'saiu_entrega':  ('Saiu para entrega',               lambda: enviar_saiu_para_entrega(pedido)),
            'entregue':      ('Entregue + avalie',               lambda: enviar_confirmacao_entrega(pedido)),
            'cancelamento':  ('Cancelamento (sem estorno)',       lambda: enviar_cancelamento(pedido, estornado=False)),
            'carrinho':      ('Carrinho abandonado',             lambda: enviar_email_carrinho_abandonado(ca)),
        }

        if tipo == 'todos':
            selecionados = list(envios.keys())
        else:
            selecionados = [tipo]

        for chave in selecionados:
            nome, fn = envios[chave]
            self.stdout.write(f'  Enviando: {nome}...', ending=' ')
            ok = fn()
            self.stdout.write(self.style.SUCCESS('OK') if ok else self.style.ERROR('FALHOU'))

        self.stdout.write(self.style.SUCCESS(f'\nConcluído. Verifique {email}'))
