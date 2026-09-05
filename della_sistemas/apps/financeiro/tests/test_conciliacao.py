"""Testes da Fase 3 (Conciliação bancária) — parser OFX/CSV + sugestão de
conciliação. Ver `services/private_label/extrato.py`."""
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.financeiro.models import Conciliacao, ImportacaoExtrato, ItemExtrato
from apps.financeiro.services.private_label.baixas import dar_baixa
from apps.financeiro.services.private_label.extrato import (
    ExtratoInvalido,
    conciliar_manualmente,
    confirmar_conciliacao,
    desfazer_conciliacao,
    ignorar_item,
    importar_extrato,
    parse_csv,
    parse_ofx,
    rejeitar_conciliacao,
)
from apps.financeiro.services.private_label.lancamentos import criar_lancamento
from apps.financeiro.tests.test_private_label import BaseFinanceiroTestCase

OFX_EXEMPLO = """OFXHEADER:100
DATA:OFXSGML
<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<BANKTRANLIST>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260905120000
<TRNAMT>-150.00
<FITID>2026090500001
<MEMO>Pagamento fornecedor
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20260906120000
<TRNAMT>500.00
<FITID>2026090600002
<MEMO>Recebimento cliente
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""

CSV_EXEMPLO = "data;valor;descricao\n05/09/2026;-150,00;Pagamento fornecedor\n06/09/2026;500,00;Recebimento cliente\n"


class ParserOfxTests(BaseFinanceiroTestCase):
    def test_parse_ofx_extrai_data_valor_e_descricao(self):
        itens = parse_ofx(OFX_EXEMPLO)
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[0].data, date(2026, 9, 5))
        self.assertEqual(itens[0].valor, Decimal("-150.00"))
        self.assertEqual(itens[0].descricao, "Pagamento fornecedor")
        self.assertEqual(itens[0].identificador_externo, "2026090500001")

    def test_parse_ofx_sem_transacao_levanta_erro(self):
        with self.assertRaises(ExtratoInvalido):
            parse_ofx("<OFX><BANKMSGSRSV1></BANKMSGSRSV1></OFX>")


class ParserCsvTests(BaseFinanceiroTestCase):
    def test_parse_csv_com_virgula_decimal_br(self):
        itens = parse_csv(CSV_EXEMPLO)
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[0].data, date(2026, 9, 5))
        self.assertEqual(itens[0].valor, Decimal("-150.00"))
        self.assertEqual(itens[1].valor, Decimal("500.00"))

    def test_parse_csv_sem_colunas_obrigatorias_levanta_erro(self):
        with self.assertRaises(ExtratoInvalido):
            parse_csv("nome;telefone\nfulano;123456\n")


class ImportarExtratoTests(BaseFinanceiroTestCase):
    def _upload(self, conteudo: str, nome="extrato.ofx"):
        return SimpleUploadedFile(nome, conteudo.encode("utf-8"), content_type="text/plain")

    def test_importar_ofx_cria_itens_e_sugere_conciliacao_por_data_e_valor(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Fornecedor",
            valor_original=Decimal("150.00"), data_competencia=date(2026, 9, 5),
            primeiro_vencimento=date(2026, 9, 5), categoria=self.categoria,
        )
        dar_baixa(parcela=lancamento.parcelas.first(), valor_principal=Decimal("150.00"), data=date(2026, 9, 5), conta=self.conta)

        importacao = importar_extrato(operacao=self.operacao, conta=self.conta, arquivo_upload=self._upload(OFX_EXEMPLO), usuario=None)
        self.assertEqual(importacao.total_itens, 2)

        item_150 = ItemExtrato.objects.get(importacao=importacao, valor=Decimal("-150.00"))
        conciliacao = Conciliacao.objects.get(item_extrato=item_150)
        self.assertEqual(conciliacao.nivel_confianca, "alta")
        self.assertEqual(conciliacao.status, "sugerido")

    def test_reimportar_mesmo_arquivo_e_bloqueado(self):
        importar_extrato(operacao=self.operacao, conta=self.conta, arquivo_upload=self._upload(OFX_EXEMPLO), usuario=None)
        with self.assertRaises(ExtratoInvalido):
            importar_extrato(operacao=self.operacao, conta=self.conta, arquivo_upload=self._upload(OFX_EXEMPLO), usuario=None)

    def test_item_sem_sugestao_fica_pendente(self):
        importacao = importar_extrato(operacao=self.operacao, conta=self.conta, arquivo_upload=self._upload(OFX_EXEMPLO), usuario=None)
        item = importacao.itens.first()
        self.assertEqual(item.status, "pendente")
        self.assertFalse(Conciliacao.objects.filter(item_extrato=item).exists())


class FluxoDeRevisaoTests(BaseFinanceiroTestCase):
    def _upload(self, conteudo: str, nome="extrato.ofx"):
        return SimpleUploadedFile(nome, conteudo.encode("utf-8"), content_type="text/plain")

    def _importar_com_baixa_casada(self):
        lancamento = criar_lancamento(
            operacao=self.operacao, tipo="despesa", descricao="Fornecedor",
            valor_original=Decimal("150.00"), data_competencia=date(2026, 9, 5),
            primeiro_vencimento=date(2026, 9, 5), categoria=self.categoria,
        )
        dar_baixa(parcela=lancamento.parcelas.first(), valor_principal=Decimal("150.00"), data=date(2026, 9, 5), conta=self.conta)
        return importar_extrato(operacao=self.operacao, conta=self.conta, arquivo_upload=self._upload(OFX_EXEMPLO), usuario=None)

    def test_confirmar_conciliacao_marca_item_como_conciliado(self):
        importacao = self._importar_com_baixa_casada()
        conciliacao = Conciliacao.objects.get(item_extrato__importacao=importacao, item_extrato__valor=Decimal("-150.00"))
        confirmar_conciliacao(conciliacao)
        conciliacao.item_extrato.refresh_from_db()
        self.assertEqual(conciliacao.item_extrato.status, "conciliado")

    def test_rejeitar_sugestao_volta_item_para_pendente_e_libera_movimento(self):
        importacao = self._importar_com_baixa_casada()
        conciliacao = Conciliacao.objects.get(item_extrato__importacao=importacao, item_extrato__valor=Decimal("-150.00"))
        rejeitar_conciliacao(conciliacao)
        conciliacao.item_extrato.refresh_from_db()
        self.assertEqual(conciliacao.item_extrato.status, "pendente")
        self.assertEqual(conciliacao.status, "rejeitado")

    def test_desfazer_conciliacao_confirmada_volta_item_para_pendente(self):
        importacao = self._importar_com_baixa_casada()
        conciliacao = Conciliacao.objects.get(item_extrato__importacao=importacao, item_extrato__valor=Decimal("-150.00"))
        confirmar_conciliacao(conciliacao)
        desfazer_conciliacao(conciliacao)
        conciliacao.item_extrato.refresh_from_db()
        self.assertEqual(conciliacao.item_extrato.status, "pendente")

    def test_ignorar_item_marca_como_ignorado(self):
        importacao = importar_extrato(operacao=self.operacao, conta=self.conta, arquivo_upload=self._upload(OFX_EXEMPLO), usuario=None)
        item = importacao.itens.first()
        ignorar_item(item)
        item.refresh_from_db()
        self.assertEqual(item.status, "ignorado")

    def test_conciliar_manualmente_um_movimento_ja_vinculado_e_bloqueado(self):
        importacao = self._importar_com_baixa_casada()
        item_500 = importacao.itens.get(valor=Decimal("500.00"))
        conciliacao_150 = Conciliacao.objects.get(item_extrato__valor=Decimal("-150.00"))
        with self.assertRaises(ValueError):
            conciliar_manualmente(item_500, conciliacao_150.movimento)
