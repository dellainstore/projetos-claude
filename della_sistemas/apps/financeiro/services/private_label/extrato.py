"""Importação de extrato bancário (OFX/CSV) e conciliação (Fase 3) — ver
plano, seção 1.4.

Parser de OFX escrito à mão (regex sobre o SGML/XML solto que os bancos
exportam) em vez de adicionar uma lib nova (`ofxparse`) sem necessidade
comprovada — mesma decisão já tomada pra máscara de dinheiro BRL (ver
plano, seção 19). Cobre o bloco `<STMTTRN>...</STMTTRN>` (às vezes sem
fechamento explícito das tags internas, comum em OFX 1.x SGML) com os
campos usados por praticamente todo banco brasileiro: `DTPOSTED`,
`TRNAMT`, `MEMO`/`NAME`, `FITID`.
"""
import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.financeiro.models import Conciliacao, ImportacaoExtrato, ItemExtrato, MovimentoConta
from .auditoria import registrar_log

EXTENSOES_PERMITIDAS = {"ofx", "qfx", "csv"}


@dataclass
class ItemBruto:
    data: date
    valor: Decimal
    descricao: str
    identificador_externo: str = ""


class ExtratoInvalido(ValueError):
    pass


# ── Parsers ──────────────────────────────────────────────────────────────

_RE_STMTTRN = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.IGNORECASE | re.DOTALL)
_RE_TAG = re.compile(r"<(\w+)>\s*([^<\r\n]*)")


def _extrair_tags(bloco: str) -> dict:
    return {m.group(1).upper(): m.group(2).strip() for m in _RE_TAG.finditer(bloco)}


def _data_ofx(bruto: str) -> date:
    # formato DTPOSTED: YYYYMMDD[HHMMSS][.xxx][[tz:TZ]] — só os 8 primeiros
    # dígitos importam pra data.
    digitos = re.sub(r"\D", "", bruto)[:8]
    if len(digitos) != 8:
        raise ExtratoInvalido(f"Data OFX inválida: {bruto!r}")
    return datetime.strptime(digitos, "%Y%m%d").date()


def parse_ofx(conteudo: str) -> list[ItemBruto]:
    blocos = _RE_STMTTRN.findall(conteudo)
    if not blocos:
        raise ExtratoInvalido("Nenhuma transação (<STMTTRN>) encontrada no arquivo OFX.")
    itens = []
    for bloco in blocos:
        tags = _extrair_tags(bloco)
        if "DTPOSTED" not in tags or "TRNAMT" not in tags:
            continue
        try:
            valor = Decimal(tags["TRNAMT"].replace(",", "."))
        except InvalidOperation:
            continue
        descricao = tags.get("MEMO") or tags.get("NAME") or ""
        itens.append(ItemBruto(
            data=_data_ofx(tags["DTPOSTED"]), valor=valor, descricao=descricao,
            identificador_externo=tags.get("FITID", ""),
        ))
    if not itens:
        raise ExtratoInvalido("Nenhuma transação válida (com data e valor) encontrada no OFX.")
    return itens


def parse_csv(conteudo: str) -> list[ItemBruto]:
    """Espera colunas (nome flexível, case-insensitive) `data`, `valor` e
    `descricao`/`historico`. Detecta separador `;` ou `,` automaticamente."""
    amostra = conteudo[:2048]
    try:
        dialeto = csv.Sniffer().sniff(amostra, delimiters=";,")
    except csv.Error:
        dialeto = csv.excel
        dialeto.delimiter = ";" if amostra.count(";") > amostra.count(",") else ","

    leitor = csv.DictReader(io.StringIO(conteudo), dialect=dialeto)
    if not leitor.fieldnames:
        raise ExtratoInvalido("CSV sem cabeçalho reconhecível.")
    colunas = {c.strip().lower(): c for c in leitor.fieldnames}

    def _coluna(*opcoes):
        for opcao in opcoes:
            if opcao in colunas:
                return colunas[opcao]
        return None

    col_data = _coluna("data", "date")
    col_valor = _coluna("valor", "value", "amount")
    col_descricao = _coluna("descricao", "descrição", "historico", "histórico", "memo", "description")
    if not col_data or not col_valor:
        raise ExtratoInvalido("CSV precisa ter pelo menos as colunas 'data' e 'valor'.")

    itens = []
    for linha in leitor:
        bruto_data = (linha.get(col_data) or "").strip()
        bruto_valor = (linha.get(col_valor) or "").strip()
        if not bruto_data or not bruto_valor:
            continue
        itens.append(ItemBruto(
            data=_data_csv(bruto_data), valor=_valor_csv(bruto_valor),
            descricao=(linha.get(col_descricao) or "").strip() if col_descricao else "",
        ))
    if not itens:
        raise ExtratoInvalido("Nenhuma linha válida encontrada no CSV.")
    return itens


def _data_csv(bruto: str) -> date:
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(bruto, formato).date()
        except ValueError:
            continue
    raise ExtratoInvalido(f"Data '{bruto}' não reconhecida (use AAAA-MM-DD ou DD/MM/AAAA).")


def _valor_csv(bruto: str) -> Decimal:
    limpo = bruto.replace("R$", "").strip()
    # decide separador decimal: se tem vírgula E ponto, o último é o
    # decimal (ex.: "1.234,56" BR ou "1,234.56" US); se só vírgula, é BR.
    if "," in limpo and "." in limpo:
        if limpo.rfind(",") > limpo.rfind("."):
            limpo = limpo.replace(".", "").replace(",", ".")
        else:
            limpo = limpo.replace(",", "")
    elif "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return Decimal(limpo)
    except InvalidOperation:
        raise ExtratoInvalido(f"Valor '{bruto}' não é um número válido.")


def _formato_por_extensao(nome_arquivo: str) -> str:
    extensao = nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else ""
    if extensao not in EXTENSOES_PERMITIDAS:
        raise ExtratoInvalido(f"Extensão '.{extensao}' não suportada — use .ofx, .qfx ou .csv.")
    return "csv" if extensao == "csv" else "ofx"


def _hash_transacao(item: ItemBruto) -> str:
    chave = f"{item.data.isoformat()}|{item.valor}|{item.descricao}|{item.identificador_externo}"
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


# ── Import + conciliação ─────────────────────────────────────────────────

@transaction.atomic
def importar_extrato(*, operacao, conta, arquivo_upload, usuario=None) -> ImportacaoExtrato:
    """`arquivo_upload` é o `UploadedFile` do Django (`request.FILES`)."""
    conteudo_bytes = arquivo_upload.read()
    hash_arquivo = hashlib.sha256(conteudo_bytes).hexdigest()
    if ImportacaoExtrato.objects.filter(hash_arquivo=hash_arquivo).exists():
        raise ExtratoInvalido("Este arquivo já foi importado antes (mesmo conteúdo).")

    formato = _formato_por_extensao(arquivo_upload.name)
    conteudo_texto = conteudo_bytes.decode("utf-8-sig", errors="replace")
    itens_brutos = parse_ofx(conteudo_texto) if formato == "ofx" else parse_csv(conteudo_texto)

    arquivo_upload.seek(0)
    importacao = ImportacaoExtrato.objects.create(
        operacao=operacao, conta=conta, arquivo=arquivo_upload, nome_original=arquivo_upload.name,
        formato=formato, hash_arquivo=hash_arquivo, total_itens=len(itens_brutos), importado_por=usuario,
    )

    itens_criados = []
    hashes_vistos = set()
    for bruto in itens_brutos:
        h = _hash_transacao(bruto)
        if h in hashes_vistos:
            continue  # mesma transação duplicada dentro do próprio arquivo
        hashes_vistos.add(h)
        itens_criados.append(ItemExtrato(
            importacao=importacao, data=bruto.data, valor=bruto.valor, descricao=bruto.descricao,
            identificador_externo=bruto.identificador_externo, hash_transacao=h,
        ))
    ItemExtrato.objects.bulk_create(itens_criados)
    importacao.total_itens = len(itens_criados)
    importacao.save(update_fields=["total_itens"])

    registrar_log(
        operacao=operacao, entidade="importacao_extrato", objeto_id=importacao.id, acao="criacao",
        usuario=usuario, valor_para=f"{importacao.nome_original} — {len(itens_criados)} itens",
    )

    sugerir_conciliacoes(importacao)
    return importacao


def sugerir_conciliacoes(importacao: ImportacaoExtrato) -> int:
    """Sugere `MovimentoConta` candidatos pra cada item pendente da conta
    da importação: mesma data + mesmo valor = confiança alta; valor igual
    com data até 3 dias de diferença = confiança média. Só considera
    movimentos ainda sem conciliação ATIVA (sugerida ou confirmada) — um
    movimento nunca é sugerido pra 2 itens ao mesmo tempo."""
    from datetime import timedelta

    movimentos_ja_usados = set(
        Conciliacao.objects.filter(
            item_extrato__importacao__conta=importacao.conta, status__in=["sugerido", "confirmado"],
            desfeita_em__isnull=True,
        ).exclude(movimento__isnull=True).values_list("movimento_id", flat=True)
    )
    candidatos = list(
        MovimentoConta.objects.filter(conta=importacao.conta).exclude(id__in=movimentos_ja_usados)
    )

    total_sugeridas = 0
    for item in importacao.itens.filter(status="pendente"):
        melhor = None
        melhor_nivel = None
        for movimento in candidatos:
            if movimento.id in movimentos_ja_usados:
                continue
            if movimento.valor != item.valor:
                continue
            diferenca_dias = abs((movimento.data - item.data).days)
            if diferenca_dias == 0:
                melhor, melhor_nivel = movimento, "alta"
                break
            if diferenca_dias <= 3 and melhor is None:
                melhor, melhor_nivel = movimento, "media"
        if melhor:
            Conciliacao.objects.create(item_extrato=item, movimento=melhor, nivel_confianca=melhor_nivel, status="sugerido")
            movimentos_ja_usados.add(melhor.id)
            total_sugeridas += 1
    return total_sugeridas


@transaction.atomic
def confirmar_conciliacao(conciliacao: Conciliacao, *, usuario=None) -> Conciliacao:
    if conciliacao.status == "confirmado":
        return conciliacao
    conciliacao.status = "confirmado"
    conciliacao.usuario = usuario
    conciliacao.save(update_fields=["status", "usuario"])
    conciliacao.item_extrato.status = "conciliado"
    conciliacao.item_extrato.save(update_fields=["status"])
    return conciliacao


@transaction.atomic
def rejeitar_conciliacao(conciliacao: Conciliacao, *, usuario=None) -> Conciliacao:
    conciliacao.status = "rejeitado"
    conciliacao.usuario = usuario
    conciliacao.desfeita_em = timezone.now()
    conciliacao.save(update_fields=["status", "usuario", "desfeita_em"])
    conciliacao.item_extrato.status = "pendente"
    conciliacao.item_extrato.save(update_fields=["status"])
    return conciliacao


@transaction.atomic
def conciliar_manualmente(item_extrato: ItemExtrato, movimento: MovimentoConta, *, usuario=None) -> Conciliacao:
    if item_extrato.status == "conciliado":
        raise ValueError("Este item já está conciliado.")
    ja_usado = Conciliacao.objects.filter(
        movimento=movimento, status__in=["sugerido", "confirmado"], desfeita_em__isnull=True,
    ).exists()
    if ja_usado:
        raise ValueError("Este movimento já está vinculado a outro item do extrato.")
    conciliacao = Conciliacao.objects.create(
        item_extrato=item_extrato, movimento=movimento, nivel_confianca="manual",
        status="confirmado", usuario=usuario,
    )
    item_extrato.status = "conciliado"
    item_extrato.save(update_fields=["status"])
    return conciliacao


@transaction.atomic
def ignorar_item(item_extrato: ItemExtrato) -> ItemExtrato:
    item_extrato.status = "ignorado"
    item_extrato.save(update_fields=["status"])
    return item_extrato


@transaction.atomic
def desfazer_conciliacao(conciliacao: Conciliacao, *, usuario=None) -> Conciliacao:
    if conciliacao.status != "confirmado":
        raise ValueError("Só dá pra desfazer uma conciliação confirmada.")
    conciliacao.desfeita_em = timezone.now()
    conciliacao.status = "rejeitado"
    conciliacao.usuario = usuario
    conciliacao.save(update_fields=["desfeita_em", "status", "usuario"])
    conciliacao.item_extrato.status = "pendente"
    conciliacao.item_extrato.save(update_fields=["status"])
    return conciliacao
