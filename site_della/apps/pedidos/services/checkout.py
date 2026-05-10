"""
Serviços de suporte ao fluxo de checkout.

Separa a lógica de negócio (cálculo de preços, criação de itens) da camada HTTP
(views.py), tornando cada responsabilidade mais fácil de entender e de testar.
"""
from dataclasses import dataclass
from decimal import Decimal


class EstoqueInsuficiente(Exception):
    """Levantada quando o estoque é insuficiente para um item no momento do checkout."""


@dataclass
class ResultadoCalculo:
    subtotal: Decimal
    desconto: Decimal
    frete: Decimal
    total: Decimal
    cupom_obj: object  # instância de Cupom ou None
    vendedor_obj: object  # instância de CodigoVendedor ou None


class CalculadorPedido:
    """Calcula subtotal, desconto de cupom, frete e total de um pedido."""

    def calcular(
        self,
        subtotal: Decimal,
        cupom_codigo: str,
        cpf: str,
        valor_frete: Decimal,
        vendedor_codigo: str = '',
    ) -> ResultadoCalculo:
        from apps.pedidos.models import Cupom, CodigoVendedor  # import local evita ciclo

        cupom_obj = None
        desconto = Decimal('0')
        codigo = (cupom_codigo or '').strip().upper()
        if codigo:
            try:
                obj = Cupom.objects.get(codigo__iexact=codigo, ativo=True)
                ok, _ = obj.esta_valido(cpf=cpf)
                if ok:
                    cupom_obj = obj
                    desconto = obj.calcular_desconto(subtotal)
            except Cupom.DoesNotExist:
                pass

        vendedor_obj = None
        codigo_vendedor = (vendedor_codigo or '').strip().upper()
        if codigo_vendedor:
            try:
                vendedor_obj = CodigoVendedor.objects.get(codigo__iexact=codigo_vendedor, ativo=True)
            except CodigoVendedor.DoesNotExist:
                pass

        total = subtotal - desconto + valor_frete
        return ResultadoCalculo(
            subtotal=subtotal,
            desconto=desconto,
            frete=valor_frete,
            total=total,
            cupom_obj=cupom_obj,
            vendedor_obj=vendedor_obj,
        )


def criar_itens_pedido(pedido, cart):
    """Cria os ItemPedido e decrementa estoque atomicamente.

    Deve ser chamada dentro de um bloco transaction.atomic().
    Levanta EstoqueInsuficiente se o estoque não comportar a quantidade pedida
    — o bloco atômico externo faz rollback automático do pedido inteiro.
    """
    from decimal import Decimal
    from django.db.models import F
    from apps.pedidos.models import ItemPedido
    from apps.produtos.models import Produto, Variacao

    for item in cart:
        try:
            produto_obj = Produto.objects.get(pk=item['produto_id'])
        except Produto.DoesNotExist:
            continue

        variacao_obj = None
        if item.get('variacao_id'):
            try:
                variacao_obj = Variacao.objects.get(pk=item['variacao_id'])
            except Variacao.DoesNotExist:
                pass

        # SKU da variação tem prioridade — casa com o produto cadastrado no Bling.
        sku_item = (
            variacao_obj.sku_variacao
            if variacao_obj and variacao_obj.sku_variacao
            else produto_obj.sku
        )

        ItemPedido.objects.create(
            pedido=pedido,
            produto=produto_obj,
            variacao=variacao_obj,
            nome_produto=item['nome'],
            sku=sku_item,
            variacao_desc=item.get('variacao_desc', ''),
            preco_unitario=Decimal(item['preco']),
            quantidade=item['quantidade'],
        )

        # select_for_update evita condição de corrida quando dois clientes
        # compram o último item ao mesmo tempo.
        if variacao_obj:
            variacao_locked = Variacao.objects.select_for_update().get(pk=variacao_obj.pk)
            if variacao_locked.pronta_entrega:
                if variacao_locked.estoque < item['quantidade']:
                    raise EstoqueInsuficiente(
                        f'Estoque insuficiente para "{item["nome"]}". '
                        f'Disponível: {variacao_locked.estoque}, '
                        f'solicitado: {item["quantidade"]}.'
                    )
                Variacao.objects.filter(pk=variacao_obj.pk).update(
                    estoque=F('estoque') - item['quantidade']
                )
