"""Backfill: liga carrinhos ja marcados como recuperados ao pedido que os gerou.

Ate 2026-07-28 o checkout marcava `recuperado=True` na criacao do pedido, mesmo
sem pagamento (PIX gerado e nao pago aparecia como "recuperado"). Aqui cada
carrinho recuperado e ligado ao pedido mais provavel (mesmo e-mail, criado a
partir da criacao do carrinho) e `recuperado` passa a refletir o pagamento real.
"""

from django.db import migrations

STATUS_PAGOS = (
    'pagamento_confirmado', 'em_separacao', 'pronto_retirada', 'enviado', 'entregue',
)


def backfill(apps, schema_editor):
    CarrinhoAbandonado = apps.get_model('pedidos', 'CarrinhoAbandonado')
    Pedido = apps.get_model('pedidos', 'Pedido')

    for ca in CarrinhoAbandonado.objects.filter(recuperado=True, pedido__isnull=True):
        pedido = (
            Pedido.objects
            .filter(email__iexact=ca.email, criado_em__gte=ca.criado_em)
            .order_by('criado_em')
            .first()
        )
        if pedido is None:
            # Sem pedido correspondente (e-mail do checkout diferente do
            # carrinho, pedido apagado): mantem como esta, sem inventar vinculo.
            continue
        ca.pedido = pedido
        ca.recuperado = pedido.status in STATUS_PAGOS
        ca.save(update_fields=['pedido', 'recuperado'])


def reverter(apps, schema_editor):
    CarrinhoAbandonado = apps.get_model('pedidos', 'CarrinhoAbandonado')
    CarrinhoAbandonado.objects.filter(pedido__isnull=False).update(pedido=None)


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0021_carrinhoabandonado_pedido_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, reverter),
    ]
