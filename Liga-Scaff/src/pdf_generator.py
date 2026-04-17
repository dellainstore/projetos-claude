"""
Gerador de PDFs da Liga Quarta Scaff.

Gera dois tipos de PDF:
1. Planilha física para anotar resultados (por quadra)
2. Ranking completo para enviar por e-mail
"""

import io
import html as _html
from typing import Optional
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, PageBreak,
    KeepTogether,
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
    Cria célula de jogo com nomes e caixas de placar.
    Layout:
        [ Nome1              ] [ □ ]
        [        ×           ]
        [ Nome2              ] [ □ ]
    """
    SCORE_W = 1.35 * cm
    NAME_W = cell_w - SCORE_W - 0.25 * cm
    ROW_H = 1.15 * cm
    X_H = 0.32 * cm

    styles = getSampleStyleSheet()
    nome_s = ParagraphStyle(
        "pn", parent=styles["Normal"],
        fontSize=10, leading=13, fontName="Helvetica-Bold",
    )
    x_s = ParagraphStyle(
        "px", parent=styles["Normal"],
        fontSize=12, fontName="Helvetica-Bold", alignment=TA_CENTER,
    )

    def score_box():
        sb = Table([[""]], colWidths=[SCORE_W - 0.2 * cm], rowHeights=[ROW_H - 0.12 * cm])
        sb.setStyle(TableStyle([
            ("BOX", (0, 0), (0, 0), 1.0, colors.black),
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
            ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
        ]))
        return sb

    p1 = dupla1.split(" / ")
    p2 = dupla2.split(" / ")
    n1 = (f"{_html.escape(p1[0])}<br/>{_html.escape(p1[1])}" if len(p1) > 1
          else _html.escape(p1[0]))
    n2 = (f"{_html.escape(p2[0])}<br/>{_html.escape(p2[1])}" if len(p2) > 1
          else _html.escape(p2[0]))

    data = [
        [Paragraph(n1, nome_s), score_box()],
        [Paragraph("×", x_s), ""],      # × fica SÓ na coluna de nomes, centralizado
        [Paragraph(n2, nome_s), score_box()],
    ]

    t = Table(data, colWidths=[NAME_W, SCORE_W], rowHeights=[ROW_H, X_H, ROW_H])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # padding coluna de nomes
        ("LEFTPADDING",  (0, 0), (0, -1), 4),
        ("RIGHTPADDING", (0, 0), (0, -1), 8),  # espaço entre nome e caixa de placar
        ("TOPPADDING",   (0, 0), (0, -1), 1),
        ("BOTTOMPADDING",(0, 0), (0, -1), 1),
        # padding coluna de score
        ("LEFTPADDING",  (1, 0), (1, -1), 3),
        ("RIGHTPADDING", (1, 0), (1, -1), 2),
        ("TOPPADDING",   (1, 0), (1, -1), 1),
        ("BOTTOMPADDING",(1, 0), (1, -1), 1),
        # × centralizado apenas na coluna de nomes (sem SPAN)
        ("ALIGN",        (0, 1), (0, 1), "CENTER"),
        ("TOPPADDING",   (0, 1), (0, 1), 0),
        ("BOTTOMPADDING",(0, 1), (0, 1), 0),
        ("LEFTPADDING",  (0, 1), (0, 1), 0),
        ("RIGHTPADDING", (0, 1), (0, 1), 0),
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
    Layout: landscape A4. Todos os 4 jogos SEMPRE na mesma folha.
    Grupos com menos quadras mantêm o mesmo tamanho das colunas (centrado na página).
    """
    MARGEM = 0.8 * cm
    PAGE_W = landscape(A4)[0] - 2 * MARGEM   # largura útil
    PAGE_H = landscape(A4)[1] - 2 * MARGEM   # altura útil
    COL_JOGO = 1.3 * cm
    MIN_COL_Q = 5.0 * cm   # 5 quadras por página (mais espaço para os nomes)
    HEADER_H = 0.65 * cm
    ESPACO_TITULO = 3.0 * cm  # reserva generosa para título + subtítulo + HR

    # Quantas quadras cabem por página mantendo largura mínima
    max_q_pag = max(1, int((PAGE_W - COL_JOGO) / MIN_COL_Q))

    quadras = sorted({j["quadra"] for j in sorteio_tabela})
    rodadas_internas = sorted({j["rodada_interna"] for j in sorteio_tabela})
    lookup = {(j["rodada_interna"], j["quadra"]): j for j in sorteio_tabela}

    # ── Tamanho FIXO para colunas e linhas — igual em TODAS as páginas ─────────
    col_q_fixo = (PAGE_W - COL_JOGO) / max_q_pag          # largura de cada quadra
    row_h_fixo = (PAGE_H - ESPACO_TITULO - HEADER_H) / len(rodadas_internas)

    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle(
        "Titulo", parent=styles["Heading1"],
        fontSize=14, textColor=COR_PRIMARIA, alignment=TA_CENTER, spaceAfter=1,
    )
    subtitulo_style = ParagraphStyle(
        "Subtitulo", parent=styles["Normal"],
        fontSize=10, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=4,
    )
    jogo_style = ParagraphStyle(
        "Jogo", parent=styles["Normal"],
        fontSize=10, fontName="Helvetica-Bold", alignment=TA_CENTER,
    )
    qhdr_style = ParagraphStyle(
        "qhdr", parent=styles["Normal"],
        fontSize=11, fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=colors.white,
    )

    # Divide quadras em grupos que cabem numa página
    grupos = [quadras[i:i + max_q_pag] for i in range(0, len(quadras), max_q_pag)]
    n_paginas = len(grupos)

    def _build_tabela_grupo(grupo: list) -> Table:
        """Monta a tabela do grupo usando col_q_fixo e row_h_fixo — mesma escala em todas as páginas."""
        n_q = len(grupo)

        header = [Paragraph("", jogo_style)] + [
            Paragraph(f"Quadra {q:02d}", qhdr_style) for q in grupo
        ]
        table_data = [header]

        for ri in rodadas_internas:
            linha = [Paragraph(f"Jogo\n{ri}", jogo_style)]
            for q in grupo:
                jogo = lookup.get((ri, q))
                if jogo:
                    linha.append(_celula_jogo(jogo["dupla1"], jogo["dupla2"], col_q_fixo))
                else:
                    linha.append(Paragraph("—", jogo_style))
            table_data.append(linha)

        col_widths  = [COL_JOGO] + [col_q_fixo] * n_q
        row_heights = [HEADER_H] + [row_h_fixo] * len(rodadas_internas)

        # splitByRow=0 impede que os jogos sejam separados entre páginas
        t = Table(table_data, colWidths=col_widths, rowHeights=row_heights, splitByRow=0)
        t.hAlign = "CENTER"  # centraliza na folha quando o grupo tem menos colunas

        rs = [
            ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("ALIGN",      (0, 0), (-1, 0), "CENTER"),
            ("VALIGN",     (0, 0), (-1, 0), "MIDDLE"),
            ("LINEBELOW",  (0, 0), (-1, 0), 1.5, COR_ACENTO),
            ("BACKGROUND", (0, 1), (0, -1), COR_CINZA_CLARO),
            ("ALIGN",      (0, 1), (0, -1), "CENTER"),
            ("VALIGN",     (0, 1), (0, -1), "MIDDLE"),
            ("VALIGN",     (1, 1), (-1, -1), "MIDDLE"),
            ("ALIGN",      (1, 1), (-1, -1), "CENTER"),
            ("TOPPADDING",    (1, 1), (-1, -1), 2),
            ("BOTTOMPADDING", (1, 1), (-1, -1), 2),
            ("LEFTPADDING",   (1, 1), (-1, -1), 2),
            ("RIGHTPADDING",  (1, 1), (-1, -1), 2),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("BOX",  (0, 0), (-1, -1), 1.2, COR_PRIMARIA),
            # Separador grosso da coluna "Jogo"
            ("LINEAFTER", (0, 0), (0, -1), 1.8, COR_PRIMARIA),
        ]
        # Linhas separando cada jogo (horizontal) — mais grossas que a grade
        for i in range(1, len(rodadas_internas)):
            rs.append(("LINEBELOW", (0, i), (-1, i), 1.5, colors.HexColor("#666666")))
        # Linhas separando cada quadra (vertical)
        for i in range(1, n_q):
            rs.append(("LINEAFTER", (i, 0), (i, -1), 1.5, colors.HexColor("#666666")))
        for i in range(1, len(rodadas_internas) + 1):
            if i % 2 == 0:
                rs.append(("BACKGROUND", (1, i), (-1, i), colors.HexColor("#f7f7f7")))
        t.setStyle(TableStyle(rs))
        return t

    # Monta elementos: cada grupo fica dentro de KeepTogether para nunca dividir
    elements = []
    for idx, grupo in enumerate(grupos):
        sufixo = f"  ·  Folha {idx + 1}/{n_paginas}" if n_paginas > 1 else ""
        quadras_str = (f"Quadras {grupo[0]:02d}–{grupo[-1]:02d}"
                       if len(grupo) > 1 else f"Quadra {grupo[0]:02d}")

        # KeepTogether garante que título + tabela ficam juntos na mesma página
        bloco = KeepTogether([
            Paragraph("Liga Quarta Scaff", titulo_style),
            Paragraph(
                f"Rodada {rodada_num}  ·  {data_rodada}  ·  {quadras_str}{sufixo}",
                subtitulo_style,
            ),
            HRFlowable(width="100%", thickness=2, color=COR_ACENTO, spaceAfter=4),
            _build_tabela_grupo(grupo),
        ])
        elements.append(bloco)

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


COR_DESCARTE_BG = colors.HexColor("#ffe0e0")   # fundo vermelho claro para descarte
COR_DESCARTE_TX = colors.HexColor("#cc0000")   # texto vermelho escuro para descarte


_MARGEM_EMAIL = 0.4 * cm   # margem mínima nos 3 PDFs de e-mail
_HEADER_H_EMAIL = 2.0 * cm  # estimativa de espaço para título + subtítulo + HR


def _ranking_table_portrait(
    ranking_entries: list[dict],
    rodadas_numeros: list[int],
    com_desconto: bool,
    page_h_usavel: float | None = None,
) -> Table:
    """
    Monta tabela de ranking em modo retrato A4.
    page_h_usavel: altura útil da página em pontos ReportLab (A4[1] - 2*margens).
    Quando fornecido, calcula font size e row_h dinamicamente para preencher a página.
    """
    # ── Cálculo dinâmico de fonte e altura de linha ───────────────────────────
    n_data = len(ranking_entries)
    n_total_rows = n_data + 1  # +1 para cabeçalho da tabela

    if page_h_usavel is not None:
        disponivel = page_h_usavel - _HEADER_H_EMAIL
        row_h_ideal = disponivel / n_total_rows
        row_h = max(0.45 * cm, min(row_h_ideal, 1.50 * cm))
        # font proporcional: 1.64 pt por mm de altura de linha
        row_h_mm = row_h / cm * 10
        fs = max(8, min(14, round(row_h_mm * 1.64)))
    else:
        fs = 8
        row_h = 0.50 * cm

    # ── Estilos de parágrafo ──────────────────────────────────────────────────
    styles = getSampleStyleSheet()
    cc = ParagraphStyle("cc2", parent=styles["Normal"], fontSize=fs, alignment=TA_CENTER)
    cl = ParagraphStyle("cl2", parent=styles["Normal"], fontSize=fs, alignment=TA_LEFT)
    cg = ParagraphStyle("cg2", parent=styles["Normal"], fontSize=fs, alignment=TA_CENTER,
                        textColor=colors.grey)
    cd = ParagraphStyle("cd2", parent=styles["Normal"], fontSize=fs, alignment=TA_CENTER,
                        textColor=COR_DESCARTE_TX, fontName="Helvetica-Bold")

    header = ["Pos", "Nome", "Total"] + [f"R{n}" for n in rodadas_numeros]
    table_data = [header]

    # Rastreia posição das células descartadas para pintar o fundo depois
    descartadas_cells: list[tuple[int, int]] = []  # (row_idx, col_idx) base-1

    for row_idx, entry in enumerate(ranking_entries, start=1):
        total_exibir = (
            entry["total"] if com_desconto
            else sum(entry["pontos_por_rodada"].values())
        )
        # pos=0, nome=1, total=2 → rodadas começam na coluna 3
        linha = [
            str(entry["posicao"]),
            Paragraph(_html.escape(entry["nome"]), cl),
            Paragraph(f"<b>{total_exibir}</b>", cc),
        ]
        for col_offset, rn in enumerate(rodadas_numeros):
            pts = entry["pontos_por_rodada"].get(rn)
            if com_desconto and rn in entry["rodadas_descartadas"]:
                valor = pts if pts is not None else 0
                linha.append(Paragraph(f"({valor})", cd))
                col_idx = 3 + col_offset  # pos=0, nome=1, total=2, rodadas a partir de 3
                descartadas_cells.append((row_idx, col_idx))
            elif pts is None:
                linha.append(Paragraph("—", cg))
            else:
                linha.append(Paragraph(str(pts), cc))
        table_data.append(linha)

    # ── Larguras de coluna responsivas ───────────────────────────────────────
    page_w = A4[0] - 2 * _MARGEM_EMAIL
    n_r = len(rodadas_numeros)
    scale = min(1.5, fs / 8.0)

    col_pos   = min(0.6 * scale * cm, 1.0 * cm)
    col_total = min(1.5 * scale * cm, 2.5 * cm)
    available = page_w - col_pos - col_total

    # Nome ocupa 35% do espaço disponível (3.0–7.0 cm)
    col_nome = min(max(available * 0.35, 3.0 * cm), 7.0 * cm)
    col_r    = (available - col_nome) / max(n_r, 1)
    col_r    = max(col_r, 1.1 * cm)   # nunca mais estreito que 1.1 cm

    # Se col_r empurrar nome abaixo do mínimo, prioriza nome
    if available - col_r * n_r < 3.0 * cm:
        col_nome = 3.0 * cm
        col_r = (available - col_nome) / max(n_r, 1)

    col_widths = [col_pos, col_nome, col_total] + [col_r] * n_r
    pad = max(2, min(5, round(fs * 0.35)))

    tabela = Table(table_data, colWidths=col_widths, repeatRows=1, hAlign="CENTER")
    n_rows = len(table_data)
    # pad_v: distribui metade do espaço vertical sobrando para centralizar o conteúdo
    fs_leading = fs * 1.2          # estimativa da altura de uma linha de texto
    pad_v = max(2, int((row_h - fs_leading) / 2))
    row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), fs),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("LEFTPADDING", (1, 0), (1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad - 1),
        ("LEFTPADDING", (0, 0), (0, -1), pad - 1),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), pad_v),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad_v),
        ("ROWHEIGHT", (0, 0), (-1, -1), row_h),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, COR_ACENTO),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
    ]
    for i in range(1, n_rows):
        if i % 2 == 0:
            row_styles.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f5f5f5")))
    for (ri, ci) in descartadas_cells:
        row_styles.append(("BACKGROUND", (ci, ri), (ci, ri), COR_DESCARTE_BG))
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
    # ── Cálculo dinâmico: preenche a página com a maior fonte possível ────────
    FOOTNOTE_H = 0.7 * cm   # espaço para rodapé ("Cerveja = ...")
    page_h_usavel = A4[1] - 2 * _MARGEM_EMAIL
    disponivel = page_h_usavel - _HEADER_H_EMAIL - FOOTNOTE_H
    n_data = len(detalhes)
    n_total_rows = n_data + 1  # +1 cabeçalho

    row_h_ideal = disponivel / n_total_rows
    row_h = max(0.45 * cm, min(row_h_ideal, 1.50 * cm))
    row_h_mm = row_h / cm * 10
    fs = max(8, min(14, round(row_h_mm * 1.64)))
    scale = min(1.5, fs / 8.0)
    pad = max(2, min(5, round(fs * 0.35)))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=_MARGEM_EMAIL, bottomMargin=_MARGEM_EMAIL,
        leftMargin=_MARGEM_EMAIL, rightMargin=_MARGEM_EMAIL,
    )
    styles = getSampleStyleSheet()
    ts_fs = max(14, min(20, round(fs * 1.4)))
    ss_fs = max(8,  min(12, round(fs * 0.8)))
    ts = ParagraphStyle("T1", parent=styles["Heading1"],
                        fontSize=ts_fs, textColor=COR_PRIMARIA, alignment=TA_CENTER, spaceAfter=1)
    ss = ParagraphStyle("S1", parent=styles["Normal"],
                        fontSize=ss_fs, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=4)
    cc = ParagraphStyle("cc1", parent=styles["Normal"], fontSize=fs, alignment=TA_CENTER)
    cl = ParagraphStyle("cl1", parent=styles["Normal"], fontSize=fs, alignment=TA_LEFT)

    header = ["Pos", "Nome", "Pts Rodada", "J1", "J2", "J3", "J4", "Cerveja?"]
    table_data = [header]

    for i, d in enumerate(detalhes):
        def fmt_j(v):
            return Paragraph("—", cc) if v is None else Paragraph(str(v), cc)
        cerveja = Paragraph("<b>Sim</b>", ParagraphStyle(
            "beer1", parent=styles["Normal"], fontSize=fs,
            alignment=TA_CENTER, textColor=COR_AMARELO,
        )) if d["tem_beer"] else Paragraph("—", cc)
        table_data.append([
            str(i + 1),
            Paragraph(_html.escape(d["nome"]), cl),
            Paragraph(f"<b>{d['total']}</b>", cc),
            fmt_j(d["j1"]), fmt_j(d["j2"]), fmt_j(d["j3"]), fmt_j(d["j4"]),
            cerveja,
        ])

    # Larguras responsivas — preenchem a largura útil
    page_w = A4[0] - 2 * _MARGEM_EMAIL
    col_j    = min(1.3 * scale * cm, 2.0 * cm)
    col_pts  = min(2.0 * scale * cm, 3.0 * cm)
    col_cerv = min(1.6 * scale * cm, 2.5 * cm)
    col_pos  = min(0.7 * scale * cm, 1.1 * cm)
    col_nome = page_w - col_pos - col_pts - 4 * col_j - col_cerv
    col_nome = max(col_nome, 3.0 * cm)
    col_widths = [col_pos, col_nome, col_pts, col_j, col_j, col_j, col_j, col_cerv]

    tabela = Table(table_data, colWidths=col_widths, repeatRows=1)
    n_rows = len(table_data)
    fs_leading = fs * 1.2
    pad_v = max(2, int((row_h - fs_leading) / 2))
    row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), fs),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("LEFTPADDING", (1, 0), (1, -1), pad),
        ("LEFTPADDING", (0, 0), (0, -1), pad - 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad - 1),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), pad_v),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad_v),
        ("ROWHEIGHT", (0, 0), (-1, -1), row_h),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, COR_ACENTO),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
    ]
    for i in range(1, n_rows):
        if i % 2 == 0:
            row_styles.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f5f5f5")))
    tabela.setStyle(TableStyle(row_styles))

    obs_fs = max(7, fs - 2)
    doc.build([
        Paragraph("Liga Quarta Scaff", ts),
        Paragraph(f"{temporada_nome}  ·  Rodada {rodada_num}  ·  {rodada_data}", ss),
        HRFlowable(width="100%", thickness=2, color=COR_ACENTO, spaceAfter=4),
        tabela,
        Spacer(1, 0.2 * cm),
        Paragraph("Cerveja = perdeu todos os 4 jogos ou levou 6×0.",
                  ParagraphStyle("obs1", parent=styles["Normal"], fontSize=obs_fs,
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
    page_h_usavel = A4[1] - 2 * _MARGEM_EMAIL
    tabela = _ranking_table_portrait(ranking, rodadas_numeros, com_desconto=True,
                                     page_h_usavel=page_h_usavel)
    # Font usado pela tabela (recalcula apenas para o título)
    _n = len(ranking) + 1
    _rh = max(0.45 * cm, min((page_h_usavel - _HEADER_H_EMAIL) / _n, 1.50 * cm))
    _fs = max(8, min(14, round(_rh / cm * 10 * 1.64)))
    ts_fs = max(14, min(20, round(_fs * 1.4)))
    ss_fs = max(8,  min(12, round(_fs * 0.8)))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=_MARGEM_EMAIL, bottomMargin=_MARGEM_EMAIL,
        leftMargin=_MARGEM_EMAIL, rightMargin=_MARGEM_EMAIL,
    )
    styles = getSampleStyleSheet()
    ts = ParagraphStyle("T2", parent=styles["Heading1"],
                        fontSize=ts_fs, textColor=COR_PRIMARIA, alignment=TA_CENTER, spaceAfter=1)
    ss = ParagraphStyle("S2", parent=styles["Normal"],
                        fontSize=ss_fs, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=4)

    doc.build([
        Paragraph("Liga Quarta Scaff", ts),
        Paragraph(
            f"{temporada_nome}  ·  Ranking c/ Descarte  ·  "
            f"Rodada {rodada_atual}/{n_rodadas_total}  ·  "
            f"(células em vermelho = rodadas descartadas)", ss),
        HRFlowable(width="100%", thickness=2, color=COR_ACENTO, spaceAfter=4),
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

    page_h_usavel = A4[1] - 2 * _MARGEM_EMAIL
    tabela = _ranking_table_portrait(ranking_sd, rodadas_numeros, com_desconto=False,
                                     page_h_usavel=page_h_usavel)
    _n = len(ranking_sd) + 1
    _rh = max(0.45 * cm, min((page_h_usavel - _HEADER_H_EMAIL) / _n, 1.50 * cm))
    _fs = max(8, min(14, round(_rh / cm * 10 * 1.64)))
    ts_fs = max(14, min(20, round(_fs * 1.4)))
    ss_fs = max(8,  min(12, round(_fs * 0.8)))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=_MARGEM_EMAIL, bottomMargin=_MARGEM_EMAIL,
        leftMargin=_MARGEM_EMAIL, rightMargin=_MARGEM_EMAIL,
    )
    styles = getSampleStyleSheet()
    ts = ParagraphStyle("T3", parent=styles["Heading1"],
                        fontSize=ts_fs, textColor=COR_PRIMARIA, alignment=TA_CENTER, spaceAfter=1)
    ss = ParagraphStyle("S3", parent=styles["Normal"],
                        fontSize=ss_fs, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=4)

    doc.build([
        Paragraph("Liga Quarta Scaff", ts),
        Paragraph(
            f"{temporada_nome}  ·  Ranking Geral (todas as rodadas)  ·  "
            f"Após Rodada {rodada_atual}/{n_rodadas_total}", ss),
        HRFlowable(width="100%", thickness=2, color=COR_ACENTO, spaceAfter=4),
        tabela,
    ])
    return buf.getvalue()
