"""
Gerador de PDFs da Liga Quarta Scaff.

Gera dois tipos de PDF:
1. Planilha física para anotar resultados (por quadra)
2. Ranking completo para enviar por e-mail
"""

import io
from typing import Optional
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


# Cores do tema
COR_PRIMARIA = colors.HexColor("#1a1a2e")
COR_ACENTO = colors.HexColor("#f5a623")
COR_CINZA_CLARO = colors.HexColor("#f0f0f0")
COR_CINZA = colors.HexColor("#cccccc")
COR_VERDE = colors.HexColor("#27ae60")
COR_VERMELHO = colors.HexColor("#e74c3c")
COR_AMARELO = colors.HexColor("#f39c12")


def _celula_jogo(dupla1: str, dupla2: str, cell_w: float) -> Table:
    """
    Cria célula de jogo com nomes grandes e caixas de placar visíveis.
    Layout:  [  Nome1 / Nome2  ] [ PLACAR ]
                      ×
             [  Nome3 / Nome4  ] [ PLACAR ]
    """
    SCORE_W = 1.8 * cm
    NAME_W = cell_w - SCORE_W - 0.3 * cm
    ROW_H = 1.4 * cm
    X_H = 0.55 * cm

    styles = getSampleStyleSheet()
    nome_s = ParagraphStyle(
        "pn", parent=styles["Normal"],
        fontSize=11, leading=15, fontName="Helvetica-Bold",
    )
    x_s = ParagraphStyle(
        "px", parent=styles["Normal"],
        fontSize=16, fontName="Helvetica-Bold", alignment=TA_CENTER,
    )

    def score_box():
        sb = Table([[""]], colWidths=[SCORE_W - 0.2 * cm], rowHeights=[ROW_H - 0.15 * cm])
        sb.setStyle(TableStyle([
            ("BOX", (0, 0), (0, 0), 1.5, colors.black),
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
            ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
        ]))
        return sb

    p1 = dupla1.split(" / ")
    p2 = dupla2.split(" / ")
    n1 = f"{p1[0]}<br/>{p1[1]}" if len(p1) > 1 else p1[0]
    n2 = f"{p2[0]}<br/>{p2[1]}" if len(p2) > 1 else p2[0]

    data = [
        [Paragraph(n1, nome_s), score_box()],
        [Paragraph("×", x_s), ""],
        [Paragraph(n2, nome_s), score_box()],
    ]

    t = Table(data, colWidths=[NAME_W, SCORE_W], rowHeights=[ROW_H, X_H, ROW_H])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("SPAN", (0, 1), (1, 1)),  # × centralizado nas duas colunas
        ("ALIGN", (0, 1), (1, 1), "CENTER"),
    ]))
    return t


def gerar_planilha_pdf(
    rodada_num: int,
    data_rodada: str,
    sorteio_tabela: list[dict],
    nomes: dict[int, str],
) -> bytes:
    """
    Gera PDF da planilha física para anotar resultados.
    Layout: landscape A4, células grandes com caixas de placar visíveis.
    """
    MARGEM = 1.0 * cm
    PAGE_W = landscape(A4)[0] - 2 * MARGEM   # largura útil
    PAGE_H = landscape(A4)[1] - 2 * MARGEM   # altura útil
    COL_JOGO = 1.5 * cm
    MIN_COL_Q = 6.0 * cm   # largura mínima para caber os nomes confortavelmente
    HEADER_H = 0.85 * cm

    # Quantas quadras cabem por página mantendo largura mínima
    max_q_pag = max(1, int((PAGE_W - COL_JOGO) / MIN_COL_Q))

    quadras = sorted({j["quadra"] for j in sorteio_tabela})
    rodadas_internas = sorted({j["rodada_interna"] for j in sorteio_tabela})
    lookup = {(j["rodada_interna"], j["quadra"]): j for j in sorteio_tabela}

    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle(
        "Titulo", parent=styles["Heading1"],
        fontSize=18, textColor=COR_PRIMARIA, alignment=TA_CENTER, spaceAfter=2,
    )
    subtitulo_style = ParagraphStyle(
        "Subtitulo", parent=styles["Normal"],
        fontSize=11, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=8,
    )
    jogo_style = ParagraphStyle(
        "Jogo", parent=styles["Normal"],
        fontSize=11, fontName="Helvetica-Bold", alignment=TA_CENTER,
    )
    qhdr_style = ParagraphStyle(
        "qhdr", parent=styles["Normal"],
        fontSize=12, fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=colors.white,
    )

    # Divide quadras em grupos que cabem numa página
    grupos = [quadras[i:i + max_q_pag] for i in range(0, len(quadras), max_q_pag)]
    n_paginas = len(grupos)

    def _build_tabela_grupo(grupo: list) -> Table:
        n_q = len(grupo)
        col_q = (PAGE_W - COL_JOGO) / n_q

        # Altura: desconta título (aprox 2.5cm) + hr + espaços
        espaco_titulo = 2.8 * cm
        altura_tabela = PAGE_H - espaco_titulo
        row_h = (altura_tabela - HEADER_H) / len(rodadas_internas)

        header = [Paragraph("", jogo_style)] + [
            Paragraph(f"Quadra {q:02d}", qhdr_style) for q in grupo
        ]
        table_data = [header]

        for ri in rodadas_internas:
            linha = [Paragraph(f"Jogo\n{ri}", jogo_style)]
            for q in grupo:
                jogo = lookup.get((ri, q))
                if jogo:
                    linha.append(_celula_jogo(jogo["dupla1"], jogo["dupla2"], col_q))
                else:
                    linha.append(Paragraph("—", jogo_style))
            table_data.append(linha)

        col_widths = [COL_JOGO] + [col_q] * n_q
        row_heights = [HEADER_H] + [row_h] * len(rodadas_internas)

        t = Table(table_data, colWidths=col_widths, rowHeights=row_heights)
        rs = [
            ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, 0), 2.5, COR_ACENTO),
            ("BACKGROUND", (0, 1), (0, -1), COR_CINZA_CLARO),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("VALIGN", (0, 1), (0, -1), "MIDDLE"),
            ("VALIGN", (1, 1), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("TOPPADDING", (1, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (1, 1), (-1, -1), 4),
            ("LEFTPADDING", (1, 1), (-1, -1), 4),
            ("RIGHTPADDING", (1, 1), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.8, colors.HexColor("#cccccc")),
            ("BOX", (0, 0), (-1, -1), 1.5, COR_PRIMARIA),
        ]
        for i in range(1, len(rodadas_internas) + 1):
            if i % 2 == 0:
                rs.append(("BACKGROUND", (1, i), (-1, i), colors.HexColor("#f7f7f7")))
        t.setStyle(TableStyle(rs))
        return t

    # Monta elementos com PageBreak entre grupos
    elements = []
    for idx, grupo in enumerate(grupos):
        if idx > 0:
            elements.append(PageBreak())

        sufixo = f"  ·  Folha {idx + 1}/{n_paginas}" if n_paginas > 1 else ""
        quadras_str = f"Quadras {grupo[0]:02d}–{grupo[-1]:02d}" if len(grupo) > 1 else f"Quadra {grupo[0]:02d}"

        elements.append(Paragraph("Liga Quarta Scaff", titulo_style))
        elements.append(Paragraph(
            f"Rodada {rodada_num}  ·  {data_rodada}  ·  {quadras_str}{sufixo}",
            subtitulo_style,
        ))
        elements.append(HRFlowable(width="100%", thickness=2, color=COR_ACENTO, spaceAfter=8))
        elements.append(_build_tabela_grupo(grupo))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        topMargin=MARGEM,
        bottomMargin=MARGEM,
        leftMargin=MARGEM,
        rightMargin=MARGEM,
    )
    doc.build(elements)
    return buf.getvalue()


def _ranking_table_portrait(
    ranking_entries: list[dict],
    rodadas_numeros: list[int],
    com_desconto: bool,
) -> Table:
    """
    Monta tabela de ranking em modo retrato A4.
    Colunas responsivas: nome proporcional ao texto mais longo,
    colunas de rodada compactas, tabela centralizada.
    com_desconto=True: rodadas descartadas em cinza itálico.
    com_desconto=False: todos os pontos, total = soma de tudo.
    """
    styles = getSampleStyleSheet()
    fs = 8  # font size base
    cc = ParagraphStyle("cc2", parent=styles["Normal"], fontSize=fs, alignment=TA_CENTER)
    cl = ParagraphStyle("cl2", parent=styles["Normal"], fontSize=fs, alignment=TA_LEFT)
    cg = ParagraphStyle("cg2", parent=styles["Normal"], fontSize=fs, alignment=TA_CENTER,
                        textColor=colors.grey)

    header = ["Pos", "Nome"] + [f"R{n}" for n in rodadas_numeros] + ["Total"]
    table_data = [header]

    for entry in ranking_entries:
        total_exibir = (
            entry["total"] if com_desconto
            else sum(entry["pontos_por_rodada"].values())
        )
        linha = [str(entry["posicao"]), Paragraph(entry["nome"], cl)]
        for rn in rodadas_numeros:
            pts = entry["pontos_por_rodada"].get(rn)
            if pts is None:
                linha.append(Paragraph("—", cg))
            elif com_desconto and rn in entry["rodadas_descartadas"]:
                linha.append(Paragraph(f"<i>({pts})</i>", cg))
            else:
                linha.append(Paragraph(str(pts), cc))
        linha.append(Paragraph(f"<b>{total_exibir}</b>", cc))
        table_data.append(linha)

    # Largura útil em retrato A4 (21cm - 2cm margens)
    page_w = A4[0] - 2 * cm
    n_r = len(rodadas_numeros)

    col_pos = 0.7 * cm
    col_total = 1.8 * cm
    # Coluna de rodada: cabe um número de 2 dígitos — mín 1.3cm, máx 2.2cm
    col_r = 1.6 * cm

    # Nome: ocupa o espaço restante, com limites razoáveis
    col_nome = page_w - col_pos - col_total - col_r * n_r
    col_nome = max(col_nome, 2.8 * cm)
    col_nome = min(col_nome, 6 * cm)

    col_widths = [col_pos, col_nome] + [col_r] * n_r + [col_total]

    tabela = Table(table_data, colWidths=col_widths, repeatRows=1, hAlign="CENTER")
    n_rows = len(table_data)
    row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), fs),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("LEFTPADDING", (1, 0), (1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (0, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWHEIGHT", (0, 0), (-1, -1), 0.56 * cm),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, COR_ACENTO),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
    ]
    for i in range(1, n_rows):
        if i % 2 == 0:
            row_styles.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f5f5f5")))
    tabela.setStyle(TableStyle(row_styles))
    return tabela


# ── PDF 1: Detalhe da Rodada ──────────────────────────────────────────────────

def gerar_email_rodada_pdf(
    detalhes: list[dict],
    temporada_nome: str,
    rodada_num: int,
    rodada_data: str,
) -> bytes:
    """
    PDF 1 — Detalhe da rodada por jogador.
    Colunas: Pos | Nome | J1 | J2 | J3 | J4 | Pts Rodada | Cerveja?
    detalhes: saída de scoring.calcular_detalhe_por_jogo()
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1 * cm, rightMargin=1 * cm,
    )
    styles = getSampleStyleSheet()
    ts = ParagraphStyle("T1", parent=styles["Heading1"],
                        fontSize=16, textColor=COR_PRIMARIA, alignment=TA_CENTER, spaceAfter=2)
    ss = ParagraphStyle("S1", parent=styles["Normal"],
                        fontSize=9, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=6)
    cc = ParagraphStyle("cc1", parent=styles["Normal"], fontSize=8, alignment=TA_CENTER)
    cl = ParagraphStyle("cl1", parent=styles["Normal"], fontSize=8, alignment=TA_LEFT)

    header = ["Pos", "Nome", "J1", "J2", "J3", "J4", "Pts Rodada", "Cerveja?"]
    table_data = [header]

    for i, d in enumerate(detalhes):
        def fmt_j(v):
            return Paragraph("—", cc) if v is None else Paragraph(str(v), cc)
        cerveja = Paragraph("<b>Sim</b>", ParagraphStyle(
            "beer1", parent=styles["Normal"], fontSize=8,
            alignment=TA_CENTER, textColor=COR_AMARELO,
        )) if d["tem_beer"] else Paragraph("—", cc)
        table_data.append([
            str(i + 1),
            Paragraph(d["nome"], cl),
            fmt_j(d["j1"]), fmt_j(d["j2"]), fmt_j(d["j3"]), fmt_j(d["j4"]),
            Paragraph(f"<b>{d['total']}</b>", cc),
            cerveja,
        ])

    # Larguras — cabe em retrato A4 (19cm útil)
    page_w = A4[0] - 2 * cm
    col_nome = min(5 * cm, page_w * 0.3)
    col_j = 1.6 * cm
    col_pts = 2.2 * cm
    col_cerv = 2 * cm
    col_pos = page_w - col_nome - 4 * col_j - col_pts - col_cerv
    col_widths = [col_pos, col_nome, col_j, col_j, col_j, col_j, col_pts, col_cerv]

    tabela = Table(table_data, colWidths=col_widths, repeatRows=1)
    n_rows = len(table_data)
    row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("LEFTPADDING", (1, 1), (1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWHEIGHT", (0, 0), (-1, -1), 0.6 * cm),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, COR_ACENTO),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
    ]
    for i in range(1, n_rows):
        if i % 2 == 0:
            row_styles.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f5f5f5")))
    tabela.setStyle(TableStyle(row_styles))

    doc.build([
        Paragraph("Liga Quarta Scaff", ts),
        Paragraph(f"{temporada_nome}  ·  Rodada {rodada_num}  ·  {rodada_data}", ss),
        HRFlowable(width="100%", thickness=2, color=COR_ACENTO, spaceAfter=8),
        tabela,
        Spacer(1, 0.3 * cm),
        Paragraph("Cerveja = perdeu todos os 4 jogos ou levou 6×0.",
                  ParagraphStyle("obs1", parent=styles["Normal"], fontSize=7,
                                 textColor=colors.grey, alignment=TA_CENTER)),
    ])
    return buf.getvalue()


# ── PDF 2: Ranking com Desconto ───────────────────────────────────────────────

def gerar_ranking_pdf(
    ranking: list[dict],
    temporada_nome: str,
    rodada_atual: int,
    n_rodadas_total: int,
    rodadas_numeros: list[int],
) -> bytes:
    """
    PDF 2 — Ranking acumulado com descontos das piores rodadas.
    Retrato A4, colunas compactas e responsivas. Rodadas descartadas em cinza/itálico.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1 * cm, rightMargin=1 * cm,
    )
    styles = getSampleStyleSheet()
    ts = ParagraphStyle("T2", parent=styles["Heading1"],
                        fontSize=16, textColor=COR_PRIMARIA, alignment=TA_CENTER, spaceAfter=2)
    ss = ParagraphStyle("S2", parent=styles["Normal"],
                        fontSize=9, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=6)

    tabela = _ranking_table_portrait(ranking, rodadas_numeros, com_desconto=True)

    doc.build([
        Paragraph("Liga Quarta Scaff", ts),
        Paragraph(
            f"{temporada_nome}  ·  Ranking c/ Descarte  ·  "
            f"Rodada {rodada_atual}/{n_rodadas_total}  ·  "
            f"(cinza = rodadas descartadas)", ss),
        HRFlowable(width="100%", thickness=2, color=COR_ACENTO, spaceAfter=8),
        tabela,
    ])
    return buf.getvalue()


# ── PDF 3: Ranking Geral Sem Desconto ─────────────────────────────────────────

def gerar_ranking_sem_desconto_pdf(
    ranking: list[dict],
    temporada_nome: str,
    rodada_atual: int,
    n_rodadas_total: int,
    rodadas_numeros: list[int],
) -> bytes:
    """
    PDF 3 — Ranking acumulado sem descontar nenhuma rodada.
    Total = soma de todas as rodadas. Retrato A4.
    """
    # Recalcula ranking sem descartes e reordena
    ranking_sd = [dict(e) for e in ranking]
    ranking_sd.sort(key=lambda x: (-sum(x["pontos_por_rodada"].values()), x["nome"]))
    for i, e in enumerate(ranking_sd):
        e["posicao"] = i + 1

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1 * cm, rightMargin=1 * cm,
    )
    styles = getSampleStyleSheet()
    ts = ParagraphStyle("T3", parent=styles["Heading1"],
                        fontSize=16, textColor=COR_PRIMARIA, alignment=TA_CENTER, spaceAfter=2)
    ss = ParagraphStyle("S3", parent=styles["Normal"],
                        fontSize=9, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=6)

    tabela = _ranking_table_portrait(ranking_sd, rodadas_numeros, com_desconto=False)

    doc.build([
        Paragraph("Liga Quarta Scaff", ts),
        Paragraph(
            f"{temporada_nome}  ·  Ranking Geral (todas as rodadas)  ·  "
            f"Após Rodada {rodada_atual}/{n_rodadas_total}", ss),
        HRFlowable(width="100%", thickness=2, color=COR_ACENTO, spaceAfter=8),
        tabela,
    ])
    return buf.getvalue()
