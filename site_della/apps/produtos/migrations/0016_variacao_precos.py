from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('produtos', '0015_variacao_disponibilidade'),
    ]

    operations = [
        migrations.AddField(
            model_name='variacao',
            name='preco',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Opcional. Se vazio, usa o preço geral do produto.',
                max_digits=10,
                null=True,
                verbose_name='Preço da variação',
            ),
        ),
        migrations.AddField(
            model_name='variacao',
            name='preco_promocional',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Opcional. Se vazio, não aplica promoção da variação.',
                max_digits=10,
                null=True,
                verbose_name='Preço promocional da variação',
            ),
        ),
    ]
