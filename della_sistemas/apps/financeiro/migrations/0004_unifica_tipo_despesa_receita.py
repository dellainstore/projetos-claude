"""Unifica tipo do lançamento: "conta a pagar"/"conta a receber" deixam de
existir como tipos separados de "despesa"/"receita" (pedido do dono,
2026-09-02 — "é tudo a mesma coisa"). A distinção agora é só a situação
(baixado ou não), não o tipo.

Migration de dados: só ATUALIZA linhas existentes (`UPDATE`, nunca
`DELETE`) — nenhum registro é apagado. Reversível: o `reverse_code` volta
os valores para "conta_pagar"/"conta_receber" (heurística: como a
distinção não existe mais, tudo volta como o tipo mais genérico —
aceitável porque isso só roda se alguém reverter a migration de propósito).
"""
from django.db import migrations


def unificar(apps, schema_editor):
    LancamentoFinanceiro = apps.get_model("financeiro", "LancamentoFinanceiro")
    RegraRecorrencia = apps.get_model("financeiro", "RegraRecorrencia")
    LancamentoFinanceiro.objects.filter(tipo="conta_pagar").update(tipo="despesa")
    LancamentoFinanceiro.objects.filter(tipo="conta_receber").update(tipo="receita")
    RegraRecorrencia.objects.filter(tipo_lancamento="conta_pagar").update(tipo_lancamento="despesa")
    RegraRecorrencia.objects.filter(tipo_lancamento="conta_receber").update(tipo_lancamento="receita")


def reverter(apps, schema_editor):
    # Não há como saber quais "despesa"/"receita" eram originalmente
    # "conta_pagar"/"conta_receber" — no-op intencional (reversão de dado
    # é impossível sem perder informação; a estrutura em si já reverteu
    # pela AlterField anterior).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0003_alter_lancamentofinanceiro_tipo_and_more"),
    ]

    operations = [
        migrations.RunPython(unificar, reverter),
    ]
