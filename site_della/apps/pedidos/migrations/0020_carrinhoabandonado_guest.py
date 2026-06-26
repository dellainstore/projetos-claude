from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0019_pedido_ga_session_id'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Remover unique_together antigo
        migrations.AlterUniqueTogether(
            name='carrinhoabandonado',
            unique_together=set(),
        ),
        # 2. Tornar cliente nullable
        migrations.AlterField(
            model_name='carrinhoabandonado',
            name='cliente',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='carrinhos_abandonados',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Cliente',
            ),
        ),
        # 3. Adicionar campo telefone
        migrations.AddField(
            model_name='carrinhoabandonado',
            name='telefone',
            field=models.CharField(blank=True, max_length=20, verbose_name='Telefone'),
        ),
        # 4. Adicionar UniqueConstraint condicional (so para clientes nao-nulos)
        migrations.AddConstraint(
            model_name='carrinhoabandonado',
            constraint=models.UniqueConstraint(
                condition=models.Q(cliente__isnull=False),
                fields=['cliente'],
                name='pedidos_carrinhoabandonado_cliente_unique',
            ),
        ),
    ]
