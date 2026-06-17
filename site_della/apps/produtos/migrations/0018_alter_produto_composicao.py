from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('produtos', '0017_alter_produtoimagem_options_produto_cor_principal_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='produto',
            name='composicao',
            field=models.TextField(blank=True, max_length=2000, verbose_name='Composição/Material'),
        ),
    ]
