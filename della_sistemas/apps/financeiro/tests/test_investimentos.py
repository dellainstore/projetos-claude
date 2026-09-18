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


class IofAutomaticoResgateTests(BaseInvestimentoTestCase):
    def setUp(self):
        super().setUp()
        self.conta_investimento.iof_automatico = True
        self.conta_investimento.categoria_iof = self.categoria_despesa_financeira
        self.conta_investimento.save()

    def test_resgate_total_com_5_dias_retem_83_por_cento_do_rendimento(self):
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 9, 1),
        )
        registrar_rendimento(
            operacao=self.operacao, conta_investimento=self.conta_investimento,
            categoria=self.categoria_receita_financeira, valor=Decimal("100.00"), data=date(2026, 9, 5),
        )
        resgatar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1100.00"), data=date(2026, 9, 6),
        )
        # 5 dias corridos desde a aplicação -> alíquota 83% (tabela regressiva),
        # incide só sobre o rendimento (100.00) -> IOF = 83.00.
        self.assertEqual(self.conta.saldo_atual(), Decimal("1017.00"))
        self.assertEqual(self.conta_investimento.saldo_atual(), Decimal("0.00"))
        iof = self.conta_investimento.transacoes.get(tipo="taxa")
        self.assertEqual(iof.valor, Decimal("83.00"))
        self.assertFalse(iof.estornada)

    def test_resgate_apos_30_dias_e_isento_de_iof(self):
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 8, 1),
        )
        registrar_rendimento(
            operacao=self.operacao, conta_investimento=self.conta_investimento,
            categoria=self.categoria_receita_financeira, valor=Decimal("50.00"), data=date(2026, 8, 10),
        )
        resgatar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1050.00"), data=date(2026, 9, 1),
        )
        self.assertEqual(self.conta.saldo_atual(), Decimal("1050.00"))
        self.assertFalse(self.conta_investimento.transacoes.filter(tipo="taxa").exists())

    def test_estornar_resgate_estorna_iof_derivado_junto(self):
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 9, 1),
        )
        registrar_rendimento(
            operacao=self.operacao, conta_investimento=self.conta_investimento,
            categoria=self.categoria_receita_financeira, valor=Decimal("100.00"), data=date(2026, 9, 5),
        )
        resgate = resgatar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1100.00"), data=date(2026, 9, 6),
        )
        iof = self.conta_investimento.transacoes.get(tipo="taxa")
        estornar_transacao(resgate, motivo="teste")
        iof.refresh_from_db()
        self.assertTrue(iof.estornada)
        self.assertEqual(self.conta.saldo_atual(), Decimal("0.00"))
        self.assertEqual(self.conta_investimento.saldo_atual(), Decimal("1100.00"))

    def test_conta_sem_iof_automatico_nao_calcula_nada(self):
        self.conta_investimento.iof_automatico = False
        self.conta_investimento.categoria_iof = None
        self.conta_investimento.save()
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 9, 1),
        )
        resgatar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 9, 2),
        )
        self.assertEqual(self.conta.saldo_atual(), Decimal("1000.00"))
        self.assertFalse(self.conta_investimento.transacoes.filter(tipo="taxa").exists())


class IrAutomaticoResgateTests(BaseInvestimentoTestCase):
    def setUp(self):
        super().setUp()
        self.conta_investimento.ir_automatico = True
        self.conta_investimento.categoria_ir = self.categoria_despesa_financeira
        self.conta_investimento.save()

    def test_resgate_com_59_dias_e_sem_iof_retem_22_5_por_cento_de_ir(self):
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 1, 1),
        )
        registrar_rendimento(
            operacao=self.operacao, conta_investimento=self.conta_investimento,
            categoria=self.categoria_receita_financeira, valor=Decimal("200.00"), data=date(2026, 1, 10),
        )
        resgatar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1200.00"), data=date(2026, 3, 1),
        )
        # 59 dias corridos -> faixa até 180 dias -> IR 22,5% sobre os 200,00
        # de rendimento (sem IOF automático ligado nesta conta) = 45,00.
        self.assertEqual(self.conta.saldo_atual(), Decimal("1155.00"))
        ir = self.conta_investimento.transacoes.get(tipo="taxa")
        self.assertEqual(ir.valor, Decimal("45.00"))
        self.assertEqual(ir.categoria_id, self.categoria_despesa_financeira.id)

    def test_iof_e_ir_juntos_ir_incide_sobre_rendimento_liquido_de_iof(self):
        self.conta_investimento.iof_automatico = True
        self.conta_investimento.categoria_iof = self.categoria_despesa_financeira
        self.conta_investimento.save()
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 9, 1),
        )
        registrar_rendimento(
            operacao=self.operacao, conta_investimento=self.conta_investimento,
            categoria=self.categoria_receita_financeira, valor=Decimal("100.00"), data=date(2026, 9, 5),
        )
        resgatar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1100.00"), data=date(2026, 9, 6),
        )
        # 5 dias -> IOF 83% sobre 100,00 de rendimento = 83,00; IR 22,5%
        # sobre o que sobrou do rendimento (100 - 83 = 17,00) = 3,82~3,83.
        # SQLite não tem tipo Decimal nativo — Sum() de DecimalField volta
        # float, então quantiza antes de comparar (mesma pegadinha de
        # qualquer outro `saldo_atual()` neste arquivo de teste).
        self.assertEqual(
            Decimal(self.conta.saldo_atual()).quantize(Decimal("0.01")), Decimal("1013.18"),
        )
        taxas = list(self.conta_investimento.transacoes.filter(tipo="taxa").values_list("valor", flat=True))
        self.assertEqual(len(taxas), 2)
        self.assertEqual(sum(taxas), Decimal("86.82"))

    def test_estornar_resgate_estorna_iof_e_ir_derivados_junto(self):
        self.conta_investimento.iof_automatico = True
        self.conta_investimento.categoria_iof = self.categoria_despesa_financeira
        self.conta_investimento.save()
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1000.00"), data=date(2026, 9, 1),
        )
        registrar_rendimento(
            operacao=self.operacao, conta_investimento=self.conta_investimento,
            categoria=self.categoria_receita_financeira, valor=Decimal("100.00"), data=date(2026, 9, 5),
        )
        resgate = resgatar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("1100.00"), data=date(2026, 9, 6),
        )
        self.assertEqual(self.conta_investimento.transacoes.filter(tipo="taxa", estornada=False).count(), 2)
        estornar_transacao(resgate, motivo="teste")
        self.assertEqual(self.conta_investimento.transacoes.filter(tipo="taxa", estornada=False).count(), 0)
        self.assertEqual(self.conta.saldo_atual(), Decimal("0.00"))
        self.assertEqual(self.conta_investimento.saldo_atual(), Decimal("1100.00"))
