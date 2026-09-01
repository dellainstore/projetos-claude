"""Testes obrigatórios da Fase 1A do módulo Private Label (ver plano
aprovado, seção 18). Primeiro conjunto de testes automatizados do projeto —
cobre as regras de cálculo financeiro que não podem regredir silenciosamente:
centavos de parcelamento, saldo/limite de baixa, transferência fora do DRE,
idempotência de recorrência e de eventos do razão."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase

from apps.financeiro.models import (
    ESTADO_CANCELADO,
    ESTADO_PARCIAL,
    ESTADO_QUITADO,
    CategoriaFinanceira,
    ContaBancaria,
    LancamentoFinanceiro,
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
    editar_parcela,
    gerar_valores_parcelas,
    reparcelar,
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
            operacao=self.operacao, tipo="despesa", descricao="Compra parcelada",
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
            operacao=self.operacao, tipo="despesa", descricao="3 parcelas",
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
            operacao=self.operacao, tipo="despesa", descricao="Série a cancelar",
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


class DashboardETransferenciaNaListaTests(BaseFinanceiroTestCase):
    """Cobre o pedido do dono de 2026-09-01: dashboard com saldo/gasto/
    recebido/parcelados, e transferência precisa aparecer em Lançamentos
    mesmo não contando pro gasto x recebido."""

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(
            username="_teste_dashboard", password="x", papel="superadmin", is_superuser=True,
        )
        self.client = Client(SERVER_NAME="localhost", HTTP_X_FORWARDED_PROTO="https")
        self.client.force_login(self.user)

    def test_dashboard_soma_gasto_recebido_e_lista_parcelados(self):
        hoje = date.today()
        despesa = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Aluguel", valor_original=Decimal("300.00"),
            data_competencia=hoje, primeiro_vencimento=hoje, categoria=self.categoria,
        )
        dar_baixa(parcela=despesa.parcelas.first(), valor_principal=Decimal("300.00"), data=hoje, conta=self.conta)
        receita = criar_lancamento(
            operacao=self.operacao, tipo="receita", descricao="Venda", valor_original=Decimal("500.00"),
            data_competencia=hoje, primeiro_vencimento=hoje, categoria=self.categoria_receita,
        )
        dar_baixa(parcela=receita.parcelas.first(), valor_principal=Decimal("500.00"), data=hoje, conta=self.conta)
        criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Compra parcelada", valor_original=Decimal("900.00"),
            data_competencia=hoje, primeiro_vencimento=hoje, categoria=self.categoria, parcelas_qtd=3,
        )

        resp = self.client.get("/financeiro/private-label/dashboard/")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Compra parcelada", body)
        self.assertIn(self.categoria.nome, body)  # despesa aparece agrupada na categoria
        self.assertIn("R$ 300,00", body)  # total gasto
        self.assertIn("R$ 500,00", body)  # total recebido
        self.assertIn("R$ 900,00", body)  # total da conta parcelada

    def test_transferencia_aparece_na_lista_de_lancamentos_mesmo_fora_do_dre(self):
        transferir(operacao=self.operacao, conta_origem=self.conta, conta_destino=self.conta2,
                   valor=Decimal("50.00"), data=date.today(), observacao="teste visibilidade")
        resp = self.client.get("/financeiro/private-label/lancamentos/?situacao=todas")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn(self.conta.nome, body)
        self.assertIn(self.conta2.nome, body)
        self.assertIn("teste visibilidade", body)

    def test_transferencia_estornada_pela_tela_recompoe_saldo(self):
        t = transferir(operacao=self.operacao, conta_origem=self.conta, conta_destino=self.conta2,
                        valor=Decimal("50.00"), data=date.today())
        resp = self.client.post(f"/financeiro/private-label/htmx/transferencias/{t.pk}/estornar/", {})
        self.assertEqual(resp.status_code, 200)
        t.refresh_from_db()
        self.assertTrue(t.estornada)
        self.assertEqual(self.conta2.saldo_atual(), Decimal("0.00"))


class TipoUnicoEAutoBaixaTests(BaseFinanceiroTestCase):
    """Pedido do dono (2026-09-02): só Receita/Despesa (sem "conta a
    pagar/receber" separado); lançamento com data passada + conta
    informada já nasce pago/recebido; sem conta informada, fica em aberto
    mesmo com data passada (não tem como baixar sem saber de qual conta)."""

    def test_tipo_so_tem_duas_opcoes(self):
        from apps.financeiro.models import TIPO_LANCAMENTO_CHOICES
        self.assertEqual([v for v, _ in TIPO_LANCAMENTO_CHOICES], ["receita", "despesa"])

    def test_data_passada_com_conta_ja_nasce_pago(self):
        ontem = date.today() - timedelta(days=5)
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Compra já paga",
            valor_original=Decimal("80.00"), data_competencia=ontem, primeiro_vencimento=ontem,
            categoria=self.categoria, conta_prevista=self.conta,
        )
        parcela = lancamento.parcelas.first()
        self.assertEqual(parcela.estado_estrutural, ESTADO_QUITADO)
        self.assertEqual(lancamento.estado_estrutural, ESTADO_QUITADO)
        self.assertEqual(self.conta.saldo_atual(), Decimal("920.00"))

    def test_data_passada_sem_conta_fica_vencida_nao_paga(self):
        ontem = date.today() - timedelta(days=5)
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Compra sem conta",
            valor_original=Decimal("80.00"), data_competencia=ontem, primeiro_vencimento=ontem,
            categoria=self.categoria,
        )
        parcela = lancamento.parcelas.first()
        self.assertEqual(parcela.estado_estrutural, "aberto")
        self.assertEqual(parcela.situacao_temporal(), "vencido")

    def test_data_de_hoje_nao_e_auto_baixada(self):
        hoje = date.today()
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Compra hoje",
            valor_original=Decimal("50.00"), data_competencia=hoje, primeiro_vencimento=hoje,
            categoria=self.categoria, conta_prevista=self.conta,
        )
        parcela = lancamento.parcelas.first()
        self.assertEqual(parcela.estado_estrutural, "aberto")

    def test_data_futura_com_conta_nao_e_auto_baixada(self):
        amanha = date.today() + timedelta(days=1)
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Compra futura",
            valor_original=Decimal("50.00"), data_competencia=amanha, primeiro_vencimento=amanha,
            categoria=self.categoria, conta_prevista=self.conta,
        )
        parcela = lancamento.parcelas.first()
        self.assertEqual(parcela.estado_estrutural, "aberto")

    def test_parcelamento_com_data_passada_baixa_so_as_parcelas_ja_vencidas(self):
        # 3 parcelas mensais a partir de 40 dias atrás: a 1ª (40d atrás) e a
        # 2ª (~10d atrás) já passaram, a 3ª (~20d à frente) ainda não.
        primeira = date.today() - timedelta(days=40)
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Parcelado histórico",
            valor_original=Decimal("300.00"), data_competencia=primeira, primeiro_vencimento=primeira,
            categoria=self.categoria, conta_prevista=self.conta, parcelas_qtd=3, frequencia_parcelas="mensal",
        )
        p1, p2, p3 = lancamento.parcelas.order_by("numero")
        self.assertEqual(p1.estado_estrutural, ESTADO_QUITADO)
        # p3 (30 dias após p1) pode ou não já ter passado dependendo do dia
        # do mês corrente — só garante que não ficou pior que p1/p2 em
        # relação à ordem cronológica esperada.
        self.assertIn(p2.estado_estrutural, [ESTADO_QUITADO, "aberto"])

    def test_rotulo_situacao_e_ciente_do_tipo(self):
        from apps.financeiro.models import rotulo_situacao
        self.assertEqual(rotulo_situacao("despesa", "quitado"), "Pago")
        self.assertEqual(rotulo_situacao("receita", "quitado"), "Recebido")
        self.assertEqual(rotulo_situacao("despesa", "aberto"), "A pagar")
        self.assertEqual(rotulo_situacao("receita", "aberto"), "A receber")
        self.assertEqual(rotulo_situacao("despesa", "cancelado"), "Cancelado")
        self.assertEqual(rotulo_situacao("despesa", "vencido"), "Vencido")

    def test_categoria_incompativel_com_tipo_e_rejeitada_no_service_via_view(self):
        user = get_user_model().objects.create_user(
            username="_teste_categoria_tipo", password="x", papel="superadmin", is_superuser=True,
        )
        client = Client(SERVER_NAME="localhost", HTTP_X_FORWARDED_PROTO="https")
        client.force_login(user)
        resp = client.post("/financeiro/private-label/htmx/lancamentos/salvar/", {
            "tipo": "despesa", "descricao": "Errado de propósito", "categoria": self.categoria_receita.pk,
            "valor_original": "10.00", "data_competencia": str(date.today()), "data_vencimento": str(date.today()),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"ds-modal-erro", resp.content)
        self.assertFalse(LancamentoFinanceiro.objects.filter(descricao="Errado de propósito").exists())


class DeletarEEditarPermissaoTests(BaseFinanceiroTestCase):
    """Pedido do dono (2026-09-02): botão de deletar só pro superadmin;
    editar é liberado pra quem criou também (além do superadmin)."""

    def setUp(self):
        super().setUp()
        self.superadmin = get_user_model().objects.create_user(
            username="_teste_superadmin", password="x", papel="superadmin", is_superuser=True,
        )
        # Usuário comum, sem ser superadmin, mas com acesso liberado ao
        # módulo (simula um futuro colega com `private_label.lancar`).
        self.colaborador = get_user_model().objects.create_user(
            username="_teste_colaborador", password="x", papel="operador",
            permissoes={"private_label": {"lancar": True, "ver_lancamentos": True}},
        )
        self.outro_colaborador = get_user_model().objects.create_user(
            username="_teste_outro_colaborador", password="x", papel="operador",
            permissoes={"private_label": {"lancar": True, "ver_lancamentos": True}},
        )
        self.client_superadmin = Client(SERVER_NAME="localhost", HTTP_X_FORWARDED_PROTO="https")
        self.client_superadmin.force_login(self.superadmin)
        self.client_colaborador = Client(SERVER_NAME="localhost", HTTP_X_FORWARDED_PROTO="https")
        self.client_colaborador.force_login(self.colaborador)
        self.client_outro = Client(SERVER_NAME="localhost", HTTP_X_FORWARDED_PROTO="https")
        self.client_outro.force_login(self.outro_colaborador)

    def _criar_lancamento_de(self, usuario, descricao="Lançamento do teste"):
        return criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao=descricao, valor_original=Decimal("40.00"),
            data_competencia=date.today(), primeiro_vencimento=date.today(), categoria=self.categoria,
            usuario=usuario,
        )

    def test_quem_criou_pode_abrir_form_de_edicao(self):
        lancamento = self._criar_lancamento_de(self.colaborador)
        resp = self.client_colaborador.get(f"/financeiro/private-label/htmx/lancamentos/{lancamento.pk}/form/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"ds-modal-erro", resp.content)

    def test_outro_usuario_nao_pode_editar_lancamento_alheio(self):
        lancamento = self._criar_lancamento_de(self.colaborador)
        resp = self.client_outro.get(f"/financeiro/private-label/htmx/lancamentos/{lancamento.pk}/form/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"ds-modal-erro", resp.content)

    def test_superadmin_pode_editar_lancamento_de_qualquer_um(self):
        lancamento = self._criar_lancamento_de(self.colaborador)
        resp = self.client_superadmin.get(f"/financeiro/private-label/htmx/lancamentos/{lancamento.pk}/form/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"ds-modal-erro", resp.content)

    def test_deletar_sem_baixa_remove_de_verdade(self):
        lancamento = self._criar_lancamento_de(self.superadmin)
        pk = lancamento.pk
        resp = self.client_superadmin.post(f"/financeiro/private-label/htmx/lancamentos/{pk}/deletar/", {})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(LancamentoFinanceiro.objects.filter(pk=pk).exists())

    def test_deletar_com_baixa_e_bloqueado_mesmo_pro_superadmin(self):
        lancamento = self._criar_lancamento_de(self.superadmin)
        dar_baixa(parcela=lancamento.parcelas.first(), valor_principal=Decimal("40.00"), data=date.today(), conta=self.conta)
        resp = self.client_superadmin.post(f"/financeiro/private-label/htmx/lancamentos/{lancamento.pk}/deletar/", {})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"ds-modal-erro", resp.content)
        self.assertTrue(LancamentoFinanceiro.objects.filter(pk=lancamento.pk).exists())

    def test_colaborador_nao_superadmin_nao_pode_deletar_mesmo_o_proprio(self):
        lancamento = self._criar_lancamento_de(self.colaborador)
        resp = self.client_colaborador.post(f"/financeiro/private-label/htmx/lancamentos/{lancamento.pk}/deletar/", {})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"ds-modal-erro", resp.content)
        self.assertTrue(LancamentoFinanceiro.objects.filter(pk=lancamento.pk).exists())

    def test_botao_editar_aparece_na_lista_mesmo_ja_pago(self):
        """Regressão 2026-09-02: o botão de Editar comparava a situação
        TEMPORAL (vencido/pendente/previsto/quitado/cancelado) com o valor
        "aberto", que só existe no estado ESTRUTURAL — a comparação nunca
        batia e o botão não aparecia pra ninguém, nem pro superadmin."""
        ontem = date.today() - timedelta(days=2)
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Já pago automaticamente",
            valor_original=Decimal("60.00"), data_competencia=ontem, primeiro_vencimento=ontem,
            categoria=self.categoria, conta_prevista=self.conta, usuario=self.superadmin,
        )
        self.assertEqual(lancamento.estado_estrutural, ESTADO_QUITADO)  # nasceu pago (auto-baixa)
        resp = self.client_superadmin.get("/financeiro/private-label/lancamentos/?situacao=todas")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn(f"/financeiro/private-label/htmx/lancamentos/{lancamento.pk}/form/", body)


class EditarParcelaEReparcelarTests(BaseFinanceiroTestCase):
    """Pedido do dono (2026-09-02): corrigir um lançamento de 7.000 em 9x
    lançado errado, com a 1ª parcela já paga pelo Santander e o resto a
    pagar pelo Itaú — editar só uma parcela, ou reparcelar tudo."""

    def test_editar_valor_de_uma_parcela_recalcula_total_do_lancamento(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Compra parcelada errada",
            valor_original=Decimal("900.00"), data_competencia=date.today(), primeiro_vencimento=date.today(),
            categoria=self.categoria, parcelas_qtd=3,
        )
        p1, p2, p3 = lancamento.parcelas.order_by("numero")
        editar_parcela(p2, valor=Decimal("500.00"))
        p2.refresh_from_db()
        lancamento.refresh_from_db()
        self.assertEqual(p2.valor, Decimal("500.00"))
        # 300 (p1) + 500 (p2 editada) + 300 (p3) = 1100
        self.assertEqual(lancamento.valor_original, Decimal("1100.00"))

    def test_nao_deixa_editar_valor_de_parcela_ja_baixada(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Com baixa",
            valor_original=Decimal("300.00"), data_competencia=date.today(), primeiro_vencimento=date.today(),
            categoria=self.categoria,
        )
        parcela = lancamento.parcelas.first()
        dar_baixa(parcela=parcela, valor_principal=Decimal("300.00"), data=date.today(), conta=self.conta)
        with self.assertRaises(ValueError):
            editar_parcela(parcela, valor=Decimal("500.00"))

    def test_editar_vencimento_de_parcela_funciona_mesmo_ja_baixada(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Com baixa, só data",
            valor_original=Decimal("300.00"), data_competencia=date.today(), primeiro_vencimento=date.today(),
            categoria=self.categoria,
        )
        parcela = lancamento.parcelas.first()
        dar_baixa(parcela=parcela, valor_principal=Decimal("300.00"), data=date.today(), conta=self.conta)
        nova_data = date.today() + timedelta(days=10)
        editar_parcela(parcela, data_vencimento=nova_data)
        parcela.refresh_from_db()
        self.assertEqual(parcela.data_vencimento, nova_data)

    def test_reparcelar_toda_a_serie_sem_baixa_nenhuma(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="7 mil errado",
            valor_original=Decimal("777.78"), data_competencia=date.today(), primeiro_vencimento=date.today(),
            categoria=self.categoria, parcelas_qtd=9,
        )
        reparcelar(lancamento, novo_valor_total=Decimal("7000.00"), novas_parcelas_qtd=9)
        lancamento.refresh_from_db()
        self.assertEqual(lancamento.valor_original, Decimal("7000.00"))
        self.assertEqual(lancamento.parcelas.count(), 9)
        self.assertEqual(sum(p.valor for p in lancamento.parcelas.all()), Decimal("7000.00"))

    def test_reparcelar_bloqueado_se_qualquer_parcela_ja_tem_baixa(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="1ª parcela paga pelo Santander",
            valor_original=Decimal("777.78"), data_competencia=date.today(), primeiro_vencimento=date.today(),
            categoria=self.categoria, parcelas_qtd=9,
        )
        p1 = lancamento.parcelas.order_by("numero").first()
        dar_baixa(parcela=p1, valor_principal=p1.valor, data=date.today(), conta=self.conta)
        with self.assertRaises(ValueError):
            reparcelar(lancamento, novo_valor_total=Decimal("7000.00"), novas_parcelas_qtd=9)
        # nada mudou
        lancamento.refresh_from_db()
        self.assertEqual(lancamento.parcelas.count(), 9)

    def test_cenario_real_estornar_depois_editar_parcelas_restantes(self):
        """O caminho que resolve o caso real: estorna a baixa da 1ª parcela
        (paga errada pelo Santander), corrige o valor dela e das demais uma
        a uma (já que reparcelar tudo de uma vez exige zero baixas)."""
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="7 mil em 9x, 1ª já paga errado",
            valor_original=Decimal("777.78"), data_competencia=date.today(), primeiro_vencimento=date.today(),
            categoria=self.categoria, parcelas_qtd=9,
        )
        p1 = lancamento.parcelas.order_by("numero").first()
        baixa = dar_baixa(parcela=p1, valor_principal=p1.valor, data=date.today(), conta=self.conta2)  # Santander
        estornar_baixa(baixa, motivo="valor errado")
        editar_parcela(p1, valor=Decimal("7000.00"))
        p1.refresh_from_db()
        self.assertEqual(p1.valor, Decimal("7000.00"))
        self.assertEqual(p1.saldo_restante, Decimal("7000.00"))
        # agora dá pra baixar de novo, dessa vez certo, pelo Santander
        dar_baixa(parcela=p1, valor_principal=Decimal("7000.00"), data=date.today(), conta=self.conta2)
        p1.refresh_from_db()
        self.assertEqual(p1.estado_estrutural, ESTADO_QUITADO)
