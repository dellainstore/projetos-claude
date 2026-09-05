"""Testes do Fluxo de Caixa (Fase 1C) — realizado × previsto, consolidado ×
por conta. Ver `services/private_label/fluxo_caixa.py`."""
from datetime import date, timedelta
from decimal import Decimal

from apps.financeiro.models import CartaoCredito
from apps.financeiro.services.private_label.baixas import dar_baixa
from apps.financeiro.services.private_label.cartoes import lancar_compra_cartao
from apps.financeiro.services.private_label.fluxo_caixa import calcular_fluxo
from apps.financeiro.services.private_label.lancamentos import criar_lancamento
from apps.financeiro.tests.test_private_label import BaseFinanceiroTestCase


class FluxoRealizadoPrevistoTests(BaseFinanceiroTestCase):
    def test_baixa_no_passado_conta_como_realizado(self):
        hoje = date(2026, 9, 10)
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Já pago",
            valor_original=Decimal("100.00"), data_competencia=date(2026, 9, 1),
            primeiro_vencimento=date(2026, 9, 5), categoria=self.categoria,
        )
        dar_baixa(parcela=lancamento.parcelas.first(), valor_principal=Decimal("100.00"), data=date(2026, 9, 5), conta=self.conta)
        linhas = calcular_fluxo(
            operacao=self.operacao, data_inicio=date(2026, 9, 1), data_fim=date(2026, 9, 30), hoje=hoje,
        )
        linha_dia5 = next(l for l in linhas if l.data == date(2026, 9, 5))
        self.assertEqual(linha_dia5.realizado_saida, Decimal("100.00"))
        self.assertEqual(linha_dia5.previsto_saida, Decimal("0.00"))

    def test_parcela_em_aberto_no_futuro_conta_como_previsto(self):
        hoje = date(2026, 9, 10)
        criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="A vencer",
            valor_original=Decimal("80.00"), data_competencia=date(2026, 9, 1),
            primeiro_vencimento=date(2026, 9, 20), categoria=self.categoria,
        )
        linhas = calcular_fluxo(
            operacao=self.operacao, data_inicio=date(2026, 9, 1), data_fim=date(2026, 9, 30), hoje=hoje,
        )
        linha_dia20 = next(l for l in linhas if l.data == date(2026, 9, 20))
        self.assertEqual(linha_dia20.previsto_saida, Decimal("80.00"))
        self.assertEqual(linha_dia20.realizado_saida, Decimal("0.00"))

    def test_parcela_ja_quitada_nao_aparece_como_previsto(self):
        hoje = date(2026, 9, 10)
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Quitada",
            valor_original=Decimal("50.00"), data_competencia=date(2026, 9, 1),
            primeiro_vencimento=date(2026, 9, 20), categoria=self.categoria,
        )
        dar_baixa(parcela=lancamento.parcelas.first(), valor_principal=Decimal("50.00"), data=date(2026, 9, 3), conta=self.conta)
        linhas = calcular_fluxo(
            operacao=self.operacao, data_inicio=date(2026, 9, 1), data_fim=date(2026, 9, 30), hoje=hoje,
        )
        linha_dia20 = next(l for l in linhas if l.data == date(2026, 9, 20))
        self.assertEqual(linha_dia20.previsto_saida, Decimal("0.00"))

    def test_saldo_acumulado_reflete_saldo_inicial_das_contas(self):
        hoje = date(2026, 9, 1)
        linhas = calcular_fluxo(
            operacao=self.operacao, data_inicio=date(2026, 9, 1), data_fim=date(2026, 9, 1), hoje=hoje,
        )
        # self.conta tem saldo_inicial 1000, self.conta2 tem 0 (ver BaseFinanceiroTestCase)
        self.assertEqual(linhas[0].saldo_acumulado, Decimal("1000.00"))

    def test_fatura_de_cartao_em_aberto_conta_como_previsto_na_data_de_vencimento(self):
        hoje = date(2026, 9, 5)
        cartao = CartaoCredito.objects.create(
            operacao=self.operacao, nome="Cartão Fluxo", limite_total=Decimal("2000.00"),
            dia_fechamento=20, dia_vencimento=27,
        )
        lancar_compra_cartao(
            operacao=self.operacao, cartao=cartao, categoria=self.categoria,
            descricao="Compra cartão", valor_total=Decimal("300.00"), data_compra=date(2026, 9, 5),
        )
        linhas = calcular_fluxo(
            operacao=self.operacao, data_inicio=date(2026, 9, 1), data_fim=date(2026, 9, 30), hoje=hoje,
        )
        linha_vencimento = next(l for l in linhas if l.data == date(2026, 9, 27))
        self.assertEqual(linha_vencimento.previsto_saida, Decimal("300.00"))

    def test_conta_especifica_filtra_movimentos_de_outras_contas(self):
        hoje = date(2026, 9, 10)
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Na conta B",
            valor_original=Decimal("70.00"), data_competencia=date(2026, 9, 1),
            primeiro_vencimento=date(2026, 9, 5), categoria=self.categoria,
        )
        dar_baixa(parcela=lancamento.parcelas.first(), valor_principal=Decimal("70.00"), data=date(2026, 9, 5), conta=self.conta2)
        linhas_conta_a = calcular_fluxo(
            operacao=self.operacao, data_inicio=date(2026, 9, 1), data_fim=date(2026, 9, 30),
            conta=self.conta, hoje=hoje,
        )
        linha_dia5 = next(l for l in linhas_conta_a if l.data == date(2026, 9, 5))
        self.assertEqual(linha_dia5.realizado_saida, Decimal("0.00"))

    def test_granularidade_mensal_agrupa_dias_do_mes(self):
        hoje = date(2026, 9, 10)
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="receita", descricao="Venda",
            valor_original=Decimal("500.00"), data_competencia=date(2026, 9, 1),
            primeiro_vencimento=date(2026, 9, 5), categoria=self.categoria_receita,
        )
        dar_baixa(parcela=lancamento.parcelas.first(), valor_principal=Decimal("500.00"), data=date(2026, 9, 5), conta=self.conta)
        linhas = calcular_fluxo(
            operacao=self.operacao, data_inicio=date(2026, 9, 1), data_fim=date(2026, 9, 30),
            granularidade="mes", hoje=hoje,
        )
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0].realizado_entrada, Decimal("500.00"))
