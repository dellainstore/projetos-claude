from django.db import migrations, models


def set_superadmin_permissions(apps, schema_editor):
    """Preenche permissoes para superadmins existentes."""
    User = apps.get_model('core', 'User')
    all_perms = {
        "estoque":    {"incluir": True,  "historico": True,  "excluir": True},
        "aprovacoes": {"ver": True,       "aprovar": True},
        "precos":     {"ver": True,       "alterar": True},
        "manutencao": {"sync": True,      "rebuild": True,   "limpeza": True},
        "admin":      {"usuarios": True},
    }
    for user in User.objects.filter(papel="superadmin"):
        user.permissoes = all_perms
        user.save()


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='permissoes',
            field=models.JSONField(default=dict, verbose_name='Permissões'),
        ),
        migrations.RunPython(set_superadmin_permissions, migrations.RunPython.noop),
    ]
