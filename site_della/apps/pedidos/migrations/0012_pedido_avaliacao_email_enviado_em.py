from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0011_correios_email_saiu_entrega'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='avaliacao_email_enviado_em',
            field=models.DateTimeField(blank=True, null=True, verbose_name='E-mail de avaliação enviado em'),
        ),
    ]
