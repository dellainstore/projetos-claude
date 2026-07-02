# Generated manually on 2026-06-28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0005_colaborador_recebe_comissao_colaborador_recebe_vt_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='colaborador',
            name='na_folha',
            field=models.BooleanField(default=True, help_text='Desmarque para quem fica só no cadastro e não entra na folha (resumida nem detalhada) — ex.: CEO.'),
        ),
        migrations.AddField(
            model_name='eventofolha',
            name='natureza',
            field=models.CharField(choices=[('provento', 'Provento'), ('desconto', 'Desconto')], default='provento', max_length=10),
        ),
        migrations.AddField(
            model_name='lancamentorecorrente',
            name='natureza',
            field=models.CharField(choices=[('provento', 'Provento'), ('desconto', 'Desconto')], default='provento', max_length=10),
        ),
    ]
