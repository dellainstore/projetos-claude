# metas.py
# ============================================================
# ✅ GERA PDF DE METAS (ANO PARAMETRIZADO) A PARTIR DO CSV DE VENDAS
# - Não chama API do Bling
# - Lê: vendas_atendidas_<ANO>.csv (sep=";" | utf-8-sig)
# - Lê: metas_<YY>.csv (manual)
# - Salva: Metas_Faturamento_<ANO>.pdf
# - Mês vigente (somente se ano_ref == ano atual): "PARCIAL ATÉ dd/mm/aaaa HH:MM"
# - Meses anteriores / ano passado: "METAS FECHADAS"
# - Não mostra meses futuros
# - RESUMO ANUAL POR LOJA no final
# - ✅ "QTD PEÇAS VENDIDAS" por LOJA (filtrando por "situacao", igual ao faturamento)
# - ✅ Ajuste alinhamento da faixa de título com tabela + tabela fecha na página
# - ✅ Copia o PDF também para: G:\Meu Drive\Relatorios
#
# COMO RODAR (PowerShell):
#   cd "C:\Users\netog\OneDrive\Della\DELLA 2026\Relatório de Metas"
#   python metas.py 2026
#   python metas.py 2025
#
# IMPORTANTE (SEU CASO):
# ✅ Mesmo para 2025, os arquivos ficam na pasta DELLA 2026:
#    ...\DELLA 2026\Relatório de Vendas Atendidas\vendas_atendidas_2025.csv
#    ...\DELLA 2026\Documentos Auxiliares Manuais\metas_25.csv
# ============================================================

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, List, Optional
import argparse
import os
import shutil

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph


# ================== CONFIG BASE (VPS) ==================
SCRIPT_DIR = Path(__file__).resolve().parent

PASTA_VENDAS      = Path("/var/www/della-sistemas/data/Relatorio de Vendas Atendidas")
PASTA_AUX         = SCRIPT_DIR   # metas_25.csv, metas_26.csv estão aqui
PASTA_METAS       = SCRIPT_DIR   # PDFs salvos aqui

# Cópia extra: feita via rclone no cron após geração do PDF
PASTA_EXTRA_COPIA = Path("/tmp/metas_extra_copia_desativada")  # inexistente → silencia


# ================== UTILITÁRIOS ==================
MESES_PT = {
    1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL",
    5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
    9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO",
}

def label_mes_slash(ano_mes: str) -> str:
    y, m = ano_mes.split("-")
    return f"{MESES_PT[int(m)]}/{y}"

def parse_money_to_float(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)

    s = str(x).strip()
    if s == "":
        return 0.0

    s = s.replace("R$", "").replace(" ", "")

    if "," in s and "." in s:  # 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:             # 1234,56
        s = s.replace(",", ".")

    try:
        return float(s)
    except Exception:
        return 0.0

def brl(x: Optional[float]) -> str:
    if x is None:
        return "—"
    s = f"{x:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"

def pct(x: float) -> str:
    return f"{x*100:.0f}%"

def parse_date_any(s):
    if s is None:
        return pd.NaT
    if isinstance(s, (pd.Timestamp,)):
        return s
    t = str(s).strip()
    if t == "":
        return pd.NaT

    # 2026-01-23
    if len(t) >= 10 and t[4:5] == "-" and t[7:8] == "-":
        return pd.to_datetime(t[:10], format="%Y-%m-%d", errors="coerce")

    return pd.to_datetime(t, dayfirst=True, errors="coerce")

def end_of_month(d: date) -> date:
    nxt = d.replace(day=28) + timedelta(days=4)
    return nxt.replace(day=1) - timedelta(days=1)

def business_days_remaining(as_of: date) -> int:
    eom = end_of_month(as_of)
    start = as_of + timedelta(days=1)
    if start > eom:
        return 0
    days = pd.date_range(start=start, end=eom, freq="B")
    return int(len(days))

def weeks_remaining(as_of: date) -> int:
    bdays = business_days_remaining(as_of)
    return int((bdays + 4) // 5)


# ================== LOADERS ==================
def load_vendas_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Não achei o CSV de vendas atendidas: {path}")

    df = pd.read_csv(path, encoding="utf-8-sig", sep=";")

    df.columns = (
        pd.Index(df.columns)
        .astype(str)
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
        .str.lower()
    )

    obrig = {"data", "total", "situacao"}
    faltando = obrig - set(df.columns)
    if faltando:
        raise RuntimeError(
            f"CSV de vendas atendidas não tem colunas esperadas. "
            f"Faltando: {faltando}. Achadas: {df.columns.tolist()}"
        )

    # ✅ qtd_itens é a coluna correta para "peças"
    if "qtd_itens" in df.columns:
        df["qtd_itens"] = pd.to_numeric(df["qtd_itens"], errors="coerce").fillna(0).astype(int)

    return df

def load_metas_csv(path: Path, ano_ref: int) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Não achei o arquivo de metas: {path}")

    enc_used = None
    first_line = ""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, "r", encoding=enc, errors="strict") as f:
                first_line = f.readline()
            enc_used = enc
            break
        except UnicodeDecodeError:
            continue

    if enc_used is None:
        enc_used = "latin-1"
        with open(path, "r", encoding=enc_used, errors="replace") as f:
            first_line = f.readline()

    sep = ";" if first_line.count(";") >= 2 else ","
    df = pd.read_csv(path, encoding=enc_used, sep=sep)

    if df.shape[1] == 1:
        col0 = str(df.columns[0])
        if (";" in col0) or ("," in col0):
            sep2 = ";" if col0.count(";") >= 2 else ","
            raw = pd.read_csv(path, encoding=enc_used, header=None, dtype=str)
            parts = raw[0].str.split(sep2, expand=True)
            header = parts.iloc[0].tolist()
            data = parts.iloc[1:].copy()
            data.columns = header
            df = data.reset_index(drop=True)

    df.columns = (
        pd.Index(df.columns)
        .astype(str)
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
        .str.lower()
    )

    obrig = {"ano_mes", "canal", "meta"}
    faltando = obrig - set(df.columns)
    if faltando:
        raise RuntimeError(
            f"metas CSV com colunas incorretas. Faltando: {faltando}. "
            f"Achadas: {df.columns.tolist()} | sep={repr(sep)} | encoding={enc_used} | "
            f"Primeira linha: {first_line.strip()}"
        )

    df["ano_mes"] = df["ano_mes"].astype(str).str.strip().str.replace("/", "-", regex=False)
    df["canal"] = df["canal"].astype(str).str.strip()
    df["meta"] = pd.to_numeric(df["meta"], errors="coerce").fillna(0.0)

    ano_ini = f"{ano_ref}-01"
    ano_fim = f"{ano_ref}-12"
    df = df[(df["ano_mes"] >= ano_ini) & (df["ano_mes"] <= ano_fim)].copy()
    return df


# ================== REGRAS / MAPAS ==================
CANAL_MAP = {
    "VAREJO SHOW ROOM": ["Atendido"],
    "VAREJO ANACA": ["Atendido-Anaca"],
    "ATACADO": ["Atendido-Atacado"],
    "INSTAGRAM/SITE": ["Atendido-Londrina", "Atendido-Site", "Atendido-Instagram"],
}

HEADER_BG = colors.HexColor("#2f3e4e")
COL_HEADER_BG = colors.HexColor("#3d4f63")
TOTAL_BG = colors.HexColor("#2a3440")
PERCENT_OK_BG = colors.HexColor("#7bd65a")


# ================== PEÇAS VENDIDAS (por mês + por canal) ==================
def compute_pecas_by_mes_canal(df_vendas: pd.DataFrame, ano_ref: int) -> pd.DataFrame:
    """
    Retorna DF: ano_mes, canal, pecas
    Canal = chaves do CANAL_MAP
    """
    if "qtd_itens" not in df_vendas.columns:
        return pd.DataFrame({"ano_mes": [], "canal": [], "pecas": []})

    df = df_vendas.copy()
    df["data_dt"] = df["data"].apply(parse_date_any)
    df = df.dropna(subset=["data_dt"])
    df["ano_mes"] = df["data_dt"].dt.to_period("M").astype(str)

    ano_ini = f"{ano_ref}-01"
    ano_fim = f"{ano_ref}-12"
    df = df[(df["ano_mes"] >= ano_ini) & (df["ano_mes"] <= ano_fim)].copy()

    df["qtd_itens"] = pd.to_numeric(df["qtd_itens"], errors="coerce").fillna(0).astype(int)

    rows: List[dict] = []
    for canal, situacoes in CANAL_MAP.items():
        sub = df[df["situacao"].isin(situacoes)].copy()
        if sub.empty:
            continue

        g = sub.groupby("ano_mes", as_index=False)["qtd_itens"].sum()
        for _, r in g.iterrows():
            rows.append({
                "ano_mes": str(r["ano_mes"]),
                "canal": str(canal),
                "pecas": int(r["qtd_itens"]),
            })

    if not rows:
        return pd.DataFrame({"ano_mes": [], "canal": [], "pecas": []})

    return pd.DataFrame(rows)


# ================== PDF / TABELAS ==================
@dataclass
class MonthTable:
    title: str
    rows: List[List[str]]

def build_month_table(
    df_vendas: pd.DataFrame,
    df_metas: pd.DataFrame,
    pecas_mes_df: pd.DataFrame,
    ano_mes: str,
    as_of: datetime,
    ano_ref: int
) -> MonthTable:
    df = df_vendas.copy()
    df["data_dt"] = df["data"].apply(parse_date_any)
    df = df.dropna(subset=["data_dt"])
    df["ano_mes"] = df["data_dt"].dt.to_period("M").astype(str)

    ano_ini = f"{ano_ref}-01"
    ano_fim = f"{ano_ref}-12"
    df = df[(df["ano_mes"] >= ano_ini) & (df["ano_mes"] <= ano_fim)].copy()

    df_mes = df[df["ano_mes"] == ano_mes].copy()
    metas_mes = df_metas[df_metas["ano_mes"] == ano_mes].set_index("canal")["meta"].to_dict()
    df_mes["total_num"] = df_mes["total"].apply(parse_money_to_float)

    is_current_year = (as_of.year == ano_ref)
    mes_vigente = as_of.strftime("%Y-%m")
    is_current_month = is_current_year and (ano_mes == mes_vigente)

    total_meta = 0.0
    total_atual = 0.0
    total_pecas = 0
    rows: List[List[str]] = []

    dias_uteis = business_days_remaining(as_of.date()) if is_current_month else 0
    semanas = weeks_remaining(as_of.date()) if is_current_month else 0

    # ✅ NOVA REGRA:
    # Se for mês vigente e "não há dias/semanas restantes" (0),
    # mostrar o total que falta (faltam) ao invés de "—".
    def calc_pace(faltam_val: float, unidades: int) -> Optional[float]:
        if not is_current_month:
            return None
        if faltam_val <= 0:
            return 0.0
        if unidades > 0:
            return faltam_val / unidades
        return faltam_val  # unidades == 0 → mostra total que falta

    for canal, situacoes in CANAL_MAP.items():
        meta = float(metas_mes.get(canal, 0.0))
        atual = float(df_mes[df_mes["situacao"].isin(situacoes)]["total_num"].sum())
        faltam = max(meta - atual, 0.0)
        perc = (atual / meta) if meta > 0 else 0.0

        por_dia = calc_pace(faltam, dias_uteis)
        por_semana = calc_pace(faltam, semanas)

        # ✅ peças por canal no mês
        pecas_val = None
        try:
            if not pecas_mes_df.empty:
                m = pecas_mes_df[(pecas_mes_df["ano_mes"] == ano_mes) & (pecas_mes_df["canal"] == canal)]
                if len(m) > 0:
                    pecas_val = int(m["pecas"].iloc[0])
        except Exception:
            pecas_val = None

        pecas_label = "—" if pecas_val is None else str(pecas_val)
        if pecas_val is not None:
            total_pecas += int(pecas_val)

        rows.append([canal, brl(meta), pecas_label, brl(atual), brl(faltam), brl(por_dia), brl(por_semana), pct(perc)])

        total_meta += meta
        total_atual += atual

    total_faltam = max(total_meta - total_atual, 0.0)
    total_perc = (total_atual / total_meta) if total_meta > 0 else 0.0

    total_por_dia = calc_pace(total_faltam, dias_uteis)
    total_por_semana = calc_pace(total_faltam, semanas)

    total_pecas_label = "—" if (pecas_mes_df.empty) else str(total_pecas)

    rows.append(["TOTAL", brl(total_meta), total_pecas_label, brl(total_atual), brl(total_faltam), brl(total_por_dia), brl(total_por_semana), pct(total_perc)])

    nome_mes = label_mes_slash(ano_mes)
    if is_current_month:
        titulo = f"D'ELLA - METAS - {nome_mes} - PARCIAL ATÉ {as_of.strftime('%d/%m/%Y %H:%M')}"
    else:
        titulo = f"D'ELLA - METAS FECHADAS - {nome_mes}"

    return MonthTable(title=titulo, rows=rows)

def build_year_summary_by_loja(
    df_vendas: pd.DataFrame,
    df_metas: pd.DataFrame,
    pecas_mes_df: pd.DataFrame,
    as_of: datetime,
    ano_ref: int
) -> MonthTable:
    mes_vigente = as_of.strftime("%Y-%m")
    mes_final = mes_vigente if as_of.year == ano_ref else f"{ano_ref}-12"

    ano_ini = f"{ano_ref}-01"
    ano_fim = mes_final

    # Vendas
    df = df_vendas.copy()
    df["data_dt"] = df["data"].apply(parse_date_any)
    df = df.dropna(subset=["data_dt"])
    df["ano_mes"] = df["data_dt"].dt.to_period("M").astype(str)
    df = df[(df["ano_mes"] >= ano_ini) & (df["ano_mes"] <= ano_fim)].copy()
    df["total_num"] = df["total"].apply(parse_money_to_float)

    rows: List[List[str]] = []
    total_meta_ano = 0.0
    total_atual_ano = 0.0
    total_pecas_ano = 0

    for canal, situacoes in CANAL_MAP.items():
        meta = df_metas[
            (df_metas["canal"] == canal)
            & (df_metas["ano_mes"] >= ano_ini)
            & (df_metas["ano_mes"] <= ano_fim)
        ]["meta"].sum()

        atual = df[df["situacao"].isin(situacoes)]["total_num"].sum()

        faltam = max(float(meta) - float(atual), 0.0)
        perc = (float(atual) / float(meta)) if float(meta) > 0 else 0.0

        pecas_val = None
        try:
            if not pecas_mes_df.empty:
                mm = pecas_mes_df[
                    (pecas_mes_df["ano_mes"] >= ano_ini)
                    & (pecas_mes_df["ano_mes"] <= ano_fim)
                    & (pecas_mes_df["canal"] == canal)
                ]
                if len(mm) > 0:
                    pecas_val = int(mm["pecas"].sum())
        except Exception:
            pecas_val = None

        pecas_label = "—" if pecas_val is None else str(pecas_val)
        if pecas_val is not None:
            total_pecas_ano += int(pecas_val)

        rows.append([canal, brl(float(meta)), pecas_label, brl(float(atual)), brl(faltam), "—", "—", pct(perc)])

        total_meta_ano += float(meta)
        total_atual_ano += float(atual)

    total_faltam = max(total_meta_ano - total_atual_ano, 0.0)
    total_perc = (total_atual_ano / total_meta_ano) if total_meta_ano > 0 else 0.0
    total_pecas_label = "—" if (pecas_mes_df.empty) else str(total_pecas_ano)

    rows.append(["TOTAL", brl(total_meta_ano), total_pecas_label, brl(total_atual_ano), brl(total_faltam), "—", "—", pct(total_perc)])

    title = f"D'ELLA - RESUMO {ano_ref} POR LOJA"
    return MonthTable(title=title, rows=rows)

def render_pdf(tables: List[MonthTable], out_pdf: Path):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleBar",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.yellow,
        alignment=1,
        leading=14,
    )

    doc = SimpleDocTemplate(
        str(out_pdf),
        pagesize=landscape(A4),
        leftMargin=18,
        rightMargin=18,
        topMargin=18,
        bottomMargin=18,
    )

    # ✅ largura útil real
    usable_w = doc.width

    # ✅ larguras "base" e escala para caber certinho
    base_col_widths = [170, 110, 105, 110, 110, 95, 110, 70]
    scale = usable_w / sum(base_col_widths)

    col_widths = [w * scale for w in base_col_widths]
    # ✅ FECHA A CONTA (evita micro-desalinhamento por float/arredondamento)
    col_widths[-1] = usable_w - sum(col_widths[:-1])

    story: List[Any] = []
    for t in tables:
        story.append(Spacer(1, 8))

        # ✅ faixa do título com MESMA largura e alinhada à esquerda
        title_bar = Table([[Paragraph(t.title, title_style)]], colWidths=[usable_w], hAlign="LEFT")
        title_bar.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), HEADER_BG),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(title_bar)
        story.append(Spacer(1, 6))

        data = [[
            "LOJA", "FATURAMENTO\nMETA", "QTD PEÇAS\nVENDIDAS",
            "FATURAMENTO\nATUAL", "R$/FALTAM", "R$/DIA", "R$/SEMANA", "% META"
        ]] + t.rows

        table = Table(data, colWidths=col_widths, hAlign="LEFT")

        ts = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COL_HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.yellow),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
        ])

        last_row = len(data) - 1
        ts.add("BACKGROUND", (0, last_row), (-1, last_row), TOTAL_BG)
        ts.add("TEXTCOLOR", (0, last_row), (-1, last_row), colors.yellow)
        ts.add("FONTNAME", (0, last_row), (-1, last_row), "Helvetica-Bold")

        # % META está na última coluna (índice 7)
        for r in range(1, last_row):
            try:
                perc_val = float(str(data[r][7]).replace("%", ""))
            except Exception:
                perc_val = 0.0
            if perc_val >= 100:
                ts.add("BACKGROUND", (7, r), (7, r), PERCENT_OK_BG)
                ts.add("TEXTCOLOR", (7, r), (7, r), colors.black)
                ts.add("FONTNAME", (7, r), (7, r), "Helvetica-Bold")

        table.setStyle(ts)
        story.append(table)
        story.append(Spacer(1, 14))

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story)


# ================== PATHS (SEMPRE PASTA 2026) ==================
def build_paths(ano_ref: int):
    yy = str(ano_ref)[-2:]
    in_csv_vendas = PASTA_VENDAS / f"vendas_atendidas_{ano_ref}.csv"
    metas_csv = PASTA_AUX / f"metas_{yy}.csv"
    out_pdf = PASTA_METAS / f"Metas_Faturamento_{ano_ref}.pdf"
    return in_csv_vendas, metas_csv, out_pdf


def copiar_pdf_para_pasta_extra(pdf_origem: Path, pasta_destino: Path):
    """
    Copia o PDF gerado para a pasta extra (ex: G:\\Meu Drive\\Relatorios)
    Sem atrapalhar o fluxo se o drive não estiver disponível.
    """
    try:
        if not pdf_origem.exists():
            print(f"⚠️ Não encontrei o PDF para copiar: {pdf_origem}")
            return

        pasta_destino.mkdir(parents=True, exist_ok=True)
        destino = pasta_destino / pdf_origem.name

        shutil.copy2(str(pdf_origem), str(destino))
        print(f"✅ Cópia criada em: {destino}")
    except Exception as e:
        print(f"⚠️ Não consegui copiar para '{pasta_destino}'. Motivo: {e}")


def gerar_pdf_metas(ano_ref: int):
    in_csv_vendas, metas_csv_path, out_pdf = build_paths(ano_ref)

    print(f"📌 BASE  : {SCRIPT_DIR}")
    print(f"📌 VENDAS: {in_csv_vendas}")
    print(f"📌 METAS : {metas_csv_path}")
    print(f"📌 PDF   : {out_pdf}")

    df_vendas = load_vendas_csv(in_csv_vendas)
    df_metas = load_metas_csv(metas_csv_path, ano_ref)

    # ✅ peças por mês e por canal
    pecas_mes_df = compute_pecas_by_mes_canal(df_vendas, ano_ref)

    as_of = datetime.now() - timedelta(hours=3)  # UTC → BRT (UTC-3)

    # meses do ano_ref até o mês vigente (se ano_ref == ano atual), senão até dezembro
    mes_limite = as_of.strftime("%Y-%m") if as_of.year == ano_ref else f"{ano_ref}-12"

    meses = sorted(df_metas["ano_mes"].unique().tolist())
    meses = [m for m in meses if f"{ano_ref}-01" <= m <= mes_limite]

    if not meses:
        raise RuntimeError(f"Nenhum mês válido encontrado no {metas_csv_path.name} para {ano_ref}-01..{mes_limite}.")

    tables = [build_month_table(df_vendas, df_metas, pecas_mes_df, m, as_of, ano_ref) for m in meses]
    tables.append(build_year_summary_by_loja(df_vendas, df_metas, pecas_mes_df, as_of, ano_ref))

    render_pdf(tables, out_pdf)
    print(f"✅ PDF gerado: {out_pdf}")

    # ✅ Copia também para o Google Drive (G:)
    copiar_pdf_para_pasta_extra(out_pdf, PASTA_EXTRA_COPIA)


def parse_args():
    p = argparse.ArgumentParser(description="Gera PDF de metas por ano (ex: python metas.py 2026)")
    p.add_argument("ano", nargs="?", type=int, default=datetime.now().year,
                   help="Ano do relatório (ex: 2026). Se vazio, usa ano atual.")
    return p.parse_args()


def main():
    args = parse_args()
    ano_ref = args.ano

    if ano_ref < 2000 or ano_ref > 2100:
        raise ValueError("Ano inválido. Use algo como 2025, 2026...")

    gerar_pdf_metas(ano_ref)


if __name__ == "__main__":
    main()
