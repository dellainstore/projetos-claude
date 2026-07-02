from django.db import migrations, models

# bling_vendedor_id → canal fixo para meta individual
CANAL_POR_VENDEDOR_ID = {
    7613793453: "show_room_sp",   # TINA MARIA DA COSTA DIAS
    15205612892: "anaca",          # MICHELLE ALVES FERNANDES
    15596882226: "show_room_sp",   # SARA NATHALY SANTOS OLIVEIRA
    # CRISLAINY SILVERIO GIACOMELLI (7616577942): fica em branco — sem meta individual
}


def set_canal(apps, schema_editor):
    Colaborador = apps.get_model("rh", "Colaborador")
    for colab in Colaborador.objects.filter(bling_vendedor_id__isnull=False):
        canal = CANAL_POR_VENDEDOR_ID.get(colab.bling_vendedor_id, "")
        colab.canal_meta_individual = canal
        colab.save(update_fields=["canal_meta_individual"])


class Migration(migrations.Migration):

    dependencies = [
        ("rh", "0012_parametrosponto_data_inicio"),
    ]

    operations = [
        migrations.AddField(
            model_name="colaborador",
            name="canal_meta_individual",
            field=models.CharField(
                blank=True,
                choices=[("show_room_sp", "Show Room SP"), ("anaca", "Anacã SP")],
                default="",
                help_text="Canal cujas metas individuais alimentam. Deixe em branco se não tem meta individual (ex.: Cris).",
                max_length=20,
                verbose_name="Canal meta individual",
            ),
        ),
        migrations.RunPython(set_canal, migrations.RunPython.noop),
    ]
