"""
Management command: gerar_relatorio_semanal
Roda toda segunda-feira as 07h via cron:
  0 7 * * 1 cd /var/www/della-sistemas/projetos-claude/della_sistemas && .venv/bin/python manage.py gerar_relatorio_semanal >> ~/logs/della-sistemas/relatorio_semanal.log 2>&1
"""

from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.utils import timezone


class Command(BaseCommand):
    help = 'Gera o relatorio semanal de analytics em PDF'

    def add_arguments(self, parser):
        parser.add_argument(
            '--semana',
            type=str,
            help='Data de inicio da semana no formato YYYY-MM-DD (padrao: semana anterior)',
        )
        parser.add_argument('--dry-run', action='store_true', help='Calcula mas nao salva')

    def handle(self, *args, **options):
        if not self._db_disponivel():
            self.stderr.write('Banco della_site nao configurado. Abortando.')
            return

        semana_inicio = self._calcular_semana(options.get('semana'))
        semana_fim    = semana_inicio + timedelta(days=6)

        self.stdout.write(f'Coletando dados: {semana_inicio} a {semana_fim}')

        try:
            stats = self._coletar_stats(semana_inicio, semana_fim)
        except Exception as e:
            self.stderr.write(f'Erro ao coletar stats: {e}')
            return

        if options.get('dry_run'):
            self.stdout.write(str(stats))
            return

        analise = self._obter_analise_ia(stats, semana_inicio, semana_fim)
        pdf_rel  = self._gerar_pdf(stats, analise, semana_inicio, semana_fim)

        from apps.analytics.models import RelatorioSemanal
        RelatorioSemanal.objects.update_or_create(
            semana_inicio=semana_inicio,
            defaults={'semana_fim': semana_fim, 'arquivo': pdf_rel},
        )
        self.stdout.write(self.style.SUCCESS(f'Relatorio salvo: {pdf_rel}'))

    def _db_disponivel(self):
        return 'della_site' in settings.DATABASES

    def _calcular_semana(self, semana_str):
        if semana_str:
            d = date.fromisoformat(semana_str)
            return d - timedelta(days=d.weekday())
        hoje = date.today()
        return hoje - timedelta(days=hoje.weekday() + 7)

    def _coletar_stats(self, semana_inicio, semana_fim):
        from apps.analytics.models import EventoSite, SessaoSite

        tz = timezone.get_current_timezone()
        inicio = timezone.make_aware(datetime.combine(semana_inicio, datetime.min.time()), tz)
        fim    = timezone.make_aware(
            datetime.combine(semana_fim, datetime.max.time().replace(microsecond=0)), tz
        )

        # Oculta dados anteriores ao corte (28/06/2026 — remoção de bots/scans).
        from apps.analytics.constants import inicio_corte_aware
        corte = inicio_corte_aware()
        if inicio < corte:
            inicio = corte
        periodo   = Q(ocorrido_em__range=(inicio, fim))
        sess_qs   = SessaoSite.objects.filter(iniciada_em__range=(inicio, fim))
        comprou   = EventoSite.objects.filter(
            sessao=OuterRef('pk'), tipo='pedido_finalizado', pedido_numero__gt=''
        )

        visitas    = EventoSite.objects.filter(periodo, tipo='pagina_vista').count()
        visitantes = sess_qs.count()

        pedidos = (
            EventoSite.objects
            .filter(periodo, tipo='pedido_finalizado', pedido_numero__gt='')
            .values('pedido_numero').distinct().count()
        )
        receita = (
            EventoSite.objects
            .filter(periodo, tipo='pedido_finalizado', pedido_numero__gt='')
            .aggregate(t=Sum('valor_total'))['t'] or 0
        )
        itens_vendidos = (
            EventoSite.objects
            .filter(periodo, tipo='pedido_finalizado', produto_slug__gt='')
            .aggregate(t=Sum('quantidade'))['t'] or 0
        )
        carrinhos_ab = (
            sess_qs
            .filter(Exists(EventoSite.objects.filter(sessao=OuterRef('pk'), tipo='produto_adicionado')))
            .exclude(Exists(comprou))
            .count()
        )
        checkouts_ab = (
            sess_qs
            .filter(Exists(EventoSite.objects.filter(sessao=OuterRef('pk'), tipo='checkout_iniciado')))
            .exclude(Exists(comprou))
            .count()
        )

        taxa         = round(pedidos / visitantes * 100, 1) if visitantes else 0
        media_pags   = round(visitas / visitantes, 1) if visitantes else 0

        def top10(tipo, filtro_slug=False):
            qs = EventoSite.objects.filter(periodo, tipo=tipo, produto_slug__gt='')
            if filtro_slug:
                qs = qs.filter(produto_nome__gt='')
            return list(
                qs.values('produto_slug', 'produto_nome')
                .annotate(total=Count('id'))
                .order_by('-total')[:10]
            )

        mais_vistos     = top10('produto_visualizado')
        mais_adicionados = top10('produto_adicionado')
        mais_vendidos   = list(
            EventoSite.objects
            .filter(periodo, tipo='pedido_finalizado', produto_slug__gt='')
            .values('produto_slug', 'produto_nome')
            .annotate(total=Count('id'), receita=Sum('valor_total'))
            .order_by('-total')[:10]
        )

        sessoes_all = list(
            SessaoSite.objects.filter(iniciada_em__range=(inicio, fim))
            .values('utm_source').annotate(total=Count('id')).order_by('-total')[:20]
        )
        agg: dict = {}
        for row in sessoes_all:
            label = self._label_origem(row['utm_source'])
            agg[label] = agg.get(label, 0) + row['total']
        total_orig = sum(agg.values()) or 1
        origens = [
            {'origem': k, 'total': v, 'pct': round(v / total_orig * 100, 1)}
            for k, v in sorted(agg.items(), key=lambda x: -x[1])
        ][:8]

        funil = self._calcular_funil(sess_qs, periodo)

        from django.db.models.functions import ExtractHour, ExtractIsoWeekDay

        NOMES_DIA      = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom']
        NOMES_DIA_FULL = ['Segunda', 'Terca', 'Quarta', 'Quinta', 'Sexta', 'Sabado', 'Domingo']

        por_dia_raw = dict(
            EventoSite.objects
            .filter(periodo, tipo='pagina_vista')
            .annotate(dia=ExtractIsoWeekDay('ocorrido_em'))
            .values('dia').annotate(t=Count('id')).values_list('dia', 't')
        )
        por_dia = [por_dia_raw.get(i + 1, 0) for i in range(7)]

        por_hora_raw = dict(
            EventoSite.objects
            .filter(periodo, tipo='pagina_vista')
            .annotate(hora=ExtractHour('ocorrido_em'))
            .values('hora').annotate(t=Count('id')).values_list('hora', 't')
        )
        hora_agg = [por_hora_raw.get(h, 0) for h in range(24)]
        pico_hora    = hora_agg.index(max(hora_agg)) if any(hora_agg) else None
        pico_dia_idx = por_dia.index(max(por_dia)) if any(por_dia) else None
        menor_dia_idx = min(
            (i for i, v in enumerate(por_dia) if v > 0),
            key=lambda i: por_dia[i], default=None,
        ) if any(por_dia) else None

        receita_float = float(receita)
        receita_fmt   = f"R$ {receita_float:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

        return {
            'visitas': visitas, 'visitantes': visitantes, 'pedidos': pedidos,
            'receita': receita_float, 'receita_fmt': receita_fmt,
            'itens_vendidos': itens_vendidos or 0,
            'carrinhos_abandonados': carrinhos_ab,
            'checkouts_abandonados': checkouts_ab,
            'taxa': taxa, 'media_paginas': media_pags,
            'mais_vistos': mais_vistos, 'mais_adicionados': mais_adicionados,
            'mais_vendidos': mais_vendidos, 'origens': origens, 'funil': funil,
            'por_dia': por_dia, 'nomes_dia': NOMES_DIA,
            'pico_hora': pico_hora,
            'pico_dia': NOMES_DIA_FULL[pico_dia_idx] if pico_dia_idx is not None else None,
            'pico_dia_total': por_dia[pico_dia_idx] if pico_dia_idx is not None else 0,
            'menor_dia': NOMES_DIA_FULL[menor_dia_idx] if menor_dia_idx is not None else None,
            'menor_dia_total': por_dia[menor_dia_idx] if menor_dia_idx is not None else 0,
        }

    def _calcular_funil(self, sess_qs, periodo):
        from apps.analytics.models import EventoSite
        visitantes = sess_qs.count()
        viram      = EventoSite.objects.filter(periodo, tipo='produto_visualizado').values('sessao_id').distinct().count()
        adicionaram = EventoSite.objects.filter(periodo, tipo='produto_adicionado').values('sessao_id').distinct().count()
        checkout   = EventoSite.objects.filter(periodo, tipo='checkout_iniciado').values('sessao_id').distinct().count()
        compraram  = EventoSite.objects.filter(periodo, tipo='pedido_finalizado', pedido_numero__gt='').values('sessao_id').distinct().count()
        base = visitantes or 1
        def pct(n): return round(n / base * 100, 1)
        return [
            {'label': 'Entraram no site',          'total': visitantes, 'pct': 100.0},
            {'label': 'Viram um produto',           'total': viram,      'pct': pct(viram)},
            {'label': 'Adicionaram ao carrinho',    'total': adicionaram,'pct': pct(adicionaram)},
            {'label': 'Foram ao checkout',          'total': checkout,   'pct': pct(checkout)},
            {'label': 'Finalizaram a compra',       'total': compraram,  'pct': pct(compraram)},
        ]

    def _label_origem(self, source):
        s = (source or '').lower().strip()
        if 'google' in s: return 'Google'
        if s in ('ig', 'instagram') or 'instagram' in s: return 'Instagram'
        if s in ('fb', 'facebook') or 'facebook' in s: return 'Facebook'
        if 'meta' in s: return 'Meta'
        if 'whatsapp' in s or 'wapp' in s: return 'WhatsApp'
        if s: return s.capitalize()
        return 'Direto / Outros'

    def _gerar_grafico_dias(self, por_dia, nomes_dia, dourado):
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.shapes import Drawing
        from reportlab.lib import colors

        drawing = Drawing(480, 145)
        bc = VerticalBarChart()
        bc.x = 42
        bc.y = 18
        bc.height = 112
        bc.width = 428

        bc.data = [tuple(por_dia)]
        bc.bars[0].fillColor = dourado
        bc.bars[0].strokeColor = None
        bc.barSpacing = 2
        bc.groupSpacing = 8

        bc.categoryAxis.categoryNames = nomes_dia
        bc.categoryAxis.labels.fontName = 'Helvetica'
        bc.categoryAxis.labels.fontSize = 9
        bc.categoryAxis.strokeColor = colors.HexColor('#cccccc')
        bc.categoryAxis.strokeWidth = 0.5

        bc.valueAxis.labels.fontName = 'Helvetica'
        bc.valueAxis.labels.fontSize = 8
        bc.valueAxis.strokeColor = colors.HexColor('#cccccc')
        bc.valueAxis.strokeWidth = 0.5
        bc.valueAxis.gridStrokeColor = colors.HexColor('#eeeeee')
        bc.valueAxis.gridStrokeWidth = 0.4
        bc.valueAxis.forceZero = 1

        drawing.add(bc)
        return drawing

    def _obter_analise_ia(self, stats, semana_inicio, semana_fim):
        api_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
        if not api_key:
            return ''

        funil_txt = '\n'.join(
            f"  - {e['label']}: {e['total']} ({e['pct']}%)" for e in stats['funil']
        )
        top_vistos = '\n'.join(
            f"  {i+1}. {(p.get('produto_nome') or p.get('produto_slug',''))[:50]} ({p['total']}x)"
            for i, p in enumerate(stats['mais_vistos'][:5])
        ) or '  Sem dados'
        top_adicionados = '\n'.join(
            f"  {i+1}. {(p.get('produto_nome') or p.get('produto_slug',''))[:50]} ({p['total']}x)"
            for i, p in enumerate(stats['mais_adicionados'][:5])
        ) or '  Sem dados'
        top_vendidos = '\n'.join(
            f"  {i+1}. {(p.get('produto_nome') or p.get('produto_slug',''))[:50]} ({p['total']} vendidos)"
            for i, p in enumerate(stats['mais_vendidos'][:5])
        ) or '  Sem dados'
        origens_txt = '\n'.join(
            f"  - {o['origem']}: {o['total']} visitantes ({o['pct']}%)"
            for o in stats['origens']
        ) or '  Sem dados'

        periodo_str = f"{semana_inicio.strftime('%d/%m/%Y')} a {semana_fim.strftime('%d/%m/%Y')}"
        prompt = f"""Voce e um especialista em analytics de e-commerce. Analise os dados abaixo para a D'ELLA Instore (moda feminina premium, loja online) e forneca uma analise objetiva em portugues.

Importante: nao inclua titulo, cabecalho nem a data no inicio da resposta - essas informacoes ja aparecem no PDF. Comece diretamente com o conteudo da analise. Nao use travessao (tracos longos tipo --) nem asteriscos.

DADOS DA SEMANA ({periodo_str}):
- Visitantes unicos: {stats['visitantes']}
- Paginas vistas: {stats['visitas']}
- Media de paginas por visitante: {stats['media_paginas']}
- Pedidos finalizados: {stats['pedidos']}
- Itens vendidos: {stats['itens_vendidos']}
- Receita total: {stats['receita_fmt']}
- Taxa de conversao: {stats['taxa']}%
- Carrinhos abandonados (adicionou mas nao comprou): {stats['carrinhos_abandonados']}
- Checkouts abandonados (iniciou checkout mas nao finalizou): {stats['checkouts_abandonados']}

FUNIL DE COMPRA:
{funil_txt}

TOP 5 PRODUTOS MAIS VISTOS:
{top_vistos}

TOP 5 PRODUTOS MAIS ADICIONADOS AO CARRINHO:
{top_adicionados}

TOP 5 PRODUTOS MAIS VENDIDOS:
{top_vendidos}

ORIGENS DOS VISITANTES:
{origens_txt}

Forneca uma analise estruturada com:
1. DESEMPENHO GERAL: como foi a semana em termos de trafego e vendas
2. PONTOS POSITIVOS: o que funcionou bem
3. PONTOS DE ATENCAO: onde melhorar (ex: alto abandono de carrinho, baixa conversao, etc)
4. SUGESTOES PARA PROXIMA SEMANA: acoes concretas e praticas

Se os dados forem insuficientes (poucos visitantes, semana sem pedidos), mencione isso e oriente a coletar mais dados antes de tirar conclusoes definitivas.

Seja direto e pratico. Maximo 350 palavras. Nao use markdown com asteriscos - use texto corrido com paragrafos."""

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model='claude-sonnet-4-6',
                max_tokens=1024,
                messages=[{'role': 'user', 'content': prompt}],
            )
            return msg.content[0].text
        except Exception as e:
            self.stderr.write(f'Erro na API Anthropic: {e}')
            return ''

    def _gerar_pdf(self, stats, analise, semana_inicio, semana_fim):
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (HRFlowable, Paragraph, SimpleDocTemplate,
                                         Spacer, Table, TableStyle)

        relatorios_dir = Path(settings.MEDIA_ROOT) / 'relatorios' / 'semanais'
        relatorios_dir.mkdir(parents=True, exist_ok=True)

        filename = f'relatorio_{semana_inicio}_{semana_fim}.pdf'
        filepath = relatorios_dir / filename

        doc = SimpleDocTemplate(
            str(filepath), pagesize=A4,
            leftMargin=2*cm, rightMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm,
        )

        dourado     = colors.HexColor('#c9a96e')
        preto       = colors.HexColor('#1a1a1a')
        cinza       = colors.HexColor('#666666')
        cinza_claro = colors.HexColor('#f5f5f3')

        titulo_st   = ParagraphStyle('T', fontName='Helvetica-Bold', fontSize=18,
                                      textColor=preto, leading=24, spaceAfter=8, alignment=TA_CENTER)
        sub_st      = ParagraphStyle('S', fontName='Helvetica', fontSize=10,
                                      textColor=cinza, leading=15, spaceAfter=5, alignment=TA_CENTER)
        secao_st    = ParagraphStyle('Se', fontName='Helvetica-Bold', fontSize=12,
                                      textColor=preto, spaceBefore=14, spaceAfter=6)
        corpo_st    = ParagraphStyle('C', fontName='Helvetica', fontSize=10,
                                      textColor=preto, spaceAfter=4, leading=14)

        def hr():
            return HRFlowable(width='100%', thickness=0.8, color=dourado)

        def tabela(data, col_widths, header_bg=None):
            t = Table(data, colWidths=col_widths)
            bg = header_bg or dourado
            t.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (-1, 0), bg),
                ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
                ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME',      (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE',      (0, 0), (-1, -1), 9),
                ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, cinza_claro]),
                ('GRID',          (0, 0), (-1, -1), 0.4, colors.HexColor('#dddddd')),
                ('TOPPADDING',    (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING',   (0, 0), (-1, -1), 7),
                ('RIGHTPADDING',  (0, 0), (-1, -1), 7),
            ]))
            return t

        E = []  # elements list

        # Cabecalho
        E.append(Paragraph("D'ELLA INSTORE", titulo_st))
        E.append(Paragraph("Resumo Semanal de Analytics", sub_st))
        E.append(Paragraph(
            f"Periodo: {semana_inicio.strftime('%d/%m/%Y')} a {semana_fim.strftime('%d/%m/%Y')}",
            sub_st,
        ))
        E.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y as %H:%M')}", sub_st))
        E.append(Spacer(1, 0.4*cm))
        E.append(hr())
        E.append(Spacer(1, 0.3*cm))

        def _n(v):
            return str(v) if v else '-'

        def _pct(v):
            return f"{v}%" if v else '-'

        # Resumo geral
        E.append(Paragraph("Resumo Geral", secao_st))
        resumo_data = [
            ['Metrica', 'Valor'],
            ['Visitantes unicos',                   _n(stats['visitantes'])],
            ['Paginas vistas',                      _n(stats['visitas'])],
            ['Media de paginas por visitante',      _n(stats['media_paginas'])],
            ['Pedidos finalizados',                 _n(stats['pedidos'])],
            ['Itens vendidos',                      _n(stats['itens_vendidos'])],
            ['Receita total',                       stats['receita_fmt'] if stats['receita'] > 0 else 'R$ -'],
            ['Taxa de conversao',                   _pct(stats['taxa'])],
            ['Carrinhos abandonados',               _n(stats['carrinhos_abandonados'])],
            ['Checkouts abandonados',               _n(stats['checkouts_abandonados'])],
        ]
        E.append(tabela(resumo_data, [10*cm, 6*cm]))
        E.append(Spacer(1, 0.4*cm))

        # Funil
        E.append(Paragraph("Funil de Compra", secao_st))
        funil_data = [['Etapa', 'Pessoas', '%']]
        for etapa in stats['funil']:
            funil_data.append([etapa['label'], _n(etapa['total']), _pct(etapa['pct'])])
        E.append(tabela(funil_data, [9*cm, 4*cm, 3*cm]))
        E.append(Spacer(1, 0.4*cm))

        # Grafico: trafego por dia da semana
        E.append(Paragraph("Trafego por Dia da Semana", secao_st))
        if any(stats.get('por_dia', [])):
            try:
                grafico_dia = self._gerar_grafico_dias(
                    stats['por_dia'], stats['nomes_dia'], dourado,
                )
                E.append(grafico_dia)
            except Exception as ex:
                self.stderr.write(f'Grafico PDF: {ex}')
                E.append(Paragraph('Grafico nao disponivel.', corpo_st))
            pico_data = [['Referencia', 'Detalhe']]
            if stats.get('pico_dia'):
                pico_data.append(['Dia com mais visitas', f"{stats['pico_dia']} ({stats['pico_dia_total']} visitas)"])
            if stats.get('menor_dia'):
                pico_data.append(['Dia mais tranquilo', f"{stats['menor_dia']} ({stats['menor_dia_total']} visitas)"])
            if stats.get('pico_hora') is not None:
                pico_data.append(['Horario de pico', f"{stats['pico_hora']}h - {stats['pico_hora']}h59"])
            if len(pico_data) > 1:
                E.append(Spacer(1, 0.25*cm))
                E.append(tabela(pico_data, [9*cm, 7*cm]))
        else:
            E.append(Paragraph('Sem dados de trafego no periodo.', corpo_st))
        E.append(Spacer(1, 0.4*cm))

        # Produtos
        for titulo_prod, lista_prod in [
            ('Top 10 Produtos Mais Vistos',                  stats['mais_vistos']),
            ('Top 10 Produtos Mais Adicionados ao Carrinho', stats['mais_adicionados']),
            ('Top 10 Produtos Mais Vendidos',                stats['mais_vendidos']),
        ]:
            E.append(Paragraph(titulo_prod, secao_st))
            if lista_prod:
                data_p = [['#', 'Produto', 'Qtd']]
                for i, p in enumerate(lista_prod[:10], 1):
                    nome = (p.get('produto_nome') or p.get('produto_slug') or '')[:55]
                    data_p.append([str(i), nome, str(p['total'])])
                E.append(tabela(data_p, [1*cm, 12*cm, 3*cm]))
            else:
                E.append(Paragraph('Sem dados no periodo.', corpo_st))
            E.append(Spacer(1, 0.3*cm))

        # Origens
        E.append(Paragraph("De Onde Vieram os Visitantes", secao_st))
        if stats['origens']:
            orig_data = [['Origem', 'Visitantes', '%']]
            for o in stats['origens']:
                orig_data.append([o['origem'], str(o['total']), f"{o['pct']}%"])
            E.append(tabela(orig_data, [9*cm, 4*cm, 3*cm]))
        else:
            E.append(Paragraph('Sem dados de origem no periodo.', corpo_st))
        E.append(Spacer(1, 0.5*cm))

        # Analise IA
        E.append(hr())
        E.append(Paragraph("Analise da Semana - Inteligencia Artificial", secao_st))
        if analise:
            for para in analise.split('\n\n'):
                para = para.strip()
                if para:
                    E.append(Paragraph(para, corpo_st))
                    E.append(Spacer(1, 0.2*cm))
        else:
            E.append(Paragraph(
                'Analise de IA nao disponivel. Configure ANTHROPIC_API_KEY no .env para ativar.',
                corpo_st,
            ))

        # Rodape
        E.append(Spacer(1, 0.5*cm))
        E.append(hr())
        E.append(Paragraph(
            f"D'ELLA Instore - Relatorio gerado automaticamente pelo sistemas.dellainstore.com",
            ParagraphStyle('Rod', fontName='Helvetica', fontSize=8, textColor=cinza, alignment=TA_CENTER),
        ))

        doc.build(E)
        return str(Path('relatorios') / 'semanais' / filename)
