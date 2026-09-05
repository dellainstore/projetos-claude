"""Testes da Fase 2 (Investimentos) — ver plano, seções 1.4 e 3."""
from datetime import date
from decimal import Decimal

from apps.financeiro.models import CategoriaFinanceira, ContaInvestimento
from apps.financeiro.services.private_label.investimentos import (
    aplicar,
    estornar_transacao,
    registrar_rendimento,
    registrar_taxa,
    resgatar,
)
from apps.financeiro.tests.test_private_label import BaseFinanceiroTestCase


class BaseInvestimentoTestCase(BaseFinanceiroTestCase):
    def setUp(self):
        super().setUp()
        self.conta_investimento = ContaInvestimento.objects.create(
            operacao=self.operacao, nome="CDB Banco X", tipo_produto="cdb",
        )
        self.categoria_receita_financeira = CategoriaFinanceira.objects.create(
            operacao=self.operacao, nome="Rendimento de aplicação", natureza="receita_financeira",
        )
        self.categoria_despesa_financeira = CategoriaFinanceira.objects.create(
            operacao=self.operacao, nome="IOF/Taxa de custódia", natureza="despesa_financeira",
        )


class AplicacaoResgateTests(BaseInvestimentoTestCase):
    def test_aplicacao_debita_conta_bancaria_e_credita_investimento(self):
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 9, 5),
        )
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.saldo_atual(), Decimal("0.00"))
        self.assertEqual(self.conta_investimento.saldo_atual(), Decimal("1000.00"))

    def test_resgate_credita_conta_bancaria_e_debita_investimento(self):
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 9, 5),
        )
        resgatar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("400.00"), data=date(2026, 9, 10),
        )
        self.assertEqual(self.conta.saldo_atual(), Decimal("400.00"))
        self.assertEqual(self.conta_investimento.saldo_atual(), Decimal("600.00"))

    def test_resgate_acima_do_saldo_e_bloqueado(self):
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("100.00"), data=date(2026, 9, 5),
        )
        with self.assertRaises(ValueError):
            resgatar(
                operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
                valor=Decimal("9999.00"), data=date(2026, 9, 10),
            )

    def test_estorno_de_aplicacao_recompoe_ambos_os_saldos(self):
        transacao = aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("500.00"), data=date(2026, 9, 5),
        )
        estornar_transacao(transacao, motivo="teste")
        self.assertEqual(self.conta.saldo_atual(), Decimal("1000.00"))
        self.assertEqual(self.conta_investimento.saldo_atual(), Decimal("0.00"))


class RendimentoTaxaTests(BaseInvestimentoTestCase):
    def test_rendimento_so_credita_o_investimento_sem_tocar_conta_bancaria(self):
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 9, 5),
        )
        saldo_conta_antes = self.conta.saldo_atual()
        registrar_rendimento(
            operacao=self.operacao, conta_investimento=self.conta_investimento,
            categoria=self.categoria_receita_financeira, valor=Decimal("15.00"), data=date(2026, 9, 20),
        )
        self.assertEqual(self.conta.saldo_atual(), saldo_conta_antes)
        self.assertEqual(self.conta_investimento.saldo_atual(), Decimal("1015.00"))

    def test_rendimento_exige_categoria_de_receita_financeira(self):
        with self.assertRaises(ValueError):
            registrar_rendimento(
                operacao=self.operacao, conta_investimento=self.conta_investimento,
                categoria=self.categoria, valor=Decimal("10.00"), data=date(2026, 9, 20),
            )

    def test_taxa_debita_o_investimento(self):
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 9, 5),
        )
        registrar_taxa(
            operacao=self.operacao, conta_investimento=self.conta_investimento,
            categoria=self.categoria_despesa_financeira, valor=Decimal("5.00"), data=date(2026, 9, 20),
        )
        self.assertEqual(self.conta_investimento.saldo_atual(), Decimal("995.00"))

    def test_taxa_exige_categoria_de_despesa_financeira(self):
        with self.assertRaises(ValueError):
            registrar_taxa(
                operacao=self.operacao, conta_investimento=self.conta_investimento,
                categoria=self.categoria_receita_financeira, valor=Decimal("5.00"), data=date(2026, 9, 20),
            )
