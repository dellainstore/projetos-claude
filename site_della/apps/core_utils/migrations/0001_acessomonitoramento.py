from django.db import migrations, models


class Migration(migrations.Migration):
    """Cria apenas a permissão core_utils.ver_monitoramento.

    O modelo é managed=False: nenhuma tabela é criada. O ContentType e a
    Permission são criados pelo post_migrate do Django.
    """

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='AcessoMonitoramento',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'verbose_name': 'Acesso ao Monitoramento',
                'verbose_name_plural': 'Acesso ao Monitoramento',
                'managed': False,
                'default_permissions': (),
                'permissions': [('ver_monitoramento', 'Pode acessar o painel de Monitoramento')],
            },
        ),
    ]
