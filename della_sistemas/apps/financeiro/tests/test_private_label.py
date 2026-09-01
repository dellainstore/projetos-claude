"""Testes obrigatórios da Fase 1A do módulo Private Label (ver plano
aprovado, seção 18). Primeiro conjunto de testes automatizados do projeto —
cobre as regras de cálculo financeiro que não podem regredir silenciosamente:
centavos de parcelamento, saldo/limite de baixa, transferência fora do DRE,
idempotência de recorrência e de eventos do razão."""
from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.financeiro.models import (
    ESTADO_CANCELADO,
    ESTADO_PARCIAL,
    ESTADO_QUITADO,
    CategoriaFinanceira,
    ContaBancaria,
    MovimentoConta,
    OperacaoFinanceira,
    RegraRecorrencia,
    Transferencia,
)
from apps.financeiro.services.private_label.ajustes import ajustar_saldo
from apps.financeiro.services.private_label.baixas import dar_baixa, estornar_baixa
from apps.financeiro.services.private_label.lancamentos import (
    cancelar_lancamento,
    cancelar_parcela,
    criar_lancamento,
    gerar_valores_parcelas,
)
from apps.financeiro.services.private_label.recorrencias import (
    criar_regra_recorrencia,
    estender_janela_recorrencias,
)
from apps.financeiro.services.private_label.transferencias import estornar_transferencia, transferir


class BaseFinanceiroTestCase(TestCase):
    def setUp(self):
        # A migration de seed (0002) já cria a operação "private-label" no
        # banco de teste também — desativa para não conflitar com
        # `obter_operacao_padrao()` (que corretamente reclama se houver
        # mais de uma ativa).
        OperacaoFinanceira.objects.filter(codigo="private-label").update(status="inativa")
        self.operacao = OperacaoFinanceira.objects.create(nome="Private Label", codigo="private-label-teste")
        self.categoria = CategoriaFinanceira.objects.create(
            operacao=self.operacao, nome="Despesas Gerais", natureza="despesa_operacional",
        )
        self.categoria_receita = CategoriaFinanceira.objects.create(
            operacao=self.operacao, nome="Vendas", natureza="receita",
        )
        self.conta = ContaBancaria.objects.create(
            operacao=self.operacao, nome="Conta A", saldo_inicial=Decimal("1000.00"),
            data_saldo_inicial=date(2026, 1, 1),
        )
        self.conta2 = ContaBancaria.objects.create(
            operacao=self.operacao, nome="Conta B", data_saldo_inicial=date(2026, 1, 1),
        )


class ParcelamentoTests(BaseFinanceiroTestCase):
    def test_soma_das_parcelas_bate_com_valor_original_mesmo_com_centavos_dificeis(self):
        valores = gerar_valores_parcelas(Decimal("1000.00"), 3)
        self.assertEqual(sum(valores), Decimal("1000.00"))
        self.assertEqual(valores, [Decimal("333.33"), Decimal("333.33"), Decimal("333.34")])

    def test_lancamento_parcelado_gera_parcelas_com_soma_exata(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="conta_pagar", descricao="Compra parcelada",
            valor_original=Decimal("100.00"), data_competencia=date(2026, 9, 1),
            primeiro_vencimento=date(2026, 9, 10), categoria=self.categoria, parcelas_qtd=3,
        )
        self.assertEqual(lancamento.parcelas.count(), 3)
        self.assertEqual(sum(p.valor for p in lancamento.parcelas.all()), Decimal("100.00"))
        vencimentos = list(lancamento.parcelas.order_by("numero").values_list("data_vencimento", flat=True))
        self.assertEqual(vencimentos, [date(2026, 9, 10), date(2026, 10, 10), date(2026, 11, 10)])


class BaixaTests(BaseFinanceiroTestCase):
    def _lancamento_simples(self, valor="200.00", tipo="despesa"):
        return criar_lancamento(
            operacao=self.operacao, tipo=tipo, descricao="Lançamento teste",
            valor_original=Decimal(valor), data_competencia=date(2026, 9, 1),
            primeiro_vencimento=date(2026, 9, 1), categoria=self.categoria,
        )

    def test_baixa_parcial_nao_sobrescreve_valor_original(self):
        lancamento = self._lancamento_simples()
        parcela = lancamento.parcelas.first()
        dar_baixa(parcela=parcela, valor_principal=Decimal("50.00"), data=date(2026, 9, 1), conta=self.conta)
        parcela.refresh_from_db()
        self.assertEqual(parcela.valor, Decimal("200.00"))
        self.assertEqual(parcela.estado_estrutural, ESTADO_PARCIAL)
        self.assertEqual(parcela.saldo_restante, Decimal("150.00"))

    def test_baixa_total_quita_parcela_e_lancamento(self):
        lancamento = self._lancamento_simples()
        parcela = lancamento.parcelas.first()
        dar_baixa(parcela=parcela, valor_principal=parcela.valor, data=date(2026, 9, 1), conta=self.conta)
        parcela.refresh_from_db()
        lancamento.refresh_from_db()
        self.assertEqual(parcela.estado_estrutural, ESTADO_QUITADO)
        self.assertEqual(lancamento.estado_estrutural, ESTADO_QUITADO)

    def test_baixa_acima_do_saldo_e_bloqueada_por_padrao(self):
        lancamento = self._lancamento_simples()
        parcela = lancamento.parcelas.first()
        with self.assertRaises(ValueError):
            dar_baixa(parcela=parcela, valor_principal=Decimal("9999.00"), data=date(2026, 9, 1), conta=self.conta)

    def test_baixa_acima_do_saldo_permitida_com_flag_explicita(self):
        lancamento = self._lancamento_simples()
        parcela = lancamento.parcelas.first()
        baixa = dar_baixa(
            parcela=parcela, valor_principal=Decimal("300.00"), data=date(2026, 9, 1),
            conta=self.conta, permitir_excedente=True,
        )
        self.assertEqual(baixa.valor_principal, Decimal("300.00"))

    def test_valor_movimentado_soma_juros_multa_e_subtrai_desconto(self):
        lancamento = self._lancamento_simples()
        parcela = lancamento.parcelas.first()
        baixa = dar_baixa(
            parcela=parcela, valor_principal=Decimal("200.00"), data=date(2026, 9, 1), conta=self.conta,
            juros=Decimal("10.00"), multa=Decimal("5.00"), desconto=Decimal("3.00"),
        )
        self.assertEqual(baixa.valor_movimentado, Decimal("212.00"))

    def test_valor_movimentado_negativo_e_rejeitado(self):
        lancamento = self._lancamento_simples()
        parcela = lancamento.parcelas.first()
        with self.assertRaises(ValueError):
            dar_baixa(
                parcela=parcela, valor_principal=Decimal("10.00"), data=date(2026, 9, 1),
                conta=self.conta, desconto=Decimal("999.00"),
            )

    def test_saldo_da_conta_reflete_baixa_com_sinal_correto_por_tipo(self):
        despesa = self._lancamento_simples(valor="100.00", tipo="despesa")
        dar_baixa(parcela=despesa.parcelas.first(), valor_principal=Decimal("100.00"), data=date(2026, 9, 1), conta=self.conta)
        self.assertEqual(self.conta.saldo_atual(), Decimal("900.00"))

        receita = self._lancamento_simples(valor="50.00", tipo="receita")
        dar_baixa(parcela=receita.parcelas.first(), valor_principal=Decimal("50.00"), data=date(2026, 9, 1), conta=self.conta)
        self.assertEqual(self.conta.saldo_atual(), Decimal("950.00"))

    def test_estorno_de_baixa_recompoe_saldo_sem_apagar_o_movimento_original(self):
        lancamento = self._lancamento_simples()
        parcela = lancamento.parcelas.first()
        baixa = dar_baixa(parcela=parcela, valor_principal=Decimal("100.00"), data=date(2026, 9, 1), conta=self.conta)
        saldo_antes_estorno = self.conta.saldo_atual()
        estornar_baixa(baixa, motivo="teste")
        self.assertEqual(self.conta.saldo_atual(), saldo_antes_estorno + Decimal("100.00"))
        # ledger append-only: o movimento original continua existindo
        self.assertTrue(MovimentoConta.objects.filter(evento_chave=f"baixa:{baixa.id}").exists())
        self.assertTrue(MovimentoConta.objects.filter(evento_chave=f"estorno-baixa:{baixa.id}").exists())

    def test_lancamento_vencido_muda_de_situacao_sem_nenhuma_mutacao(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Conta vencida",
            valor_original=Decimal("50.00"), data_competencia=date(2020, 1, 1),
            primeiro_vencimento=date(2020, 1, 10), categoria=self.categoria,
        )
        # sem nenhuma baixa nem edição, só a passagem do tempo muda a leitura:
        # no próprio dia do vencimento ainda não é "vencido" (é "pendente");
        # anos depois, com saldo aberto, passa a ser "vencido" — mesmo
        # `estado_estrutural` (aberto) o tempo todo, nunca mutado.
        self.assertEqual(lancamento.situacao_temporal(hoje=date(2020, 1, 10)), "pendente")
        self.assertEqual(lancamento.situacao_temporal(hoje=date(2026, 9, 1)), "vencido")
        lancamento.refresh_from_db()
        self.assertEqual(lancamento.estado_estrutural, "aberto")


class CancelamentoTests(BaseFinanceiroTestCase):
    def test_cancelamento_de_uma_parcela_nao_afeta_as_demais(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="conta_pagar", descricao="3 parcelas",
            valor_original=Decimal("300.00"), data_competencia=date(2026, 9, 1),
            primeiro_vencimento=date(2026, 9, 1), categoria=self.categoria, parcelas_qtd=3,
        )
        p1, p2, p3 = lancamento.parcelas.order_by("numero")
        cancelar_parcela(p2)
        p1.refresh_from_db(); p2.refresh_from_db(); p3.refresh_from_db()
        self.assertEqual(p2.estado_estrutural, ESTADO_CANCELADO)
        self.assertNotEqual(p1.estado_estrutural, ESTADO_CANCELADO)
        self.assertNotEqual(p3.estado_estrutural, ESTADO_CANCELADO)

    def test_cancelamento_da_serie_inteira(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="conta_pagar", descricao="Série a cancelar",
            valor_original=Decimal("300.00"), data_competencia=date(2026, 9, 1),
            primeiro_vencimento=date(2026, 9, 1), categoria=self.categoria, parcelas_qtd=3,
        )
        cancelar_lancamento(lancamento)
        lancamento.refresh_from_db()
        self.assertEqual(lancamento.estado_estrutural, ESTADO_CANCELADO)
        self.assertTrue(all(p.estado_estrutural == ESTADO_CANCELADO for p in lancamento.parcelas.all()))

    def test_nao_permite_cancelar_parcela_com_baixa(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Com baixa parcial",
            valor_original=Decimal("100.00"), data_competencia=date(2026, 9, 1),
            primeiro_vencimento=date(2026, 9, 1), categoria=self.categoria,
        )
        parcela = lancamento.parcelas.first()
        dar_baixa(parcela=parcela, valor_principal=Decimal("30.00"), data=date(2026, 9, 1), conta=self.conta)
        with self.assertRaises(ValueError):
            cancelar_parcela(parcela)


class TransferenciaTests(BaseFinanceiroTestCase):
    def test_transferencia_gera_dois_movimentos_com_efeito_liquido_zero(self):
        transferir(operacao=self.operacao, conta_origem=self.conta, conta_destino=self.conta2,
                   valor=Decimal("100.00"), data=date(2026, 9, 1))
        self.assertEqual(self.conta.saldo_atual(), Decimal("900.00"))
        self.assertEqual(self.conta2.saldo_atual(), Decimal("100.00"))
        movimentos = MovimentoConta.objects.filter(transferencia__isnull=False)
        self.assertEqual(movimentos.count(), 2)
        self.assertEqual(sum(m.valor for m in movimentos), Decimal("0.00"))

    def test_transferencia_nunca_tem_categoria_fica_fora_do_dre(self):
        t = transferir(operacao=self.operacao, conta_origem=self.conta, conta_destino=self.conta2,
                        valor=Decimal("10.00"), data=date(2026, 9, 1))
        self.assertFalse(hasattr(t, "categoria"))

    def test_transferencia_mesma_conta_e_bloqueada_pelo_banco(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Transferencia.objects.create(
                    operacao=self.operacao, conta_origem=self.conta, conta_destino=self.conta,
                    valor=Decimal("10.00"), data=date(2026, 9, 1),
                )

    def test_estorno_de_transferencia_neutraliza_efeito_sem_apagar_original(self):
        t = transferir(operacao=self.operacao, conta_origem=self.conta, conta_destino=self.conta2,
                        valor=Decimal("100.00"), data=date(2026, 9, 1))
        estornar_transferencia(t, motivo="teste")
        self.assertEqual(self.conta.saldo_atual(), Decimal("1000.00"))
        self.assertEqual(self.conta2.saldo_atual(), Decimal("0.00"))
        self.assertEqual(MovimentoConta.objects.filter(transferencia=t).count(), 4)


class AjusteSaldoTests(BaseFinanceiroTestCase):
    def test_ajuste_de_saldo_exige_motivo(self):
        with self.assertRaises(ValueError):
            ajustar_saldo(operacao=self.operacao, conta=self.conta, valor=Decimal("10.00"), motivo="")

    def test_ajuste_de_saldo_recompoe_saldo_e_e_auditado(self):
        from apps.financeiro.models import LogAuditoriaFinanceiro
        ajustar_saldo(operacao=self.operacao, conta=self.conta, valor=Decimal("-25.00"), motivo="correção de saldo inicial")
        self.assertEqual(self.conta.saldo_atual(), Decimal("975.00"))
        self.assertTrue(LogAuditoriaFinanceiro.objects.filter(entidade="ajuste_saldo").exists())


class MovimentoContaIntegridadeTests(BaseFinanceiroTestCase):
    def test_movimento_sem_nenhuma_origem_e_rejeitado(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MovimentoConta.objects.create(
                    operacao=self.operacao, conta=self.conta, data=date(2026, 9, 1),
                    valor=Decimal("10.00"), evento_chave="orfao:1",
                )

    def test_movimento_valor_zero_e_rejeitado(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="x", valor_original=Decimal("10.00"),
            data_competencia=date(2026, 9, 1), primeiro_vencimento=date(2026, 9, 1), categoria=self.categoria,
        )
        parcela = lancamento.parcelas.first()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                from apps.financeiro.models import Baixa
                baixa = Baixa.objects.create(
                    parcela=parcela, valor_principal=Decimal("10.00"), valor_movimentado=Decimal("10.00"),
                    data=date(2026, 9, 1), conta=self.conta,
                )
                MovimentoConta.objects.create(
                    operacao=self.operacao, conta=self.conta, data=date(2026, 9, 1),
                    valor=Decimal("0.00"), evento_chave="zero:1", baixa=baixa,
                )

    def test_evento_chave_duplicado_e_rejeitado_idempotencia(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="dup", valor_original=Decimal("10.00"),
            data_competencia=date(2026, 9, 1), primeiro_vencimento=date(2026, 9, 1), categoria=self.categoria,
        )
        parcela = lancamento.parcelas.first()
        dar_baixa(parcela=parcela, valor_principal=Decimal("10.00"), data=date(2026, 9, 1), conta=self.conta)
        movimento = MovimentoConta.objects.filter(conta=self.conta).order_by("-id").first()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MovimentoConta.objects.create(
                    operacao=self.operacao, conta=self.conta, data=date(2026, 9, 1),
                    valor=Decimal("10.00"), evento_chave=movimento.evento_chave, ajuste=None,
                    baixa=movimento.baixa,
                )


class RecorrenciaTests(BaseFinanceiroTestCase):
    def test_janela_sem_fim_gera_exatamente_a_quantidade_esperada(self):
        regra = criar_regra_recorrencia(
            operacao=self.operacao, tipo_lancamento="despesa", descricao="Assinatura",
            categoria=self.categoria, valor=Decimal("29.90"), frequencia="mensal",
            data_inicial=date(2026, 9, 1), janela_meses=12,
        )
        self.assertEqual(regra.ocorrencias.count(), 12)

    def test_regra_com_fim_definido_inclui_ocorrencia_na_borda(self):
        regra = criar_regra_recorrencia(
            operacao=self.operacao, tipo_lancamento="despesa", descricao="Com fim",
            categoria=self.categoria, valor=Decimal("10.00"), frequencia="mensal",
            data_inicial=date(2026, 9, 1), data_final=date(2026, 9, 1) + timedelta(days=95),
        )
        self.assertEqual(regra.ocorrencias.count(), 4)

    def test_rodar_extensao_duas_vezes_nao_duplica_ocorrencias(self):
        criar_regra_recorrencia(
            operacao=self.operacao, tipo_lancamento="despesa", descricao="Idempotente",
            categoria=self.categoria, valor=Decimal("15.00"), frequencia="mensal",
            data_inicial=date(2026, 9, 1), janela_meses=3,
        )
        antes = RegraRecorrencia.objects.get(descricao="Idempotente").ocorrencias.count()
        estender_janela_recorrencias()
        estender_janela_recorrencias()
        depois = RegraRecorrencia.objects.get(descricao="Idempotente").ocorrencias.count()
        self.assertEqual(antes, depois)

    def test_pausar_regra_impede_novas_ocorrencias(self):
        regra = criar_regra_recorrencia(
            operacao=self.operacao, tipo_lancamento="despesa", descricao="Pausável",
            categoria=self.categoria, valor=Decimal("15.00"), frequencia="mensal",
            data_inicial=date(2026, 9, 1), janela_meses=1,
        )
        regra.pausada = True
        regra.janela_meses = 12
        regra.save()
        estender_janela_recorrencias()
        regra.refresh_from_db()
        self.assertLessEqual(regra.ocorrencias.count(), 1)


class OperacaoUnicaTests(BaseFinanceiroTestCase):
    def test_obter_operacao_padrao_resolve_a_unica_ativa(self):
        from apps.financeiro.services.private_label.operacao import obter_operacao_padrao
        resolvida = obter_operacao_padrao()
        self.assertEqual(resolvida.pk, self.operacao.pk)

    def test_obter_operacao_padrao_falha_explicitamente_com_mais_de_uma_ativa(self):
        OperacaoFinanceira.objects.create(nome="Outra", codigo="outra-operacao-teste")
        from apps.financeiro.services.private_label.operacao import obter_operacao_padrao
        with self.assertRaises(RuntimeError):
            obter_operacao_padrao()
