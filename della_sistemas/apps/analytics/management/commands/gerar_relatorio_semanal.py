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

        historico = self._obter_historico(semana_inicio)
        analise = self._obter_analise_ia(stats, semana_inicio, semana_fim, historico)
        pdf_rel  = self._gerar_pdf(stats, analise, semana_inicio, semana_fim)

        from apps.analytics.models import RelatorioSemanal
        rel, _ = RelatorioSemanal.objects.update_or_create(
            semana_inicio=semana_inicio,
            defaults={
                'semana_fim': semana_fim, 'arquivo': pdf_rel,
                'visitantes': stats['visitantes'], 'paginas_vistas': stats['visitas'],
                'pedidos_pagos': stats['pedidos'], 'aguardando_pagamento': stats['aguardando'],
                'itens_vendidos': stats['itens_vendidos'], 'receita': stats['receita'],
                'taxa_conversao': stats['taxa'],
                'carrinhos_abandonados': stats['carrinhos_abandonados'],
                'checkouts_abandonados': stats['checkouts_abandonados'],
                'analise_ia': analise,
            },
        )
        # gerado_em e auto_now_add (so grava na criacao). Ao regerar a mesma
        # semana, atualizamos a data manualmente para refletir a ultima geracao.
        RelatorioSemanal.objects.filter(pk=rel.pk).update(gerado_em=timezone.now())
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
        # Mesma regra de trafego do painel (apps/analytics/trafego.py): alem do
        # is_bot da coleta, tira o scraper que passa por ele. Manter os dois
        # lados iguais, senao o PDF da semana diverge da tela que o gerou.
        from apps.analytics.trafego import base_trafego
        periodo   = Q(ocorrido_em__range=(inicio, fim), sessao__in=base_trafego().values('pk'))
        # Sessoes com atividade na semana, nao iniciadas nela: a sessao vive
        # muito mais que sete dias (ver a nota em views/visitas.py), e contar
        # por inicio deixa de fora quem voltou com o cookie antigo.
        _ativas   = EventoSite.objects.filter(periodo).values('sessao_id')
        sess_qs   = base_trafego().filter(pk__in=_ativas)
        # Venda = pedido PAGO (regra unica em apps/analytics/vendas.py). Pedido
        # gerado e nao pago entra em "aguardando"; cancelado nao entra em nada.
        from apps.analytics.vendas import (
            STATUS_AGUARDANDO, eventos_itens, eventos_pedidos, sessoes_com_venda_paga,
            ids_com_carrinho_liquido_positivo,
        )
        comprou = sessoes_com_venda_paga()

        visitas    = EventoSite.objects.filter(periodo, tipo='pagina_vista').count()
        # Visitante = quem teve ATIVIDADE na semana, nao quem criou a sessao
        # nela (mesmo criterio do painel, ver views/dashboard.py).
        visitantes = (
            EventoSite.objects.filter(periodo).values('sessao_id').distinct().count()
        )

        # Venda nao passa por filtro de bot (ver a nota em views/dashboard.py).
        periodo_venda = Q(ocorrido_em__range=(inicio, fim))
        pagos_qs = eventos_pedidos(periodo_venda)
        pedidos = pagos_qs.values('pedido_numero').distinct().count()
        receita = pagos_qs.aggregate(t=Sum('valor_total'))['t'] or 0
        itens_vendidos = eventos_itens(periodo_venda).aggregate(t=Sum('quantidade'))['t'] or 0

        aguardando_qs = eventos_pedidos(periodo_venda, status=STATUS_AGUARDANDO)
        aguardando = aguardando_qs.values('pedido_numero').distinct().count()
        aguardando_valor = float(aguardando_qs.aggregate(t=Sum('valor_total'))['t'] or 0)
        # Ancorado no EVENTO ocorrido na semana, nao na sessao iniciada nela
        # (mesmo criterio do painel, ver views/dashboard.py::_calcular_resumo).
        def _sessoes_com_evento(tipo):
            ids = (
                EventoSite.objects
                .filter(periodo, tipo=tipo)
                .values_list('sessao_id', flat=True).distinct()
            )
            return SessaoSite.objects.filter(pk__in=ids).exclude(Exists(comprou))

        # So conta quem ainda tem algo no carrinho -- quem adicionou e
        # removeu tudo antes de sair nao e um carrinho abandonado.
        candidatos_carrinho = _sessoes_com_evento('produto_adicionado').values_list('id', flat=True)
        carrinhos_ab = len(ids_com_carrinho_liquido_positivo(candidatos_carrinho))
        checkouts_ab = _sessoes_com_evento('checkout_iniciado').count()

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
            eventos_itens(periodo)
            .values('produto_slug', 'produto_nome')
            .annotate(total=Count('id'), receita=Sum('valor_total'))
            .order_by('-total')[:10]
        )

        from apps.analytics.attribution import label_origem
        from django.db.models import BooleanField, Case, Value, When

        sessoes_all = list(
            base_trafego().filter(pk__in=_ativas)
            .annotate(
                tem_fbclid=Case(When(fbclid='', then=Value(False)),
                                default=Value(True), output_field=BooleanField()),
                tem_gclid=Case(When(gclid='', then=Value(False)),
                               default=Value(True), output_field=BooleanField()),
            )
            .values('utm_source', 'utm_medium', 'tem_fbclid', 'tem_gclid')
            .annotate(total=Count('id')).order_by('-total')[:40]
        )
        agg: dict = {}
        for row in sessoes_all:
            label = label_origem(row['utm_source'], row['tem_fbclid'], row['tem_gclid'],
                                 row['utm_medium'])
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
            'aguardando': aguardando, 'aguardando_valor': aguardando_valor,
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
        from apps.analytics.vendas import eventos_pedidos
        # Visitante = quem teve ATIVIDADE na semana, nao quem criou a sessao
        # nela (mesmo criterio do painel, ver views/dashboard.py).
        visitantes = (
            EventoSite.objects.filter(periodo).values('sessao_id').distinct().count()
        )
        viram      = EventoSite.objects.filter(periodo, tipo='produto_visualizado').values('sessao_id').distinct().count()
        adicionaram = EventoSite.objects.filter(periodo, tipo='produto_adicionado').values('sessao_id').distinct().count()
        checkout   = EventoSite.objects.filter(periodo, tipo='checkout_iniciado').values('sessao_id').distinct().count()
        # Fechar o pedido nao e pagar: a diferenca entre as duas ultimas etapas
        # e o PIX gerado e nao pago / cartao recusado.
        fecharam   = EventoSite.objects.filter(periodo, tipo='pedido_finalizado', produto_slug='', pedido_numero__gt='').values('sessao_id').distinct().count()
        compraram  = eventos_pedidos(periodo).values('sessao_id').distinct().count()
        base = visitantes or 1
        def pct(n): return round(n / base * 100, 1)
        return [
            {'label': 'Entraram no site',          'total': visitantes, 'pct': 100.0},
            {'label': 'Viram um produto',           'total': viram,      'pct': pct(viram)},
            {'label': 'Adicionaram ao carrinho',    'total': adicionaram,'pct': pct(adicionaram)},
            {'label': 'Foram ao checkout',          'total': checkout,   'pct': pct(checkout)},
            {'label': 'Fecharam o pedido',          'total': fecharam,   'pct': pct(fecharam)},
            {'label': 'Pagaram (venda)',            'total': compraram,  'pct': pct(compraram)},
        ]

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

    def _obter_historico(self, semana_inicio, n_semanas=8):
        """Ultimas N semanas ja geradas, mais recente primeiro.

        E a "memoria" do relatorio: sem isso, cada semana e analisada como
        um evento isolado, sem noticia do que vem se repetindo ou mudando
        na operacao.
        """
        from apps.analytics.models import RelatorioSemanal
        return list(
            RelatorioSemanal.objects
            .filter(semana_inicio__lt=semana_inicio)
            .order_by('-semana_inicio')[:n_semanas]
        )

    def _obter_analise_ia(self, stats, semana_inicio, semana_fim, historico=None):
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

        historico = historico or []
        if historico:
            historico_txt = '\n'.join(
                f"  - {h.semana_inicio.strftime('%d/%m')} a {h.semana_fim.strftime('%d/%m')}: "
                f"{h.visitantes} visitantes, {h.pedidos_pagos} vendas pagas, "
                f"R$ {h.receita:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') +
                f", conversao {h.taxa_conversao}%, {h.carrinhos_abandonados} carrinhos abandonados"
                for h in historico
            )
            # Analise da semana imediatamente anterior, para dar continuidade
            # narrativa sem repetir as mesmas frases.
            analise_anterior = historico[0].analise_ia
            bloco_historico = f"""
HISTORICO DAS ULTIMAS {len(historico)} SEMANAS (mais recente primeiro, ja gerado antes desta):
{historico_txt}

ANALISE QUE VOCE MESMO ESCREVEU NA SEMANA ANTERIOR (so para voce ter contexto do que ja foi dito - NAO repita as mesmas frases nem a mesma estrutura):
{analise_anterior or '(sem analise registrada nessa semana)'}
"""
        else:
            bloco_historico = "\nHISTORICO: esta e a primeira semana com relatorio gerado, ainda nao ha semanas anteriores para comparar.\n"

        periodo_str = f"{semana_inicio.strftime('%d/%m/%Y')} a {semana_fim.strftime('%d/%m/%Y')}"
        prompt = f"""Voce e um especialista em analytics de e-commerce. Analise os dados abaixo para a D'ELLA Instore (moda feminina premium, loja online) e forneca uma analise objetiva em portugues.

Importante: nao inclua titulo, cabecalho nem a data no inicio da resposta - essas informacoes ja aparecem no PDF. Comece diretamente com o conteudo da analise. Nao use travessao (tracos longos tipo --) nem asteriscos.

Voce escreve esse relatorio toda semana e tem memoria das semanas anteriores (dados abaixo). Trate a operacao como algo continuo: aponte tendencias reais (ex: "e a terceira semana seguida de queda na conversao", "o pico de trafego de sexta se repete ha um mes", "carrinho abandonado caiu depois da mudanca da semana passada"), e nao comente a semana atual como um evento isolado. Ao mesmo tempo, NAO repita as mesmas frases, exemplos ou estrutura de paragrafo da analise anterior (colada abaixo) - varie a redacao mesmo quando o diagnostico for parecido. Se o historico for curto (menos de 3 semanas) ou os numeros muito instaveis, foque mais na semana atual e comente a tendencia com cautela.
{bloco_historico}

COMO LER OS NUMEROS (mudou em 24/08/2026, considere ao comparar com semanas anteriores):
- "Visitante" agora e quem teve ATIVIDADE na semana, e nao quem criou a sessao nela.
  Quem voltou ao site com o cookie de uma semana passada passou a contar.
- O trafego automatizado que escapava do filtro de robo foi retirado da conta. Era
  cerca de um terco do que antes aparecia como gente real, quase todo em computador
  e sem nenhuma compra.
- Por causa desses dois pontos, os numeros de visitantes das semanas ANTERIORES no
  historico nao sao diretamente comparaveis com os desta: a base mudou. Compare
  tendencia de conversao, receita e comportamento, e evite afirmar que o trafego
  "caiu" ou "subiu" com base em semanas de antes dessa data. Se precisar mencionar,
  diga que a forma de contar mudou.
- As origens agora tem nome de gente ("Anuncio no Instagram", "Link da bio",
  "Loja do Instagram", "Direto ou busca"). "Direto ou busca" reune quem digitou o
  endereco, veio da busca do Google sem anuncio ou de link no WhatsApp: NAO trate
  isso como trafego sem valor, porque costuma ser quem ja conhece a marca.

DADOS DA SEMANA ({periodo_str}):
- Visitantes unicos: {stats['visitantes']}
- Paginas vistas: {stats['visitas']}
- Media de paginas por visitante: {stats['media_paginas']}
- Vendas pagas (pedidos com pagamento confirmado): {stats['pedidos']}
- Pedidos gerados e ainda nao pagos (PIX aberto, cartao em analise): {stats['aguardando']}
- Itens vendidos: {stats['itens_vendidos']}
- Receita total (so pedidos pagos): {stats['receita_fmt']}
- Taxa de conversao (sobre vendas pagas): {stats['taxa']}%
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
1. DESEMPENHO GERAL: como foi a semana em termos de trafego e vendas, situando no contexto das semanas anteriores (melhorou, piorou ou manteve o padrao recente)
2. PONTOS POSITIVOS: o que funcionou bem, destacando o que e recorrente (se ja apareceu em semanas passadas) e o que e novo
3. PONTOS DE ATENCAO: onde melhorar (ex: alto abandono de carrinho, baixa conversao, etc), sinalizando se e um problema pontual desta semana ou algo que persiste ha mais tempo
4. SUGESTOES PARA PROXIMA SEMANA: acoes concretas e praticas, levando em conta o que ja foi sugerido antes (nao repita uma sugestao antiga como se fosse nova sem dizer que ela ainda nao foi resolvida)

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
            ['Vendas pagas',                        _n(stats['pedidos'])],
            ['Pedidos aguardando pagamento',        _n(stats['aguardando'])],
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
