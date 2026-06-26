from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='RelatorioSemanal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('semana_inicio', models.DateField(verbose_name='Inicio da semana')),
                ('semana_fim', models.DateField(verbose_name='Fim da semana')),
                ('gerado_em', models.DateTimeField(auto_now_add=True, verbose_name='Gerado em')),
                ('arquivo', models.CharField(max_length=300, verbose_name='Caminho do PDF (relativo a MEDIA_ROOT)')),
            ],
            options={
                'verbose_name': 'Relatorio Semanal',
                'verbose_name_plural': 'Relatorios Semanais',
                'ordering': ['-semana_inicio'],
            },
        ),
    ]
