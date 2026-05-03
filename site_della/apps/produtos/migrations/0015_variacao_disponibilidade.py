from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('produtos', '0014_remove_genero_produto'),
    ]

    operations = [
        migrations.AddField(
            model_name='variacao',
            name='disponibilidade',
            field=models.CharField(
                choices=[('imediata', 'Disponibilidade imediata'), ('sob_demanda', 'Sob demanda')],
                default='imediata',
                help_text='Use "disponibilidade imediata" para peças a pronta entrega e "sob demanda" para peças confeccionadas após a compra.',
                max_length=20,
                verbose_name='Disponibilidade',
            ),
        ),
        migrations.AddField(
            model_name='variacao',
            name='prazo_confeccao_dias',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text='Preencha apenas para variações sob demanda. Esse prazo será somado ao prazo do frete.',
                null=True,
                verbose_name='Prazo de confecção (dias úteis)',
            ),
        ),
    ]
