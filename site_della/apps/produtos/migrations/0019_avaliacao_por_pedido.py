from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0012_pedido_avaliacao_email_enviado_em'),
        ('produtos', '0018_alter_produto_composicao'),
    ]

    operations = [
        migrations.AddField(
            model_name='avaliacao',
            name='nota_experiencia',
            field=models.PositiveSmallIntegerField(blank=True, choices=[(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)], null=True, verbose_name='Experiência da compra'),
        ),
        migrations.AddField(
            model_name='avaliacao',
            name='nota_produtos',
            field=models.PositiveSmallIntegerField(blank=True, choices=[(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)], null=True, verbose_name='Produtos comprados'),
        ),
        migrations.AddField(
            model_name='avaliacao',
            name='pedido',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='avaliacao_compra', to='pedidos.pedido', verbose_name='Pedido'),
        ),
    ]
