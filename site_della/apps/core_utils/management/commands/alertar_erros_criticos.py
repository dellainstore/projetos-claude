"""
Alerta por e-mail quase em tempo real quando um CLIENTE HUMANO real bate num
erro 5xx real durante o acesso ao site (Fase 8 - Monitoramento 5xx).

Diferente do relatorio_seguranca.py (resumo diario as 7h), este comando roda
com frequencia curta (cron sugerido: a cada 10 min) e filtra agressivamente
pra nao virar spam quando bots/scanners geram uma onda de 500:

- so considera fonte 'django' (erro real do Django/excecao), 'checkout'
  (falha de pagamento/frete/estoque durante a compra) e 'nginx' (502/503/504
  de gateway, coletados por coletar_erros_nginx -- o Django nem rodou, mas o
  cliente levou Bad Gateway na cara) -- nunca 'integracao' nem 'webhook'
  isolados, que sao falhas servidor-a-servidor, nao "cliente tentando acessar
  e travando";
- descarta caminhos tipicos de scanner/bot (wp-admin, .php, .env, .git etc.)
  e paineis internos (/admin/, /painel/, /bling/);
- descarta navegador nao reconhecido (curl, scripts e bots automatizados
  normalmente nao batem com nenhuma familia de browser conhecida em
  apps.core_utils.erros.classificar_ua), EXCETO em fonte 'checkout': quem
  chegou a criar pedido e chamar o gateway passou por form validado e e
  cliente real, mesmo com UA exotica (webview de app, navegador antigo);
- recusa de cartao pelo emissor so vira alerta em volume (_LIMIAR_RECUSA_
  CARTAO na janela): uma recusa isolada e rotina de varejo, varias seguidas
  sao sintoma de credencial/gateway quebrado. Falha real do gateway chega
  com status HTTP 4xx/5xx e alerta na primeira ocorrencia;
- so dispara 1 e-mail a cada 30 minutos (debounce via cache), mesmo que
  varios eventos novos apareçam -- nunca inunda a caixa de entrada.

Uso: python manage.py alertar_erros_criticos --settings=core.settings.production
"""
import re

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.formats import date_format

from apps.core_utils import monitoramento as monit

_JANELA_MIN_PADRAO = 15   # olha os ultimos N minutos a cada execucao
_DEBOUNCE_S = 60 * 30     # no maximo 1 e-mail a cada 30 min
_CACHE_DEBOUNCE = 'alerta5xx:ultimo_envio'
_LIMIAR_RECUSA_CARTAO = 4  # recusas na janela antes de virar alerta

_PATHS_IGNORAR = re.compile(
    r'(?:\.php|wp-admin|wp-content|wp-login|phpmyadmin|adminer|xmlrpc|\.git|\.env'
    r'|\.htaccess|\.htpasswd|web\.config|/etc/|/proc/|/mcp'
    r'|^/admin/|^/painel/|^/bling/)',
    re.IGNORECASE,
)


def _e_evento_real(ev: dict) -> bool:
    """Heuristica: so conta como 'erro real de cliente' o que sobra depois
    de descartar bot/scanner e trafego servidor-a-servidor."""
    if ev.get('fonte') not in ('django', 'checkout', 'nginx'):
        return False
    caminho = ev.get('caminho') or ''
    endpoint = ev.get('endpoint') or ''
    if _PATHS_IGNORAR.search(caminho) or _PATHS_IGNORAR.search(endpoint):
        return False
    # UA desconhecida so descarta trafego de navegacao. Um evento de checkout
    # ja passou por form validado e criacao de pedido: e cliente real mesmo
    # com UA que nao bate com nenhuma familia conhecida.
    if ev.get('navegador') == 'Outro' and ev.get('fonte') != 'checkout':
        return False
    return True


def _e_recusa_de_cartao(ev: dict) -> bool:
    """Recusa do emissor (sem saldo, cartao bloqueado, antifraude do banco).

    E rotina no varejo e nao indica site quebrado, entao so entra no alerta
    em volume. Falha real do gateway (credencial invalida, PagBank fora do ar)
    e registrada com o status HTTP da resposta, nao 200, e por isso nunca cai
    aqui: alerta na primeira ocorrencia.
    """
    return (
        ev.get('fonte') == 'checkout'
        and ev.get('etapa') == 'pagamento'
        and ev.get('status') == 200
    )


def _gerar_html_alerta(agrupados, total, minutos, agora):
    linhas = ''
    for g in agrupados[:15]:
        linhas += f'''
        <tr>
          <td style="padding:6px 12px;border-bottom:1px solid #f0f0f0;">{g['status']}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #f0f0f0;">{g['endpoint']}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #f0f0f0;">{(g.get('exc') or '')[:60]}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #f0f0f0;text-align:center;">{g['count']}</td>
        </tr>'''

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:24px 0;">
  <tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">
      <tr><td style="background:#c0392b;padding:20px 28px;text-align:center;">
        <p style="margin:0;font-size:24px;">&#128308;</p>
        <h1 style="margin:8px 0 0;color:#fff;font-size:18px;font-weight:700;">Erro real de cliente detectado</h1>
        <p style="margin:4px 0 0;color:rgba(255,255,255,.85);font-size:13px;">
          {total} ocorrencia(s) nos ultimos {minutos} min &mdash; {date_format(agora, 'd/m/Y H:i')}
        </p>
      </td></tr>
      <tr><td style="padding:20px 28px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px;">
          <tr style="background:#f8f8f8;">
            <th style="padding:6px 12px;text-align:left;">Status</th>
            <th style="padding:6px 12px;text-align:left;">Endpoint</th>
            <th style="padding:6px 12px;text-align:left;">Erro</th>
            <th style="padding:6px 12px;text-align:center;">Qtd</th>
          </tr>
          {linhas}
        </table>
        <p style="margin:16px 0 0;font-size:12px;color:#999;">
          Filtrado para excluir bots/scanners e paineis internos.
          Proximo alerta so depois de 30 min, mesmo que novos erros apareçam.<br>
          Detalhes completos: <a href="https://www.dellainstore.com/painel/monitoramento/erros/" style="color:#c9a96e;">Erros 5xx no painel</a>
        </p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""


class Command(BaseCommand):
    help = 'Alerta por e-mail quase em tempo real erros 5xx reais de clientes (nao bots).'

    def add_arguments(self, parser):
        parser.add_argument('--minutos', type=int, default=_JANELA_MIN_PADRAO,
                             help='Janela de analise em minutos (padrao: 15)')
        parser.add_argument('--email', type=str, default='',
                             help='Destinatario (padrao: SECURITY_NOTIF_EMAILS)')
        parser.add_argument('--dry-run', action='store_true',
                             help='Mostra o que seria enviado sem enviar')
        parser.add_argument('--forcar', action='store_true',
                             help='Ignora o debounce de 30 min (uso: teste manual)')

    def handle(self, *args, **options):
        minutos = options['minutos']
        agora = timezone.now()

        eventos = monit.ler_eventos(horas=minutos / 60)
        reais = [e for e in eventos if _e_evento_real(e)]

        # Recusa de cartao isolada nao vira e-mail (fica so no painel). Em
        # volume, entra no alerta junto com o resto.
        recusas = [e for e in reais if _e_recusa_de_cartao(e)]
        if recusas and len(recusas) < _LIMIAR_RECUSA_CARTAO:
            reais = [e for e in reais if not _e_recusa_de_cartao(e)]
            self.stdout.write(
                f'{len(recusas)} recusa(s) de cartao abaixo do limiar '
                f'({_LIMIAR_RECUSA_CARTAO} na janela): fora do alerta.'
            )

        if not reais:
            self.stdout.write(f'Nenhum erro real de cliente nos ultimos {minutos} min.')
            return

        if not options['forcar'] and cache.get(_CACHE_DEBOUNCE):
            self.stdout.write(
                f'{len(reais)} erro(s) real(is) detectado(s), mas ja houve alerta '
                f'ha menos de 30 min (debounce). Sem novo envio.'
            )
            return

        agrupados = monit.agregar(reais)
        self.stdout.write(f'{len(reais)} erro(s) real(is) de cliente -- preparando alerta.')

        if options['dry_run']:
            for g in agrupados:
                self.stdout.write(f"  - {g['status']} {g['endpoint']} x{g['count']}")
            self.stdout.write('--dry-run: e-mail nao enviado.')
            return

        html = _gerar_html_alerta(agrupados, len(reais), minutos, timezone.localtime(agora))
        texto = (
            f"Alerta: {len(reais)} erro(s) 5xx de cliente real nos ultimos {minutos} min.\n\n"
            + '\n'.join(f"- {g['status']} {g['endpoint']} (x{g['count']})" for g in agrupados[:10])
        )

        notif_raw = options['email'] or getattr(settings, 'SECURITY_NOTIF_EMAILS', '')
        to_list = [e.strip() for e in notif_raw.split(',') if e.strip()] or ['financeiro@dellainstore.com.br']

        msg = EmailMultiAlternatives(
            subject=f"[ALERTA] Erro no site D'ELLA - {len(reais)} ocorrencia(s) de cliente real",
            body=texto,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_list[0]],
            bcc=to_list[1:],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()

        cache.set(_CACHE_DEBOUNCE, True, _DEBOUNCE_S)
        self.stdout.write(self.style.SUCCESS(f'Alerta enviado para {to_list}'))
