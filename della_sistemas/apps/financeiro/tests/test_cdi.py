"""Testes do rendimento automático indexado ao CDI (services/private_label/cdi.py)."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from apps.financeiro.models import CategoriaFinanceira, ContaInvestimento, TaxaCDIDiaria
from apps.financeiro.services.private_label.cdi import (
    _calcular_rendimento_dia,
    atualizar_taxas_cdi,
    lancar_rendimentos_automaticos_todas_contas,
    lancar_rendimentos_pendentes,
)
from apps.financeiro.services.private_label.investimentos import aplicar
from apps.financeiro.tests.test_private_label import BaseFinanceiroTestCase


class CalculoRendimentoDiaTests(BaseFinanceiroTestCase):
    def test_98_por_cento_do_cdi(self):
        # CDI de 0.051660% a.d. (valor real observado), 98% disso sobre R$ 10.000.
        valor = _calcular_rendimento_dia(Decimal("10000.00"), Decimal("0.051660"), Decimal("98.00"))
        esperado = (Decimal("10000.00") * Decimal("0.051660") / 100 * Decimal("98.00") / 100)
        self.assertEqual(valor, esperado.quantize(Decimal("0.01")))
        self.assertEqual(valor, Decimal("5.06"))


class AtualizarTaxasCdiTests(BaseFinanceiroTestCase):
    @patch("apps.financeiro.services.private_label.cdi.buscar_cdi_bacen")
    def test_grava_taxas_novas_sem_duplicar(self, mock_buscar):
        mock_buscar.return_value = [
            {"data": date(2026, 9, 10), "taxa_pct_dia": Decimal("0.051660")},
            {"data": date(2026, 9, 11), "taxa_pct_dia": Decimal("0.051660")},
        ]
        atualizar_taxas_cdi()
        self.assertEqual(TaxaCDIDiaria.objects.count(), 2)
        # Roda de novo (cron reexecutado no mesmo dia) — não duplica, só atualiza.
        atualizar_taxas_cdi()
        self.assertEqual(TaxaCDIDiaria.objects.count(), 2)


class LancarRendimentosPendentesTests(BaseFinanceiroTestCase):
    def setUp(self):
        super().setUp()
        self.categoria_receita_financeira = CategoriaFinanceira.objects.create(
            operacao=self.operacao, nome="Rendimento de aplicação", natureza="receita_financeira",
        )
        self.conta_investimento = ContaInvestimento.objects.create(
            operacao=self.operacao, nome="DCB Banco X", tipo_produto="dcb", liquidez="diaria",
            rendimento_automatico=True, percentual_cdi=Decimal("98.00"),
            categoria_rendimento=self.categoria_receita_financeira,
        )
        for dia, taxa in [
            (date(2026, 9, 8), "0.051660"), (date(2026, 9, 9), "0.051660"), (date(2026, 9, 10), "0.051660"),
        ]:
            TaxaCDIDiaria.objects.create(data=dia, taxa_pct_dia=Decimal(taxa))
        aplicar(
            operacao=self.operacao, conta_investimento=self.conta_investimento, conta_bancaria=self.conta,
            valor=Decimal("10000.00"), data=date(2026, 9, 7),
        )

    def test_lanca_um_rendimento_por_dia_util_em_juros_compostos(self):
        qtd = lancar_rendimentos_pendentes(self.conta_investimento, ate=date(2026, 9, 10))
        self.assertEqual(qtd, 3)
        # Dia 1: 10000.00 * fator = 5.06 -> saldo 10005.06
        # Dia 2: 10005.06 * fator = 5.07 -> saldo 10010.13 (juros sobre juros)
        # Dia 3: 10010.13 * fator = 5.07 -> saldo 10015.20
        self.assertEqual(self.conta_investimento.saldo_atual(), Decimal("10015.20"))
        self.assertEqual(
            self.conta_investimento.transacoes.filter(tipo="rendimento").count(), 3,
        )

    def test_reexecutar_no_mesmo_dia_nao_duplica(self):
        lancar_rendimentos_pendentes(self.conta_investimento, ate=date(2026, 9, 10))
        saldo_apos_primeira = self.conta_investimento.saldo_atual()
        qtd_segunda = lancar_rendimentos_pendentes(self.conta_investimento, ate=date(2026, 9, 10))
        self.assertEqual(qtd_segunda, 0)
        self.assertEqual(self.conta_investimento.saldo_atual(), saldo_apos_primeira)

    def test_conta_sem_rendimento_automatico_e_ignorada(self):
        self.conta_investimento.rendimento_automatico = False
        self.conta_investimento.percentual_cdi = None
        self.conta_investimento.categoria_rendimento = None
        self.conta_investimento.save()
        qtd = lancar_rendimentos_pendentes(self.conta_investimento, ate=date(2026, 9, 10))
        self.assertEqual(qtd, 0)

    def test_lancar_rendimentos_automaticos_todas_contas(self):
        resultado = lancar_rendimentos_automaticos_todas_contas()
        self.assertEqual(resultado, {self.conta_investimento.id: 3})
