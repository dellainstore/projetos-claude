"""Salas iniciais do cenário + vínculo com as lojas físicas.

Migration de DADOS, separada e reversível. Não cria personagem nenhuma: quem
aparece no escritório é decisão do gestor, não da migration.

O vínculo loja -> sala é resolvido AQUI, uma única vez, por nome exato da
loja, e só quando há exatamente uma loja com aquele nome. Em runtime a
resolução passa a ser por chave estrangeira (ver `services/salas.py`), nunca
por texto. Ids de produção não são presumidos: se a loja não existir neste
banco (dev, teste, CI), a sala é criada sem vínculo e o gestor liga depois.
"""

from django.db import migrations

SALAS = [
    # slug,             nome,          ordem, loja (nome exato) , pos_x, pos_y, larg, alt
    ("store-entrance",  "Entrada",         0, None,               0,   240, 200, 140),
    ("showroom-1",      "Showroom 1",      1, "Show Room SP",     220,   0, 320, 220),
    ("showroom-2",      "Showroom 2",      2, "Loja Anacã",       560,   0, 320, 220),
    ("cafeteria",       "Refeitório",      3, None,               220, 240, 320, 180),
]


def criar_salas(apps, schema_editor):
    SalaEscritorio = apps.get_model("escritorio_virtual", "SalaEscritorio")
    LocalEmpresa = apps.get_model("rh", "LocalEmpresa")

    for slug, nome, ordem, nome_loja, x, y, larg, alt in SALAS:
        loja = None
        if nome_loja:
            candidatas = list(LocalEmpresa.objects.filter(nome=nome_loja)[:2])
            # Só vincula quando não há ambiguidade e a loja ainda não está
            # ligada a outra sala (o campo é OneToOne).
            if len(candidatas) == 1:
                ja_usada = SalaEscritorio.objects.filter(loja_id=candidatas[0].pk).exists()
                if not ja_usada:
                    loja = candidatas[0]

        SalaEscritorio.objects.update_or_create(
            slug=slug,
            defaults={
                "nome": nome,
                "ordem": ordem,
                "ativo": True,
                "loja": loja,
                "pos_x": x,
                "pos_y": y,
                "largura": larg,
                "altura": alt,
            },
        )


def remover_salas(apps, schema_editor):
    """Remove apenas as salas criadas por esta migration (pelos slugs)."""
    SalaEscritorio = apps.get_model("escritorio_virtual", "SalaEscritorio")
    SalaEscritorio.objects.filter(slug__in=[s[0] for s in SALAS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("escritorio_virtual", "0001_initial"),
        ("rh", "0020_vtvalorvigencia"),
    ]

    operations = [
        migrations.RunPython(criar_salas, remover_salas),
    ]
