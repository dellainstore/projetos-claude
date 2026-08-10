from django.db import migrations

COLUNAS_PADRAO = [
    ("A Fazer", 0, False),
    ("Em Andamento", 1, False),
    ("Aguardando", 2, False),
    ("Concluído", 3, True),
]


def criar_colunas_padrao(apps, schema_editor):
    ColunaStatus = apps.get_model("tarefas", "ColunaStatus")
    for nome, ordem, eh_conclusao in COLUNAS_PADRAO:
        ColunaStatus.objects.get_or_create(
            nome=nome, defaults={"ordem": ordem, "eh_conclusao": eh_conclusao},
        )


def remover_colunas_padrao(apps, schema_editor):
    ColunaStatus = apps.get_model("tarefas", "ColunaStatus")
    ColunaStatus.objects.filter(nome__in=[c[0] for c in COLUNAS_PADRAO]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tarefas", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(criar_colunas_padrao, remover_colunas_padrao),
    ]
