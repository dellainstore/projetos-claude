"""Vincula MetaFuncionario ao Colaborador do RH (cadastro único) em vez do
model Funcionario das metas, e remove o Funcionario.

O vínculo passa a ser pelo ID do Bling: cada Funcionario antigo (nome_bling) é
mapeado para o Colaborador com o bling_vendedor_id correspondente.
"""

import django.db.models.deletion
from django.db import migrations, models

# nome_bling do antigo Funcionario -> bling_vendedor_id (mesmo mapa do CLAUDE.md)
NOME_BLING_TO_VENDEDOR_ID = {
    "TINA DIAS": 7613793453,
    "MICHELLE ALVES FERNANDES": 15205612892,
    "SARA OLIVEIRA": 15596882226,
    "CRISLAINY SILVERIO GIACOMELLI": 7616577942,
}


def migrar_para_colaborador(apps, schema_editor):
    MetaFuncionario = apps.get_model("metas", "MetaFuncionario")
    Funcionario = apps.get_model("metas", "Funcionario")
    Colaborador = apps.get_model("rh", "Colaborador")

    por_vendedor_id = {c.bling_vendedor_id: c for c in Colaborador.objects.all() if c.bling_vendedor_id}

    for meta in MetaFuncionario.objects.all():
        func = Funcionario.objects.filter(pk=meta.funcionario_id).first()
        colab = None
        if func:
            vid = NOME_BLING_TO_VENDEDOR_ID.get((func.nome_bling or "").strip().upper())
            if vid:
                colab = por_vendedor_id.get(vid)
            if colab is None:
                # Fallback: casa pelo primeiro nome (TINA -> TINA MARIA DA COSTA DIAS)
                primeiro = (func.nome_bling or func.nome or "").strip().split(" ")[0].upper()
                if primeiro:
                    colab = next(
                        (c for c in por_vendedor_id.values()
                         if c.nome.upper().startswith(primeiro)),
                        None,
                    )
        if colab:
            meta.colaborador_id = colab.id
            meta.save(update_fields=["colaborador"])
        else:
            print(f"[migracao metas] meta {meta.pk} (funcionario {meta.funcionario_id}) "
                  f"sem colaborador correspondente -> removida")
            meta.delete()


def reverter(apps, schema_editor):
    # Sem reversão de dados (mantém o backup do banco como rede de segurança).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("metas", "0001_initial"),
        ("rh", "0011_tipobeneficio_periodoaquisitivo_abono_dias_and_more"),
    ]

    operations = [
        migrations.AlterUniqueTogether(name="metafuncionario", unique_together=set()),
        migrations.AddField(
            model_name="metafuncionario",
            name="colaborador",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="metas",
                to="rh.colaborador",
                verbose_name="Colaborador",
            ),
        ),
        migrations.RunPython(migrar_para_colaborador, reverter),
        migrations.RemoveField(model_name="metafuncionario", name="funcionario"),
        migrations.AlterField(
            model_name="metafuncionario",
            name="colaborador",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="metas",
                to="rh.colaborador",
                verbose_name="Colaborador",
            ),
        ),
        migrations.AlterModelOptions(
            name="metafuncionario",
            options={
                "ordering": ["-ano", "-mes", "colaborador__nome"],
                "verbose_name": "Meta Individual",
                "verbose_name_plural": "Metas Individuais",
            },
        ),
        migrations.AlterUniqueTogether(
            name="metafuncionario",
            unique_together={("colaborador", "ano", "mes")},
        ),
        migrations.DeleteModel(name="Funcionario"),
    ]
