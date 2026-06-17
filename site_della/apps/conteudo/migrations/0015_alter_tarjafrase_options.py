from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('conteudo', '0014_tarjafrase'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='tarjafrase',
            options={
                'ordering': ['ordem', 'id'],
                'verbose_name': 'Tarja (Frase)',
                'verbose_name_plural': 'Tarja (Frases)',
            },
        ),
    ]
