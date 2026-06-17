from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conteudo', '0013_alter_configuracaoloja_options_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TarjaFrase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('texto', models.CharField(
                    help_text='Ex: Frete grátis acima de R$ 500 · Parcelamento em até 10x',
                    max_length=100,
                    verbose_name='Texto',
                )),
                ('ativa', models.BooleanField(default=True, verbose_name='Ativa')),
                ('ordem', models.PositiveSmallIntegerField(
                    default=0,
                    help_text='Menor número aparece primeiro.',
                    verbose_name='Ordem',
                )),
            ],
            options={
                'verbose_name': 'Tarja — Frase',
                'verbose_name_plural': 'Tarja — Frases',
                'ordering': ['ordem', 'id'],
            },
        ),
    ]
