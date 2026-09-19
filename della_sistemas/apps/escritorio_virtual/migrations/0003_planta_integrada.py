"""Planta integrada: cômodos dividindo parede, corredor e portas.

A planta da `0002` eram quatro retângulos soltos no vazio. Aqui os cômodos
passam a encostar uns nos outros, um corredor de verdade (uma linha na tabela,
não uma constante no frontend) liga tudo, e as portas passam a ser deduzidas
de onde cada cômodo encosta no corredor (ver `src/environment/geometry.ts`).

Aproveita para renomear o "Showroom 2" para **Anacã**, que é o nome da loja
que ele representa.

                  520        920
                   ┌──────────┐                        y=0
                   │REFEITÓRIO│
    0        560   │          │   880           1440
    ┌──────────────┼──────────┼──────────────────┐     y=250
    │              │          │                  │
    │  SHOW ROOM   │ CORREDOR │      ANACÃ       │
    │              │          │                  │
    └──────────────┼──────────┼──────────────────┘     y=760
                   │ ENTRADA  │
                   └──────────┘                        y=900
                  560        880

Proporção 1440x900 (1,60), a mesma da imagem de referência (1,61).

Os cômodos existentes são **atualizados**, nunca recriados: renomear o slug
com `update()` preserva o id, e com ele o vínculo da loja física
(`SalaEscritorio.loja`) e a sala padrão das personagens já cadastradas
(`PersonagemEscritorio.sala_padrao`). Recriar as linhas deixaria as
personagens apontando para cômodos órfãos.
"""

from django.db import migrations

# slug antigo -> (slug novo, nome, ordem, x, y, largura, altura)
RENOMEAR = {
    "showroom-1": ("showroom", "Show Room", 1, 0, 250, 560, 510),
    "showroom-2": ("anaca", "Anacã", 2, 880, 250, 560, 510),
}

# slug -> (nome, ordem, x, y, largura, altura)
REPOSICIONAR = {
    "cafeteria": ("Refeitório", 4, 520, 0, 400, 250),
    "store-entrance": ("Entrada", 0, 560, 760, 320, 140),
}

CORREDOR = ("corredor", "Corredor", 3, 560, 250, 320, 510)

# Para o `reverse`: volta exatamente à geometria da 0002.
ANTIGO = {
    "showroom": ("showroom-1", "Showroom 1", 1, 220, 0, 320, 220),
    "anaca": ("showroom-2", "Showroom 2", 2, 560, 0, 320, 220),
    "cafeteria": ("cafeteria", "Refeitório", 3, 220, 240, 320, 180),
    "store-entrance": ("store-entrance", "Entrada", 0, 0, 240, 200, 140),
}


def aplicar(apps, schema_editor):
    Sala = apps.get_model("escritorio_virtual", "SalaEscritorio")

    for slug_antigo, (slug, nome, ordem, x, y, larg, alt) in RENOMEAR.items():
        # Aceita os dois slugs: num banco novo a 0002 já rodou com o antigo;
        # se alguém já tiver renomeado à mão, não quebra.
        Sala.objects.filter(slug__in=[slug_antigo, slug]).update(
            slug=slug, nome=nome, ordem=ordem,
            pos_x=x, pos_y=y, largura=larg, altura=alt,
        )

    for slug, (nome, ordem, x, y, larg, alt) in REPOSICIONAR.items():
        Sala.objects.filter(slug=slug).update(
            nome=nome, ordem=ordem, pos_x=x, pos_y=y, largura=larg, altura=alt,
        )

    slug, nome, ordem, x, y, larg, alt = CORREDOR
    Sala.objects.update_or_create(
        slug=slug,
        defaults={
            "nome": nome, "ordem": ordem, "ativo": True, "loja": None,
            "pos_x": x, "pos_y": y, "largura": larg, "altura": alt,
        },
    )


def reverter(apps, schema_editor):
    Sala = apps.get_model("escritorio_virtual", "SalaEscritorio")

    for slug_atual, (slug, nome, ordem, x, y, larg, alt) in ANTIGO.items():
        Sala.objects.filter(slug=slug_atual).update(
            slug=slug, nome=nome, ordem=ordem,
            pos_x=x, pos_y=y, largura=larg, altura=alt,
        )

    Sala.objects.filter(slug=CORREDOR[0]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("escritorio_virtual", "0002_salas_iniciais"),
    ]

    operations = [
        migrations.RunPython(aplicar, reverter),
    ]
