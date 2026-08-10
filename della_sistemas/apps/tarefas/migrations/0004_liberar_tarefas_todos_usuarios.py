from django.db import migrations

# Pedido do usuário em 2026-08-10: hoje libera acesso ao módulo pra todo
# mundo já cadastrado — depois disso, quem entrar como funcionário novo
# continua opt-in via /usuarios/ (a tela sempre reconstrói o dict inteiro
# de permissoes a partir dos checkboxes marcados no formulário, então
# DEFAULT_PERMS_BY_PAPEL nunca chega a valer pra usuário criado por ali).


def liberar_tarefas_para_todos(apps, schema_editor):
    User = apps.get_model("core", "User")
    for user in User.objects.all():
        permissoes = dict(user.permissoes or {})
        tarefas = dict(permissoes.get("tarefas", {}))
        tarefas.setdefault("ver", True)
        tarefas.setdefault("criar", True)
        permissoes["tarefas"] = tarefas
        user.permissoes = permissoes
        user.save(update_fields=["permissoes"])


def reverter(apps, schema_editor):
    # Não desfaz automaticamente — revogar em massa é decisão do Super Admin
    # pela tela de usuários, não um rollback de migração.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tarefas", "0003_tarefa_editado_em_tarefaresponsavel_visto_em"),
        ("core", "0002_user_permissoes"),
    ]

    operations = [
        migrations.RunPython(liberar_tarefas_para_todos, reverter),
    ]
