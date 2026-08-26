"""Relatorio mensal de vendas do site (PDF, botao no painel Vendas).

Uma linha por mes desde a ABERTURA DO SITE (maio/2026, pedido 2026-0001 em
22/05) ate o mes corrente. Meses antes disso nao existem em `pedidos_pedido`
(ver nota em apps/analytics/vendas.py) -- comecar antes so mostraria zero.

Reaproveita `apps.analytics.faturamento` (mesma fonte de verdade do painel:
PedidoSite/ItemPedidoSite, nunca evento de analytics) para nao divergir da
tela. `novos`+`recorrentes` sempre bate com `vendas` porque
`novos_x_recorrentes` particiona o MESMO queryset de pedidos pagos usado em
`resumo()` -- garantido por construcao, nao por coincidencia.
"""

from datetime import datetime, timedelta

from django.utils import timezone

INICIO_SITE = (2026, 5)  # ano, mes de abertura do site

MESES_PT = {
    1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
    7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez',
}


def _primeiro_dia(ano, mes):
    return timezone.make_aware(datetime(ano, mes, 1))


def _proximo_mes(ano, mes):
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def _meses_ate_hoje(ano_ini, mes_ini):
    agora = timezone.localtime(timezone.now())
    ano, mes = ano_ini, mes_ini
    while (ano, mes) <= (agora.year, agora.month):
        yield ano, mes
        ano, mes = _proximo_mes(ano, mes)


def dados_mensais():
    """Uma linha por mes com os numeros do painel Vendas para aquele mes.

    O mes corrente entra com dado PARCIAL (so ate agora) e marcado com
    `em_andamento=True` -- o PDF deixa isso explicito, nao esconde o mes nem
    finge que ele ja fechou.
    """
    from apps.analytics import faturamento as F

    agora = timezone.localtime(timezone.now())
    linhas = []
    for ano, mes in _meses_ate_hoje(*INICIO_SITE):
        inicio = _primeiro_dia(ano, mes)
        ano_prox, mes_prox = _proximo_mes(ano, mes)
        fim_mes = _primeiro_dia(ano_prox, mes_prox) - timedelta(seconds=1)
        em_andamento = (ano, mes) == (agora.year, agora.month)
        fim = min(fim_mes, agora) if em_andamento else fim_mes

        resumo = F.resumo(inicio, fim)
        clientes = F.novos_x_recorrentes(inicio, fim)

        linhas.append({
            'label': f'{MESES_PT[mes]}/{ano}',
            'em_andamento': em_andamento,
            'faturamento': resumo['receita'],
            'vendas': resumo['vendas'],
            'pecas': resumo['itens'],
            'ticket': resumo['ticket'],
            'novos': clientes['novos'],
            'recorrentes': clientes['recorrentes'],
        })
    return linhas


def _brl(valor):
    texto = f'{float(valor or 0):,.2f}'
    texto = texto.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'R$ {texto}'


def _gerar_grafico(linhas):
    """PNG (bytes) com barras de faturamento + linha de vendas, mes a mes.

    Via matplotlib (nao reportlab.graphics): o combo bar+linha com dois eixos
    Y precisaria de eixo secundario manual no reportlab; o matplotlib faz
    nativamente (`twinx`) e da um resultado mais legivel no celular (fontes
    maiores, menos elementos brutos na imagem).
    """
    from io import BytesIO

    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.ticker import FuncFormatter
    import matplotlib.pyplot as plt

    labels = [l['label'] for l in linhas]
    faturamento = [float(l['faturamento']) for l in linhas]
    vendas = [l['vendas'] for l in linhas]

    dourado = '#c9a96e'
    preto = '#1a1a1a'
    cinza = '#666666'
    grade = '#e5e0d5'

    largura = max(6.8, len(labels) * 0.85)
    fig, ax1 = plt.subplots(figsize=(largura, 3.4), dpi=200)
    x = range(len(labels))

    caixa_rotulo = dict(boxstyle='round,pad=0.18', facecolor='white', edgecolor='none', alpha=0.85)

    ax1.bar(x, faturamento, color=dourado, width=0.55, zorder=2, label='Faturamento')
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(labels, fontsize=9.5, color=preto)
    # Folga extra nas pontas: o rotulo da 1a barra desloca pra esquerda (ver
    # abaixo) e sem isso encosta nos numeros do eixo Y.
    ax1.set_xlim(-0.7, len(labels) - 1 + 0.7)
    ax1.tick_params(axis='y', labelsize=8.5, colors=cinza)
    ax1.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f'R$ {v:,.0f}'.replace(',', '.')))
    ax1.set_ylim(bottom=0, top=(maior_fat := (max(faturamento) if faturamento else 0)) * 1.22 or 1)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.spines['left'].set_color(cinza)
    ax1.spines['bottom'].set_color(cinza)
    ax1.grid(axis='y', color=grade, linewidth=0.7, zorder=0)
    ax1.set_axisbelow(True)

    # Rotulo de valor em cima de cada barra (R$ 0.000,00, igual a tabela) e
    # ao lado de cada ponto da linha -- facilita ler no celular sem precisar
    # medir a altura contra o eixo. Fundo branco semi-opaco atras dos dois
    # pra continuar legivel quando a linha passa por cima (ex.: Jun/2026).
    for i, v in enumerate(faturamento):
        if v > 0:
            ax1.text(i - 0.06, v + maior_fat * 0.03, _brl(v), ha='right', va='bottom',
                      fontsize=7.3, color=preto, bbox=caixa_rotulo, zorder=4)

    ax2 = ax1.twinx()
    ax2.plot(x, vendas, color=preto, marker='o', linewidth=2, markersize=5, zorder=3, label='Vendas (qtd)')
    maior_venda = max(vendas) if vendas else 0
    ax2.set_ylim(bottom=0, top=maior_venda * 1.28 or 1)
    for i, v in enumerate(vendas):
        ax2.annotate(str(v), (i, v), textcoords='offset points', xytext=(10, 8),
                     ha='left', fontsize=7.8, color=preto, fontweight='bold',
                     bbox=caixa_rotulo, zorder=5)
    ax2.tick_params(axis='y', labelsize=8.5, colors=cinza)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_color(cinza)

    ax1.set_ylabel('Faturamento', fontsize=9, color=preto)
    ax2.set_ylabel('Vendas (qtd)', fontsize=9, color=preto)

    # Legenda fora do grafico, embaixo, os dois itens lado a lado (nao
    # empilhados e nao por cima dos dados).
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc='upper center', bbox_to_anchor=(0.5, -0.14),
               ncol=2, fontsize=8.8, frameon=False)

    fig.tight_layout()
    buf = BytesIO()
    # bbox_inches='tight': a legenda agora fica ABAIXO dos eixos (fora da
    # area de plot), sem isso ela e cortada na exportacao.
    fig.savefig(buf, format='png', dpi=200, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


def gerar_pdf():
    """Monta o PDF completo (bytes) e devolve um BytesIO pronto pra resposta HTTP."""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (HRFlowable, Image, Paragraph, SimpleDocTemplate,
                                     Table, TableStyle)

    linhas = dados_mensais()

    dourado     = colors.HexColor('#c9a96e')
    preto       = colors.HexColor('#1a1a1a')
    cinza       = colors.HexColor('#666666')
    cinza_claro = colors.HexColor('#f5f5f3')
    destaque    = colors.HexColor('#7a6220')

    titulo_st = ParagraphStyle('T', fontName='Helvetica-Bold', fontSize=17,
                                textColor=preto, leading=22, spaceAfter=4, alignment=TA_CENTER)
    sub_st    = ParagraphStyle('S', fontName='Helvetica', fontSize=9.5,
                                textColor=cinza, leading=13, spaceAfter=10, alignment=TA_CENTER)
    secao_st  = ParagraphStyle('Se', fontName='Helvetica-Bold', fontSize=12,
                                textColor=preto, spaceBefore=16, spaceAfter=7)
    nota_st   = ParagraphStyle('N', fontName='Helvetica-Oblique', fontSize=8,
                                textColor=cinza, spaceBefore=5, leading=11)

    buf_pdf = BytesIO()
    doc = SimpleDocTemplate(
        buf_pdf, pagesize=A4,
        leftMargin=1.6 * cm, rightMargin=1.6 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
    )

    agora_local = timezone.localtime(timezone.now())
    periodo_label = f"{linhas[0]['label']} a {linhas[-1]['label']}" if linhas else '-'

    elementos = [
        Paragraph("Relatório Mensal de Vendas", titulo_st),
        Paragraph(
            f"Site D'ELLA &nbsp;&middot;&nbsp; {periodo_label} "
            f"&nbsp;&middot;&nbsp; gerado em {agora_local:%d/%m/%Y às %H:%M}",
            sub_st,
        ),
        HRFlowable(width='100%', thickness=0.8, color=dourado),
        Paragraph('Resumo por mês', secao_st),
    ]

    if not linhas:
        elementos.append(Paragraph('Sem dados no período.', sub_st))
        doc.build(elementos)
        buf_pdf.seek(0)
        return buf_pdf

    cabecalho = ['Mês', 'Faturamento', 'Vendas', 'Peças', 'Ticket médio', 'Novos', 'Recorr.']
    dados_tabela = [cabecalho]
    for l in linhas:
        dados_tabela.append([
            l['label'] + (' *' if l['em_andamento'] else ''),
            _brl(l['faturamento']),
            str(l['vendas']),
            str(l['pecas']),
            _brl(l['ticket']),
            str(l['novos']),
            str(l['recorrentes']),
        ])

    tabela = Table(
        dados_tabela,
        colWidths=[2.3 * cm, 3.0 * cm, 1.7 * cm, 1.7 * cm, 2.7 * cm, 1.7 * cm, 1.9 * cm],
        repeatRows=1,
    )
    estilo_tabela = [
        ('BACKGROUND', (0, 0), (-1, 0), preto),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8.3),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8.6),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, cinza_claro]),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#dddddd')),
        ('TOPPADDING', (0, 0), (-1, -1), 5.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]
    for i, l in enumerate(linhas, start=1):
        if l['em_andamento']:
            estilo_tabela.append(('TEXTCOLOR', (0, i), (-1, i), destaque))
            estilo_tabela.append(('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'))
    tabela.setStyle(TableStyle(estilo_tabela))
    elementos.append(tabela)

    if any(l['em_andamento'] for l in linhas):
        elementos.append(Paragraph(
            '* mês em andamento — dados parciais até o momento da geração deste PDF.',
            nota_st,
        ))

    elementos.append(Paragraph('Faturamento e vendas mês a mês', secao_st))
    buf_grafico = _gerar_grafico(linhas)
    largura_disponivel = doc.width
    from PIL import Image as PILImage
    with PILImage.open(buf_grafico) as im:
        proporcao = im.height / im.width
    buf_grafico.seek(0)
    elementos.append(Image(buf_grafico, width=largura_disponivel,
                            height=largura_disponivel * proporcao))

    doc.build(elementos)
    buf_pdf.seek(0)
    return buf_pdf
