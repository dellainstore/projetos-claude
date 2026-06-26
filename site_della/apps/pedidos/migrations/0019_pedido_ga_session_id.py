from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0018_pedido_capi_purchase_enviado_pedido_fbclid_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='ga_session_id',
            field=models.CharField(
                blank=True,
                max_length=50,
                verbose_name='GA4 session_id',
                help_text=(
                    'ID da sessao GA4 (cookie _ga_<stream>) capturado no checkout. '
                    'Necessario para o Measurement Protocol atribuir o purchase '
                    'a uma sessao e ao canal de origem correto.'
                ),
            ),
        ),
    ]
