"""Lógica de negócio para o módulo Metas: leitura do CSV e cálculos de desempenho."""

from __future__ import annotations

import calendar
import csv
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

# ── Constantes de negócio ──────────────────────────────────────────────────────

CSV_BASE = Path("/var/www/della-sistemas/data/Relatorio de Vendas Atendidas")

# Situações que entram na meta INDIVIDUAL da vendedora
SITUACOES_META_INDIVIDUAL: set[str] = {"Atendido", "Atendido-Anaca"}

# Mapeamento de canal → lista de situações Bling
CANAL_SITUACOES: dict[str, list[str]] = {
    "show_room_sp":   ["Atendido"],
    "anaca":          ["Atendido-Anaca"],
    "atacado":        ["Atendido-Atacado"],
    "site_instagram": ["Atendido-Site", "Atendido-Instagram"],
    "londrina":       ["Atendido-Londrina"],
}

CANAL_LABELS: dict[str, str] = {
    "show_room_sp":   "Show Room SP",
    "anaca":          "Anacã SP",
    "atacado":        "Atacado",
    "site_instagram": "Instagram / Site",
    "londrina":       "Show Room Londrina",
}

# Canais que NUNCA têm meta (só faturamento)
CANAIS_SEM_META: set[str] = {"londrina"}

# Mês a partir do qual as metas individuais entram em vigor (retroativo a jan/2026)
ANO_MES_INICIO_INDIVIDUAL = (2026, 1)

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_valor(raw: str | Any) -> Decimal:
    """Converte string de valor monetário para Decimal."""
    if raw is None:
        return Decimal("0")
    s = str(raw).strip().replace("R$", "").replace(" ", "")
    if not s:
        return Decimal("0")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")


def _parse_int(raw: str | Any) -> int:
    try:
        return int(str(raw).strip())
    except Exception:
        return 0


def _pct(realizado: Decimal, meta: Decimal) -> float:
    if meta <= 0:
        return 0.0
    return float(realizado / meta * 100)


def usa_metas_individuais(ano: int, mes: int) -> bool:
    return (ano, mes) >= ANO_MES_INICIO_INDIVIDUAL


def dias_seg_a_sab_restantes(ano_fim: int, mes_fim: int) -> int:
    """Conta dias Seg-Sáb restantes até o fim do mês (incluindo hoje)."""
    hoje = date.today()
    ultimo = date(ano_fim, mes_fim, calendar.monthrange(ano_fim, mes_fim)[1])
    if hoje > ultimo:
        return 0
    count = 0
    d = hoje
    while d <= ultimo:
        if d.weekday() <= 5:  # 0=Seg … 5=Sáb
            count += 1
        d += timedelta(days=1)
    return count


def calcular_por_semana(faltam: Decimal, dias: int) -> Decimal:
    """Quanto precisa vender por semana (semana de 6 dias Seg-Sáb)."""
    if dias <= 0 or faltam <= 0:
        return Decimal("0")
    return (faltam / Decimal(dias) * Decimal("6")).quantize(Decimal("0.01"))


# ── Carregamento do CSV ────────────────────────────────────────────────────────

def _iter_months(ano_ini: int, mes_ini: int, ano_fim: int, mes_fim: int):
    """Gera (ano, mes) para cada mês no intervalo inclusivo."""
    a, m = ano_ini, mes_ini
    while (a, m) <= (ano_fim, mes_fim):
        yield a, m
        m += 1
        if m > 12:
            m, a = 1, a + 1


def carregar_vendas_periodo(ano_ini: int, mes_ini: int, ano_fim: int, mes_fim: int) -> list[dict[str, Any]]:
    """Carrega vendas de todos os meses no período."""
    result: list[dict[str, Any]] = []
    for a, m in _iter_months(ano_ini, mes_ini, ano_fim, mes_fim):
        result.extend(carregar_vendas(a, m))
    return result


def carregar_vendas(ano: int, mes: int) -> list[dict[str, Any]]:
    """Lê o CSV de vendas atendidas e retorna pedidos do mês/ano filtrado."""
    csv_path = CSV_BASE / f"vendas_atendidas_{ano}.csv"
    if not csv_path.exists():
        return []

    mes_str = f"{ano}-{mes:02d}"
    resultado: list[dict[str, Any]] = []

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            data = str(row.get("data") or "").strip()
            if not data.startswith(mes_str):
                continue
            resultado.append({
                "pedido_id": row.get("pedido_id", ""),
                "data": data,
                "total": _parse_valor(row.get("total")),
                "situacao": str(row.get("situacao") or "").strip(),
                "qtd_itens": _parse_int(row.get("qtd_itens")),
                "vendedor": str(row.get("vendedor") or "").strip(),
                "cliente": str(row.get("cliente") or "").strip(),
            })

    return resultado


# ── Cálculos ───────────────────────────────────────────────────────────────────

def calcular_individual(
    vendas: list[dict],
    funcionarios: list,
    metas_ind: list,
) -> list[dict]:
    """
    Para cada funcionária com meta no mês: soma vendas onde
    situacao in SITUACOES_META_INDIVIDUAL E vendedor == funcionario.nome_bling.
    """
    meta_map: dict[int, Decimal] = {}
    for m in metas_ind:
        meta_map[m.funcionario_id] = meta_map.get(m.funcionario_id, Decimal("0")) + m.valor

    resultado = []
    for func in funcionarios:
        if not func.ativo:
            continue
        meta_val = meta_map.get(func.id, Decimal("0"))
        total = Decimal("0")
        pecas = 0
        for v in vendas:
            if (
                v["situacao"] in SITUACOES_META_INDIVIDUAL
                and v["vendedor"].upper() == func.nome_bling.upper()
            ):
                total += v["total"]
                pecas += v["qtd_itens"]

        faltam = max(meta_val - total, Decimal("0")) if meta_val > 0 else Decimal("0")
        resultado.append({
            "nome": func.nome,
            "nome_bling": func.nome_bling,
            "meta": meta_val,
            "realizado": total,
            "faltam": faltam,
            "pecas": pecas,
            "pct": _pct(total, meta_val),
            "tem_meta": meta_val > 0,
        })

    resultado.sort(key=lambda x: (-float(x["realizado"])))
    return resultado


def calcular_canais(
    vendas: list[dict],
    metas_canal: list,
    ano: int,
    mes: int,
    funcionarios_com_meta: list | None = None,
    metas_ind: list | None = None,
) -> list[dict]:
    """
    Retorna desempenho por canal.
    - Jan-Jun: meta vem de MetaCanal para todos os 4 canais.
    - Jul+: Show Room SP e Anacã têm meta = sum(MetaFuncionario) do canal;
            Atacado e Site/Instagram mantêm MetaCanal.
    """
    canal_meta_map: dict[str, Decimal] = {}
    for m in metas_canal:
        canal_meta_map[m.canal] = canal_meta_map.get(m.canal, Decimal("0")) + m.valor

    # Meta de Show Room e Anacã no modo individual = sum das metas individuais
    # de funcionárias que venderam naquele canal (aproximado como total das metas individuais)
    meta_individual_por_canal: dict[str, Decimal] = {"show_room_sp": Decimal("0"), "anaca": Decimal("0")}
    if usa_metas_individuais(ano, mes) and funcionarios_com_meta and metas_ind:
        meta_map_ind: dict[int, Decimal] = {m.funcionario_id: m.valor for m in metas_ind}
        for func in funcionarios_com_meta:
            if func.id in meta_map_ind:
                meta_individual_por_canal["show_room_sp"] += meta_map_ind[func.id]
                meta_individual_por_canal["anaca"] += meta_map_ind[func.id]
        # Dividir de forma que cada canal derive meta de suas próprias vendas
        # Simplificação: Show Room SP e Anacã herdam toda a meta individual (usuário
        # pode refinar com MetaCanal explícita se quiser)

    resultado = []
    for canal_key, situacoes in CANAL_SITUACOES.items():
        total = sum(
            (v["total"] for v in vendas if v["situacao"] in situacoes),
            Decimal("0"),
        )
        pecas = sum(v["qtd_itens"] for v in vendas if v["situacao"] in situacoes)

        if canal_key in CANAIS_SEM_META:
            # Londrina: só faturamento, sem meta
            resultado.append({
                "canal_key": canal_key,
                "label": CANAL_LABELS[canal_key],
                "meta": Decimal("0"),
                "realizado": total,
                "faltam": Decimal("0"),
                "pecas": pecas,
                "pct": 0.0,
                "tem_meta": False,
            })
            continue

        # Determina meta
        if usa_metas_individuais(ano, mes) and canal_key in ("show_room_sp", "anaca"):
            meta_val = canal_meta_map.get(canal_key, Decimal("0"))
            if meta_val == 0:
                meta_val = meta_individual_por_canal.get(canal_key, Decimal("0"))
        else:
            meta_val = canal_meta_map.get(canal_key, Decimal("0"))

        faltam_canal = max(meta_val - total, Decimal("0")) if meta_val > 0 else Decimal("0")
        resultado.append({
            "canal_key": canal_key,
            "label": CANAL_LABELS[canal_key],
            "meta": meta_val,
            "realizado": total,
            "faltam": faltam_canal,
            "pecas": pecas,
            "pct": _pct(total, meta_val),
            "tem_meta": meta_val > 0,
        })

    return resultado


def calcular_lojas(vendas: list[dict]) -> list[dict]:
    """Faturamento total por loja/canal (5 lojas, incluindo Londrina sem meta)."""
    resultado = []
    total_geral = sum((v["total"] for v in vendas), Decimal("0"))

    for canal_key, situacoes in CANAL_SITUACOES.items():
        total = sum(
            (v["total"] for v in vendas if v["situacao"] in situacoes),
            Decimal("0"),
        )
        pecas = sum(v["qtd_itens"] for v in vendas if v["situacao"] in situacoes)
        pct_total = float(total / total_geral * 100) if total_geral > 0 else 0.0

        resultado.append({
            "canal_key": canal_key,
            "label": CANAL_LABELS[canal_key],
            "total": total,
            "pecas": pecas,
            "pct_total": pct_total,
            "sem_meta": canal_key in CANAIS_SEM_META,
        })

    resultado.sort(key=lambda x: -float(x["total"]))
    return resultado


def calcular_geral_vendedoras(vendas: list[dict], funcionarios: list) -> list[dict]:
    """
    Agrupa faturamento por vendedor (todos, incluindo sem meta e sem nome).
    """
    agg: dict[str, dict] = {}

    for v in vendas:
        nome = v["vendedor"] or "(sem vendedora)"
        if nome not in agg:
            agg[nome] = {"total": Decimal("0"), "pecas": 0, "situacoes": {}}
        agg[nome]["total"] += v["total"]
        agg[nome]["pecas"] += v["qtd_itens"]
        sit = v["situacao"]
        agg[nome]["situacoes"][sit] = agg[nome]["situacoes"].get(sit, 0) + int(v["total"])

    nome_bling_set = {f.nome_bling.upper() for f in funcionarios}

    resultado = []
    for nome, dados in sorted(agg.items(), key=lambda x: -float(x[1]["total"])):
        resultado.append({
            "vendedora": nome,
            "tem_meta": nome.upper() in nome_bling_set,
            "total": dados["total"],
            "pecas": dados["pecas"],
        })

    return resultado


def calcular_por_situacao(vendas: list[dict]) -> list[dict]:
    """Agrupa faturamento por situação."""
    agg: dict[str, dict] = {}
    for v in vendas:
        sit = v["situacao"] or "Outros"
        if sit not in agg:
            agg[sit] = {"total": Decimal("0"), "pecas": 0}
        agg[sit]["total"] += v["total"]
        agg[sit]["pecas"] += v["qtd_itens"]

    total_geral = sum((d["total"] for d in agg.values()), Decimal("0"))

    resultado = []
    for sit, dados in sorted(agg.items(), key=lambda x: -float(x[1]["total"])):
        resultado.append({
            "situacao": sit,
            "total": dados["total"],
            "pecas": dados["pecas"],
            "pct_total": float(dados["total"] / total_geral * 100) if total_geral > 0 else 0.0,
        })
    return resultado


def total_geral_mes(vendas: list[dict]) -> dict:
    total = sum((v["total"] for v in vendas), Decimal("0"))
    pecas = sum(v["qtd_itens"] for v in vendas)
    return {"total": total, "pecas": pecas}


def meses_disponiveis() -> list[tuple[int, int, str]]:
    """Retorna lista de (ano, mes, label) com dados disponíveis nos CSVs."""
    resultado = []
    hoje = date.today()

    for csv_file in sorted(CSV_BASE.glob("vendas_atendidas_*.csv"), reverse=True):
        try:
            ano = int(csv_file.stem.replace("vendas_atendidas_", ""))
        except ValueError:
            continue
        for mes in range(12, 0, -1):
            if ano == hoje.year and mes > hoje.month:
                continue
            resultado.append((ano, mes, f"{MESES_PT[mes]}/{ano}"))

    return resultado
