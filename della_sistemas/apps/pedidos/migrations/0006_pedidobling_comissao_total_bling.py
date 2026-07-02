from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0005_pedidobling_vendedor_id_pedidobling_vendedor_nome"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedidobling",
            name="comissao_total_bling",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True
            ),
        ),
    ]
