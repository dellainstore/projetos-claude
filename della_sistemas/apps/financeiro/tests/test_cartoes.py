"""Testes obrigatórios da Fase 1B (Cartões) — ver plano aprovado, seção 18.
Reaproveita `BaseFinanceiroTestCase` de `test_private_label.py` (mesma
operação/categoria/contas de teste)."""
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.financeiro.models import CartaoCredito, FaturaCartao
from apps.financeiro.services.private_label.cartoes import (
    cancelar_compra_cartao,
    estornar_pagamento_fatura,
    lancar_compra_cartao,
    pagar_fatura,
)
from apps.financeiro.tests.test_private_label import BaseFinanceiroTestCase


class BaseCartaoTestCase(BaseFinanceiroTestCase):
    def setUp(self):
        super().setUp()
        self.cartao = CartaoCredito.objects.create(
            operacao=self.operacao, nome="Nubank Empresarial", limite_total=Decimal("5000.00"),
            dia_fechamento=20, dia_vencimento=27,
        )


class CartaoValidacaoTests(BaseCartaoTestCase):
    def test_dia_fechamento_fora_do_intervalo_e_rejeitado_pelo_banco(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CartaoCredito.objects.create(
                    operacao=self.operacao, nome="Cartão inválido", limite_total=Decimal("100.00"),
                    dia_fechamento=29, dia_vencimento=5,
                )

    def test_limite_total_zero_e_rejeitado_pelo_banco(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CartaoCredito.objects.create(
                    operacao=self.operacao, nome="Cartão inválido", limite_total=Decimal("0.00"),
                    dia_fechamento=10, dia_vencimento=20,
                )


class CompraParceladaTests(BaseCartaoTestCase):
    def test_compra_a_vista_compromete_o_limite_na_hora(self):
        lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Tecido", valor_total=Decimal("500.00"), data_compra=date(2026, 9, 5),
        )
        self.cartao.refresh_from_db()
        self.assertEqual(self.cartao.limite_utilizado, Decimal("500.00"))
        self.assertEqual(self.cartao.limite_disponivel, Decimal("4500.00"))

    def test_soma_das_parcelas_bate_com_valor_total_mesmo_com_centavos_dificeis(self):
        compra = lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Máquina", valor_total=Decimal("1000.00"), data_compra=date(2026, 9, 5),
            parcelas_qtd=3,
        )
        self.assertEqual(compra.parcelas.count(), 3)
        self.assertEqual(sum(p.valor for p in compra.parcelas.all()), Decimal("1000.00"))

    def test_compra_parcelada_compromete_o_limite_total_de_uma_vez(self):
        lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Máquina 3x", valor_total=Decimal("900.00"), data_compra=date(2026, 9, 5),
            parcelas_qtd=3,
        )
        self.cartao.refresh_from_db()
        # compromete o valor TOTAL na hora da compra, não só a 1ª parcela
        self.assertEqual(self.cartao.limite_utilizado, Decimal("900.00"))

    def test_compra_antes_do_fechamento_cai_na_fatura_do_mesmo_mes(self):
        compra = lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Antes do fechamento", valor_total=Decimal("100.00"), data_compra=date(2026, 9, 15),
        )
        parcela = compra.parcelas.first()
        self.assertEqual((parcela.fatura.competencia_ano, parcela.fatura.competencia_mes), (2026, 9))

    def test_compra_depois_do_fechamento_cai_na_fatura_seguinte(self):
        # dia_fechamento=20 — compra no dia 25 já não cabe mais na fatura de
        # setembro (que fechou no dia 20), cai na de outubro.
        compra = lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Depois do fechamento", valor_total=Decimal("100.00"), data_compra=date(2026, 9, 25),
        )
        parcela = compra.parcelas.first()
        self.assertEqual((parcela.fatura.competencia_ano, parcela.fatura.competencia_mes), (2026, 10))

    def test_parcelas_seguintes_caem_nos_meses_seguintes(self):
        compra = lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="3x", valor_total=Decimal("300.00"), data_compra=date(2026, 9, 15), parcelas_qtd=3,
        )
        competencias = [(p.fatura.competencia_ano, p.fatura.competencia_mes) for p in compra.parcelas.order_by("numero")]
        self.assertEqual(competencias, [(2026, 9), (2026, 10), (2026, 11)])

    def test_data_vencimento_da_fatura_cai_no_mes_seguinte_quando_dia_vencimento_menor_que_fechamento(self):
        # fechamento dia 20, vencimento dia 27 -> mesma competência
        compra = lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Vencimento mesmo mês", valor_total=Decimal("100.00"), data_compra=date(2026, 9, 15),
        )
        fatura = compra.parcelas.first().fatura
        self.assertEqual(fatura.data_vencimento, date(2026, 9, 27))

        cartao2 = CartaoCredito.objects.create(
            operacao=self.operacao, nome="Fechamento 28, vencimento 5", limite_total=Decimal("1000.00"),
            dia_fechamento=28, dia_vencimento=5,
        )
        compra2 = lancar_compra_cartao(
            operacao=self.operacao, cartao=cartao2, categoria=self.categoria,
            descricao="Vencimento mês seguinte", valor_total=Decimal("100.00"), data_compra=date(2026, 9, 15),
        )
        fatura2 = compra2.parcelas.first().fatura
        self.assertEqual(fatura2.data_vencimento, date(2026, 10, 5))

    def test_uma_fatura_por_competencia_e_reaproveitada_entre_compras(self):
        lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Compra 1", valor_total=Decimal("100.00"), data_compra=date(2026, 9, 5),
        )
        lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Compra 2", valor_total=Decimal("50.00"), data_compra=date(2026, 9, 10),
        )
        self.assertEqual(FaturaCartao.objects.filter(cartao=self.cartao, competencia_ano=2026, competencia_mes=9).count(), 1)
        fatura = FaturaCartao.objects.get(cartao=self.cartao, competencia_ano=2026, competencia_mes=9)
        self.assertEqual(fatura.valor_total, Decimal("150.00"))


class CancelamentoCompraTests(BaseCartaoTestCase):
    def test_cancelar_compra_sem_pagamento_libera_limite(self):
        compra = lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="A cancelar", valor_total=Decimal("200.00"), data_compra=date(2026, 9, 5),
        )
        cancelar_compra_cartao(compra, usuario=None)
        self.cartao.refresh_from_db()
        self.assertEqual(self.cartao.limite_utilizado, Decimal("0.00"))

    def test_cancelar_compra_com_parcela_paga_e_bloqueado(self):
        compra = lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Já paga", valor_total=Decimal("200.00"), data_compra=date(2026, 9, 5),
        )
        fatura = compra.parcelas.first().fatura
        pagar_fatura(fatura=fatura, valor=Decimal("200.00"), data=date(2026, 9, 27), conta=self.conta)
        with self.assertRaises(ValueError):
            cancelar_compra_cartao(compra, usuario=None)


class PagamentoFaturaTests(BaseCartaoTestCase):
    def _fatura_com_duas_compras(self):
        c1 = lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Compra A", valor_total=Decimal("300.00"), data_compra=date(2026, 9, 5),
        )
        c2 = lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Compra B", valor_total=Decimal("200.00"), data_compra=date(2026, 9, 10),
        )
        fatura = FaturaCartao.objects.get(cartao=self.cartao, competencia_ano=2026, competencia_mes=9)
        return fatura, c1, c2

    def test_pagamento_total_quita_a_fatura_e_libera_o_limite(self):
        fatura, c1, c2 = self._fatura_com_duas_compras()
        pagar_fatura(fatura=fatura, valor=Decimal("500.00"), data=date(2026, 9, 27), conta=self.conta)
        fatura.refresh_from_db()
        self.assertEqual(fatura.estado_estrutural, "quitado")
        self.cartao.refresh_from_db()
        self.assertEqual(self.cartao.limite_utilizado, Decimal("0.00"))

    def test_pagamento_parcial_recompoe_limite_proporcionalmente_na_ordem_da_compra_mais_antiga(self):
        fatura, c1, c2 = self._fatura_com_duas_compras()
        pagar_fatura(fatura=fatura, valor=Decimal("300.00"), data=date(2026, 9, 27), conta=self.conta)
        c1.refresh_from_db()
        c2.refresh_from_db()
        p1 = c1.parcelas.first()
        p2 = c2.parcelas.first()
        p1.refresh_from_db()
        p2.refresh_from_db()
        # a compra mais antiga (A, R$300) é quitada primeiro; sobra 0 para B
        self.assertEqual(p1.paga_valor, Decimal("300.00"))
        self.assertEqual(p2.paga_valor, Decimal("0.00"))
        self.cartao.refresh_from_db()
        self.assertEqual(self.cartao.limite_utilizado, Decimal("200.00"))
        fatura.refresh_from_db()
        self.assertEqual(fatura.estado_estrutural, "parcial")

    def test_pagamento_nao_cria_lancamento_financeiro(self):
        from apps.financeiro.models import LancamentoFinanceiro
        fatura, c1, c2 = self._fatura_com_duas_compras()
        antes = LancamentoFinanceiro.objects.count()
        pagar_fatura(fatura=fatura, valor=Decimal("500.00"), data=date(2026, 9, 27), conta=self.conta)
        depois = LancamentoFinanceiro.objects.count()
        self.assertEqual(antes, depois)

    def test_pagamento_acima_do_saldo_e_bloqueado(self):
        fatura, c1, c2 = self._fatura_com_duas_compras()
        with self.assertRaises(ValueError):
            pagar_fatura(fatura=fatura, valor=Decimal("9999.00"), data=date(2026, 9, 27), conta=self.conta)

    def test_pagamento_debita_a_conta_bancaria(self):
        fatura, c1, c2 = self._fatura_com_duas_compras()
        saldo_antes = self.conta.saldo_atual()
        pagar_fatura(fatura=fatura, valor=Decimal("500.00"), data=date(2026, 9, 27), conta=self.conta)
        self.assertEqual(self.conta.saldo_atual(), saldo_antes - Decimal("500.00"))

    def test_estorno_de_pagamento_recompoe_limite_e_saldo_sem_apagar_o_original(self):
        from apps.financeiro.models import MovimentoConta
        fatura, c1, c2 = self._fatura_com_duas_compras()
        saldo_antes = self.conta.saldo_atual()
        pagamento = pagar_fatura(fatura=fatura, valor=Decimal("500.00"), data=date(2026, 9, 27), conta=self.conta)
        estornar_pagamento_fatura(pagamento, motivo="teste")
        self.assertEqual(self.conta.saldo_atual(), saldo_antes)
        self.cartao.refresh_from_db()
        self.assertEqual(self.cartao.limite_utilizado, Decimal("500.00"))
        fatura.refresh_from_db()
        self.assertEqual(fatura.estado_estrutural, "aberto")
        self.assertTrue(MovimentoConta.objects.filter(evento_chave=f"fatura-pagamento:{pagamento.id}").exists())
        self.assertTrue(MovimentoConta.objects.filter(evento_chave=f"estorno-fatura-pagamento:{pagamento.id}").exists())

    def test_estornar_pagamento_ja_estornado_e_bloqueado(self):
        fatura, c1, c2 = self._fatura_com_duas_compras()
        pagamento = pagar_fatura(fatura=fatura, valor=Decimal("100.00"), data=date(2026, 9, 27), conta=self.conta)
        estornar_pagamento_fatura(pagamento, motivo="teste")
        with self.assertRaises(ValueError):
            estornar_pagamento_fatura(pagamento, motivo="de novo")


class TelaCartoesTests(BaseCartaoTestCase):
    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model
        from django.test import Client
        self.user = get_user_model().objects.create_user(
            username="_teste_cartoes", password="x", papel="superadmin", is_superuser=True,
        )
        self.client = Client(SERVER_NAME="localhost", HTTP_X_FORWARDED_PROTO="https")
        self.client.force_login(self.user)

    def test_tela_de_cartoes_lista_o_cartao_e_a_fatura(self):
        lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Compra na tela", valor_total=Decimal("150.00"), data_compra=date.today(),
        )
        resp = self.client.get("/financeiro/private-label/cartoes/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.cartao.nome, resp.content.decode())

    def test_tela_de_detalhe_do_cartao(self):
        compra = lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Compra no detalhe", valor_total=Decimal("150.00"), data_compra=date.today(),
        )
        resp = self.client.get(f"/financeiro/private-label/cartoes/{self.cartao.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Compra no detalhe", resp.content.decode())

    def test_pagar_fatura_pela_tela(self):
        compra = lancar_compra_cartao(
            operacao=self.operacao, cartao=self.cartao, categoria=self.categoria,
            descricao="Compra a pagar", valor_total=Decimal("150.00"), data_compra=date.today(),
        )
        fatura = compra.parcelas.first().fatura
        resp = self.client.post(f"/financeiro/private-label/htmx/faturas/{fatura.pk}/pagar/salvar/", {
            "valor": "150.00", "data": str(date.today()), "conta": self.conta.pk,
        })
        self.assertEqual(resp.status_code, 200)
        fatura.refresh_from_db()
        self.assertEqual(fatura.estado_estrutural, "quitado")
