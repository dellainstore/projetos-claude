"""Seed inicial: operação "Private Label", categorias e formas de pagamento.

Reversível: o `reverse_code` apaga só o que este seed criou (filtrando pela
operação "private-label"), nunca um DELETE genérico da tabela inteira.
"""
from django.db import migrations

CATEGORIAS = [
    # (nome, natureza, icone)
    ("Vendas", "receita", "\U0001F4B0"),
    ("Serviços", "receita", "\U0001F6E0"),
    ("Outras receitas operacionais", "receita", "➕"),
    ("Receitas financeiras", "receita_financeira", "\U0001F4C8"),
    ("Matéria-prima", "custo", "\U0001F9F5"),
    ("Produção", "custo", "\U0001F3ED"),
    ("Fretes sobre vendas", "custo", "\U0001F69A"),
    ("Serviços terceirizados", "custo", "\U0001F477"),
    ("Embalagens", "custo", "\U0001F4E6"),
    ("Aluguel", "despesa_operacional", "\U0001F3E0"),
    ("Energia", "despesa_operacional", "⚡"),
    ("Água", "despesa_operacional", "\U0001F4A7"),
    ("Internet", "despesa_operacional", "\U0001F4F6"),
    ("Marketing", "despesa_operacional", "\U0001F4E3"),
    ("Sistemas e assinaturas", "despesa_operacional", "\U0001F4BB"),
    ("Salários", "despesa_operacional", "\U0001F465"),
    ("Encargos", "despesa_operacional", "\U0001F4CB"),
    ("Contabilidade", "despesa_operacional", "\U0001F4D2"),
    ("Impostos", "deducao", "\U0001F3DB"),
    ("Tarifas bancárias", "despesa_financeira", "\U0001F3E6"),
    ("Manutenção", "despesa_operacional", "\U0001F527"),
    ("Viagens", "despesa_operacional", "✈"),
    ("Combustível", "despesa_operacional", "⛽"),
    ("Alimentação", "despesa_operacional", "\U0001F37D"),
    ("Pró-labore", "despesa_operacional", "\U0001F464"),
    ("Despesas financeiras", "despesa_financeira", "\U0001F4C9"),
]

FORMAS_PAGAMENTO = [
    "Dinheiro", "Pix", "Débito", "Crédito", "Boleto", "Transferência", "Cheque",
]


def seed(apps, schema_editor):
    OperacaoFinanceira = apps.get_model("financeiro", "OperacaoFinanceira")
    CategoriaFinanceira = apps.get_model("financeiro", "CategoriaFinanceira")
    FormaPagamento = apps.get_model("financeiro", "FormaPagamento")

    operacao, _ = OperacaoFinanceira.objects.get_or_create(
        codigo="private-label",
        defaults={"nome": "Private Label", "status": "ativa"},
    )

    for ordem, (nome, natureza, icone) in enumerate(CATEGORIAS):
        CategoriaFinanceira.objects.get_or_create(
            operacao=operacao,
            nome=nome,
            defaults={"natureza": natureza, "icone": icone, "ordem": ordem},
        )

    for ordem, nome in enumerate(FORMAS_PAGAMENTO):
        FormaPagamento.objects.get_or_create(
            operacao=operacao,
            nome=nome,
            defaults={"ordem": ordem},
        )


def remover_seed(apps, schema_editor):
    OperacaoFinanceira = apps.get_model("financeiro", "OperacaoFinanceira")
    operacao = OperacaoFinanceira.objects.filter(codigo="private-label").first()
    if not operacao:
        return
    apps.get_model("financeiro", "CategoriaFinanceira").objects.filter(operacao=operacao).delete()
    apps.get_model("financeiro", "FormaPagamento").objects.filter(operacao=operacao).delete()
    operacao.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, remover_seed),
    ]
