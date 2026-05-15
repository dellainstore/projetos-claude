from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pagamentos', '0002_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CartaoSalvo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_pagbank', models.CharField(max_length=100, verbose_name='Token PagBank')),
                ('ultimos_4', models.CharField(max_length=4, verbose_name='Últimos 4 dígitos')),
                ('nome_titular', models.CharField(max_length=120, verbose_name='Nome no cartão')),
                ('bandeira', models.CharField(
                    choices=[
                        ('visa', 'Visa'), ('mastercard', 'Mastercard'), ('elo', 'Elo'),
                        ('amex', 'American Express'), ('hipercard', 'Hipercard'), ('outro', 'Outro'),
                    ],
                    default='outro', max_length=20, verbose_name='Bandeira',
                )),
                ('mes_expiracao', models.PositiveSmallIntegerField(verbose_name='Mês de validade')),
                ('ano_expiracao', models.PositiveSmallIntegerField(verbose_name='Ano de validade')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('cliente', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='cartoes_salvos',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Cartão salvo',
                'verbose_name_plural': 'Cartões salvos',
                'ordering': ['-criado_em'],
            },
        ),
    ]
