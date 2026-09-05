"""Testes do DRE gerencial (Fase 1C) — ver plano, seções 16 e 18."""
from datetime import date
from decimal import Decimal

from apps.financeiro.models import CategoriaFinanceira, CartaoCredito
from apps.financeiro.services.private_label.baixas import dar_baixa
from apps.financeiro.services.private_label.cartoes import lancar_compra_cartao
from apps.financeiro.services.private_label.dre import calcular_dre_ano, calcular_dre_mes
from apps.financeiro.services.private_label.investimentos import aplicar, registrar_rendimento
from apps.financeiro.services.private_label.lancamentos import criar_lancamento
from apps.financeiro.services.private_label.transferencias import transferir
from apps.financeiro.tests.test_private_label import BaseFinanceiroTestCase


class DreCompetenciaTests(BaseFinanceiroTestCase):
    def test_receita_e_despesa_entram_pela_competencia_nao_pela_baixa(self):
        criar_lancamento(
            operacao=self.operacao, tipo="receita", descricao="Venda de setembro",
            valor_original=Decimal("1000.00"), data_competencia=date(2026, 9, 15),
            primeiro_vencimento=date(2026, 10, 5), categoria=self.categoria_receita,
        )
        dre_setembro = calcular_dre_mes(self.operacao, 2026, 9)
        dre_outubro = calcular_dre_mes(self.operacao, 2026, 10)
        self.assertEqual(dre_setembro["receita_bruta"], Decimal("1000.00"))
        self.assertEqual(dre_outubro["receita_bruta"], Decimal("0.00"))

    def test_lancamento_cancelado_nao_entra_no_dre(self):
        from apps.financeiro.services.private_label.lancamentos import cancelar_lancamento
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Vai cancelar",
            valor_original=Decimal("200.00"), data_competencia=date(2026, 9, 5),
            primeiro_vencimento=date(2026, 9, 5), categoria=self.categoria,
        )
        cancelar_lancamento(lancamento)
        dre = calcular_dre_mes(self.operacao, 2026, 9)
        self.assertEqual(dre["totais"]["despesa_operacional"], Decimal("0.00"))

    def test_transferencia_nunca_aparece_no_dre(self):
        transferir(operacao=self.operacao, conta_origem=self.conta, conta_destino=self.conta2,
                   valor=Decimal("300.00"), data=date(2026, 9, 5))
        dre = calcular_dre_mes(self.operacao, 2026, 9)
        total = sum(dre["totais"].values())
        self.assertEqual(total, Decimal("0.00"))

    def test_categoria_fora_do_dre_e_ignorada(self):
        categoria_fora = CategoriaFinanceira.objects.create(
            operacao=self.operacao, nome="Movimentação interna", natureza="fora_do_dre",
        )
        criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Fora do DRE",
            valor_original=Decimal("50.00"), data_competencia=date(2026, 9, 5),
            primeiro_vencimento=date(2026, 9, 5), categoria=categoria_fora,
        )
        dre = calcular_dre_mes(self.operacao, 2026, 9)
        total = sum(dre["totais"].values())
        self.assertEqual(total, Decimal("0.00"))


class DreCartaoTests(BaseFinanceiroTestCase):
    def setUp(self):
        super().setUp()
        self.cartao = CartaoCredito.objects.create(
            operacao=self.operacao, nome="Cartão DRE", limite_total=Decimal("5000.00"),
            dia_fechamento=20, dia_vencimento=27,
        )

    def test_compra_no_cartao_entra_no_dre_pela_data_da_compra(self):
        lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Compra 3x", valor_total=Decimal("900.00"), data_compra=date(2026, 9, 5), parcelas_qtd=3,
        )
        # entra INTEIRA no mês da compra, mesmo parcelada em 3 meses distintos
        dre_setembro = calcular_dre_mes(self.operacao, 2026, 9)
        dre_outubro = calcular_dre_mes(self.operacao, 2026, 10)
        self.assertEqual(dre_setembro["totais"]["despesa_operacional"], Decimal("900.00"))
        self.assertEqual(dre_outubro["totais"]["despesa_operacional"], Decimal("0.00"))

    def test_pagamento_de_fatura_nunca_aparece_no_dre(self):
        from apps.financeiro.services.private_label.cartoes import pagar_fatura
        compra = lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Compra à vista", valor_total=Decimal("300.00"), data_compra=date(2026, 9, 5),
        )
        fatura = compra.parcelas.first().fatura
        dre_antes = calcular_dre_mes(self.operacao, 2026, 9)
        pagar_fatura(fatura=fatura, valor=Decimal("300.00"), data=date(2026, 9, 27), conta=self.conta)
        dre_depois = calcular_dre_mes(self.operacao, 2026, 9)
        self.assertEqual(dre_antes["totais"]["despesa_operacional"], dre_depois["totais"]["despesa_operacional"])


class DreJurosMultaTests(BaseFinanceiroTestCase):
    def test_juros_e_multa_de_baixa_entram_no_mes_da_baixa_como_financeira(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Conta atrasada",
            valor_original=Decimal("100.00"), data_competencia=date(2026, 7, 1),
            primeiro_vencimento=date(2026, 7, 10), categoria=self.categoria,
        )
        parcela = lancamento.parcelas.first()
        dar_baixa(
            parcela=parcela, valor_principal=Decimal("100.00"), data=date(2026, 9, 5), conta=self.conta,
            juros=Decimal("8.00"), multa=Decimal("2.00"),
        )
        dre_julho = calcular_dre_mes(self.operacao, 2026, 7)
        dre_setembro = calcular_dre_mes(self.operacao, 2026, 9)
        # a despesa principal entra em julho (competência); os R$10 de
        # juros+multa entram em setembro (mês da baixa), como financeira
        self.assertEqual(dre_julho["totais"]["despesa_operacional"], Decimal("100.00"))
        self.assertEqual(dre_julho["totais"]["despesa_financeira"], Decimal("0.00"))
        self.assertEqual(dre_setembro["totais"]["despesa_financeira"], Decimal("10.00"))


class DreInvestimentoTests(BaseFinanceiroTestCase):
    def setUp(self):
        super().setUp()
        from apps.financeiro.models import ContaInvestimento
        self.conta_investimento = ContaInvestimento.objects.create(operacao=self.operacao, nome="CDB")
        self.categoria_rf = CategoriaFinanceira.objects.create(
            operacao=self.operacao, nome="Rendimento CDB", natureza="receita_financeira",
        )

    def test_aplicacao_nao_entra_no_dre(self):
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 9, 5),
        )
        dre = calcular_dre_mes(self.operacao, 2026, 9)
        total = sum(dre["totais"].values())
        self.assertEqual(total, Decimal("0.00"))

    def test_rendimento_entra_no_dre_como_receita_financeira(self):
        registrar_rendimento(
            operacao=self.operacao, conta_investimento=self.conta_investimento,
            categoria=self.categoria_rf, valor=Decimal("25.00"), data=date(2026, 9, 20),
        )
        dre = calcular_dre_mes(self.operacao, 2026, 9)
        self.assertEqual(dre["totais"]["receita_financeira"], Decimal("25.00"))
        self.assertEqual(dre["resultado_liquido"], Decimal("25.00"))


class DreAnoTests(BaseFinanceiroTestCase):
    def test_dre_ano_soma_os_12_meses_no_total(self):
        criar_lancamento(
            operacao=self.operacao, tipo="receita", descricao="Venda jan",
            valor_original=Decimal("100.00"), data_competencia=date(2026, 1, 10),
            primeiro_vencimento=date(2026, 1, 10), categoria=self.categoria_receita,
        )
        criar_lancamento(
            operacao=self.operacao, tipo="receita", descricao="Venda dez",
            valor_original=Decimal("200.00"), data_competencia=date(2026, 12, 10),
            primeiro_vencimento=date(2026, 12, 10), categoria=self.categoria_receita,
        )
        dre_ano = calcular_dre_ano(self.operacao, 2026)
        self.assertEqual(len(dre_ano["meses"]), 12)
        self.assertEqual(dre_ano["total"]["receita_bruta"], Decimal("300.00"))
