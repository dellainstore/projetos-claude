"""
Relatorio diario de seguranca do site D'ELLA.

Analisa logs das ultimas N horas, classifica o risco e envia e-mail.
Uso: python manage.py relatorio_seguranca --settings=core.settings.production
"""
import re
import subprocess
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.formats import date_format


BASE_DIR   = Path(settings.BASE_DIR)
LOGS_DIR   = BASE_DIR / 'logs'
FAIL2BAN   = '/var/log/fail2ban.log'

# Caminhos suspeitos que indicam varredura automatizada
_SCANNER_PATHS = re.compile(
    r'(?:\.php|wp-admin|wp-content|wp-includes|wp-login|phpmyadmin|adminer|xmlrpc'
    r'|\.git|\.env|\.htaccess|\.htpasswd|web\.config|Dockerfile|docker-compose'
    r'|terraform|\.tfstate|\.tfvars|\.boto|\.netrc|\.s3cfg|credentials\.json'
    r'|/etc/|/proc/|/mcp)',
    re.IGNORECASE,
)

_SCANNER_UA = re.compile(r'(?:curl/|zgrab|masscan|nikto|sqlmap|nuclei|nmap|dirbuster)', re.IGNORECASE)

# path_info das linhas AXES: distingue login de cliente (loja) de login do
# painel administrativo -- sao riscos muito diferentes. Ver incidente
# 2026-08-09: cliente convidada (Camila Dantas, pedido 2026-0018) tentou
# logar em /conta/entrar/ vinda do e-mail de avaliacao, errou a senha 6x
# (nao tem conta -- comprou sem cadastro) e foi bloqueada pelo Axes. O
# relatorio classificou como VERMELHO e mandou "reforce a senha do admin",
# quando na verdade era uma cliente sem conta tentando entrar na loja.
_PATH_INFO = re.compile(r'path_info:\s*"([^"]*)"')


def _eh_path_painel(linha: str) -> bool:
    """True se a linha AXES for de tentativa de login no /painel/ (admin)."""
    m = _PATH_INFO.search(linha)
    return bool(m and m.group(1).startswith('/painel/'))


# Bloqueios de login mal sucedidos de clientes na loja sao normais (senha
# esquecida, checkout como convidada sem conta). So vira sinal de risco
# real (credential stuffing) em volume incomum -- diferente do painel
# administrativo, onde qualquer bloqueio ja e sensivel.
LIMIAR_FALHAS_LOJA_AMARELO   = 15
LIMIAR_BLOQUEIOS_LOJA_AMARELO = 3


def _dedup_episodios(itens: list[tuple], janela_seg: int = 600) -> list[str]:
    """Colapsa linhas 'AXES: Locking out' repetidas da MESMA pessoa bloqueada
    tentando de novo durante o cooloff. O Axes grava uma linha nova a cada
    tentativa enquanto o IP/usuario continua bloqueado -- sem isso, 1 pessoa
    bloqueada e tenta de novo 3x em 2 minutos virava "3 bloqueios" no
    relatorio. Linhas dentro de janela_seg da anterior contam como o mesmo
    episodio; só uma lacuna maior que isso indica um bloqueio novo de fato."""
    if not itens:
        return []
    itens_ordenados = sorted(itens, key=lambda x: x[0])
    episodios = [itens_ordenados[0][1]]
    ultimo_ts = itens_ordenados[0][0]
    for ts, linha in itens_ordenados[1:]:
        if (ts - ultimo_ts).total_seconds() > janela_seg:
            episodios.append(linha)
        ultimo_ts = ts
    return episodios


# --------------------------------------------------------------------------- #
# Helpers de parse                                                             #
# --------------------------------------------------------------------------- #

def _ler_log(caminho: Path, encoding='utf-8', errors='replace') -> list[str]:
    try:
        with open(caminho, encoding=encoding, errors=errors) as f:
            return f.readlines()
    except FileNotFoundError:
        return []


def _ler_fail2ban() -> list[str]:
    """Le fail2ban.log via sudo (requer regra em /etc/sudoers.d/della-monitoring)."""
    try:
        r = subprocess.run(
            ['sudo', '-n', 'tail', '-n', '100000', FAIL2BAN],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.splitlines()
    except Exception:
        pass
    return []


def _ts_security(linha: str):
    """Extrai datetime de linha do security.log: 'WARNING 2026-05-22 13:10:29,...'"""
    m = re.match(r'\w+\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', linha)
    if m:
        from django.utils.dateparse import parse_datetime
        return parse_datetime(m.group(1).replace(' ', 'T'))
    return None


def _ts_gunicorn(linha: str):
    """Extrai datetime de linha do gunicorn_access.log: '[22/May/2026:13:10:29 -0300]'"""
    m = re.search(r'\[(\d{2}/\w+/\d{4}):(\d{2}:\d{2}:\d{2})', linha)
    if m:
        from datetime import datetime
        meses = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,
                 'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
        d, t = m.group(1), m.group(2)
        dia, mes_str, ano = d.split('/')
        mes = meses.get(mes_str, 1)
        naive = datetime(int(ano), mes, int(dia),
                         int(t[:2]), int(t[3:5]), int(t[6:8]))
        return timezone.make_aware(naive)
    return None


def _ts_fail2ban(linha: str):
    """Extrai datetime de linha do fail2ban.log: '2026-05-22 13:10:29,123'"""
    m = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', linha)
    if m:
        from django.utils.dateparse import parse_datetime
        return parse_datetime(m.group(1).replace(' ', 'T'))
    return None


# --------------------------------------------------------------------------- #
# Coleta de dados                                                              #
# --------------------------------------------------------------------------- #

def _analisar_security_log(desde):
    falhas_login_loja   = []
    falhas_login_painel = []
    bloqueios_loja_raw   = []  # (ts, linha) -- dedup por episodio antes de contar
    bloqueios_painel_raw = []
    disallowed    = []
    honeypot      = []

    for linha in _ler_log(LOGS_DIR / 'security.log'):
        ts = _ts_security(linha)
        if ts and timezone.is_naive(ts):
            ts = timezone.make_aware(ts)
        if not ts or ts < desde:
            continue

        if 'HONEYPOT' in linha and 'contato' in linha:
            honeypot.append(linha.strip())
        elif 'TIMING contato' in linha:
            honeypot.append(linha.strip())
        elif 'AXES: Locking out' in linha:
            if _eh_path_painel(linha):
                bloqueios_painel_raw.append((ts, linha.strip()))
            else:
                bloqueios_loja_raw.append((ts, linha.strip()))
        elif 'AXES: New login failure' in linha:
            if _eh_path_painel(linha):
                falhas_login_painel.append(linha.strip())
            else:
                falhas_login_loja.append(linha.strip())
        elif 'DisallowedHost' in linha and 'Invalid HTTP_HOST' in linha:
            m = re.search(r"'([^']+)'", linha)
            host = m.group(1) if m else '?'
            disallowed.append(host)

    bloqueios_loja   = _dedup_episodios(bloqueios_loja_raw)
    bloqueios_painel = _dedup_episodios(bloqueios_painel_raw)

    return {
        'falhas_login_loja':   falhas_login_loja,
        'falhas_login_painel': falhas_login_painel,
        'falhas_login':        falhas_login_loja + falhas_login_painel,
        'bloqueios_loja':      bloqueios_loja,
        'bloqueios_painel':    bloqueios_painel,
        'bloqueios':           bloqueios_loja + bloqueios_painel,
        'disallowed':    list(dict.fromkeys(disallowed)),  # unicos, ordem preservada
        'honeypot':      honeypot,
    }


def _analisar_gunicorn(desde):
    scanners   = []
    total_404  = 0
    ua_suspeitos = set()
    contato_posts = 0

    for linha in _ler_log(LOGS_DIR / 'gunicorn_access.log'):
        ts = _ts_gunicorn(linha)
        if not ts or ts < desde:
            continue

        if '" 404 ' in linha or '" 400 ' in linha:
            total_404 += 1

        if 'POST /contato/' in linha:
            contato_posts += 1

        ua_m = re.search(r'" "([^"]+)"$', linha.strip())
        ua = ua_m.group(1) if ua_m else ''
        if _SCANNER_UA.search(ua):
            ua_suspeitos.add(ua[:80])

        req_m = re.search(r'"(?:GET|POST|HEAD) ([^ ]+)', linha)
        if req_m and _SCANNER_PATHS.search(req_m.group(1)):
            scanners.append(linha.strip())

    return {
        'total_404':    total_404,
        'scanners':     scanners,
        'ua_suspeitos': list(ua_suspeitos),
        'contato_posts': contato_posts,
    }


def _analisar_fail2ban(desde):
    banimentos = []
    for linha in _ler_fail2ban():
        ts = _ts_fail2ban(linha)
        if ts and timezone.is_naive(ts):
            ts = timezone.make_aware(ts)
        if not ts or ts < desde:
            continue
        if '] Ban ' in linha:
            jail_m = re.search(r'\[([^\]]+)\] Ban (\S+)', linha)
            if jail_m:
                banimentos.append({'jail': jail_m.group(1), 'ip': jail_m.group(2), 'linha': linha.strip()})
    return banimentos


def _analisar_formularios(desde):
    from apps.conteudo.models import ContatoFormulario
    recentes = list(
        ContatoFormulario.objects.filter(recebido_em__gte=desde).order_by('-recebido_em')[:50]
    )
    suspeitos = []
    for c in recentes:
        msg = (c.mensagem or '').strip()
        # Detecta mensagens sem caracteres portugueses/latinos comuns
        tem_pt = bool(re.search(r'[a-zA-ZÀ-ú]{3,}', msg))
        parece_estrangeiro = tem_pt and not re.search(
            r'\b(?:oi|ol[aá]|bom|boa|precis|quero|gost|d[uú]vida|pedido|ajud|entrega|troca|produto|preco|pre[cç]o|tamanho|cor)\b',
            msg, re.IGNORECASE
        )
        if parece_estrangeiro and len(msg) > 5:
            suspeitos.append(c)
    return {'total': len(recentes), 'suspeitos': suspeitos}


# --------------------------------------------------------------------------- #
# Classificacao de risco                                                       #
# --------------------------------------------------------------------------- #

def _calcular_risco(seg, guni, f2b, forms) -> tuple[str, str, list[str]]:
    """Retorna (nivel, cor_hex, lista_de_motivos)."""
    motivos = []
    nivel = 'VERDE'

    # Painel administrativo: qualquer bloqueio ja e sensivel (e' o acesso
    # de quem gerencia a loja, nao de cliente).
    if seg['bloqueios_painel']:
        nivel = 'VERMELHO'
        motivos.append(f"{len(seg['bloqueios_painel'])} bloqueio(s) de login no PAINEL por excesso de tentativas")

    if seg['falhas_login_painel']:
        if nivel == 'VERDE':
            nivel = 'AMARELO'
        motivos.append(f"{len(seg['falhas_login_painel'])} tentativa(s) de login mal sucedida(s) no painel")

    # Loja: cliente errando senha (ou tentando entrar sem ter conta, ex:
    # checkout como convidada) e normal e nao eleva risco sozinho. So
    # escala se o volume for incompativel com "1 pessoa confusa".
    if len(seg['bloqueios_loja']) >= LIMIAR_BLOQUEIOS_LOJA_AMARELO:
        if nivel == 'VERDE':
            nivel = 'AMARELO'
        motivos.append(f"{len(seg['bloqueios_loja'])} bloqueio(s) de login de clientes na loja por excesso de tentativas")
    elif seg['bloqueios_loja']:
        motivos.append(f"{len(seg['bloqueios_loja'])} bloqueio(s) de login de cliente(s) na loja (volume normal, provavel senha esquecida)")

    if len(seg['falhas_login_loja']) >= LIMIAR_FALHAS_LOJA_AMARELO:
        if nivel == 'VERDE':
            nivel = 'AMARELO'
        motivos.append(f"{len(seg['falhas_login_loja'])} tentativa(s) de login mal sucedida(s) de clientes na loja")
    elif seg['falhas_login_loja']:
        motivos.append(f"{len(seg['falhas_login_loja'])} tentativa(s) de login mal sucedida(s) de cliente(s) na loja (volume normal)")

    if len(f2b) >= 5:
        nivel = 'VERMELHO'
        motivos.append(f"{len(f2b)} IPs banidos pelo fail2ban nas ultimas horas")

    if len(seg['honeypot']) >= 5:
        nivel = max(nivel, 'AMARELO') if nivel == 'VERDE' else nivel
        motivos.append(f"{len(seg['honeypot'])} captura(s) de honeypot no formulario")

    if guni['scanners']:
        if nivel == 'VERDE':
            nivel = 'AMARELO'
        motivos.append(f"{len(guni['scanners'])} requisicao(oes) de varredura detectada(s)")

    if forms['suspeitos']:
        if nivel == 'VERDE':
            nivel = 'AMARELO'
        motivos.append(f"{len(forms['suspeitos'])} formulario(s) de contato suspeito(s)")

    if f2b and nivel == 'VERDE':
        nivel = 'AMARELO'
        motivos.append(f"{len(f2b)} IP(s) banido(s) pelo fail2ban")

    if not motivos:
        motivos.append('Nenhuma atividade suspeita detectada')

    cores = {'VERDE': '#27ae60', 'AMARELO': '#e67e22', 'VERMELHO': '#c0392b'}
    return nivel, cores[nivel], motivos


_ORDEM_RISCO = {'VERDE': 0, 'AMARELO': 1, 'VERMELHO': 2}


def _calcular_risco_monitoramento(resumo_monit, saude_monit, integr_monit) -> tuple[str, list[str]]:
    """Risco baseado em erros 5xx, saude do sistema e integracoes (painel Monitoramento)."""
    motivos = []
    nivel = 'VERDE'

    if saude_monit.get('db') is False or saude_monit.get('cache') is False:
        nivel = 'VERMELHO'
        servico = 'banco de dados' if not saude_monit.get('db') else 'cache'
        motivos.append(f'Falha de prontidao no {servico} (/readyz)')

    total_24h = resumo_monit.get('total_24h', 0)
    if total_24h >= 10:
        nivel = 'VERMELHO'
        motivos.append(f'{total_24h} erro(s) 5xx nas ultimas 24h')
    elif total_24h >= 1:
        if nivel == 'VERDE':
            nivel = 'AMARELO'
        motivos.append(f'{total_24h} erro(s) 5xx nas ultimas 24h')

    incidentes = [i for i in integr_monit if i['estado'] == 'incidente']
    atencao = [i for i in integr_monit if i['estado'] == 'atencao']
    if incidentes:
        nivel = 'VERMELHO'
        motivos.append(f"Integracao(oes) em incidente: {', '.join(i['nome'] for i in incidentes)}")
    elif atencao:
        if nivel == 'VERDE':
            nivel = 'AMARELO'
        motivos.append(f"Integracao(oes) em atencao: {', '.join(i['nome'] for i in atencao)}")

    disco_pct = saude_monit.get('disco_pct')
    if disco_pct is not None and disco_pct >= 90:
        nivel = 'VERMELHO'
        motivos.append(f'Disco em {disco_pct}% de uso')

    if not motivos:
        motivos.append('Monitoramento sem incidentes nas ultimas 24h')

    return nivel, motivos


# --------------------------------------------------------------------------- #
# Geracao do e-mail HTML                                                       #
# --------------------------------------------------------------------------- #

def _fmt_hora(dt):
    if not dt:
        return ''
    return date_format(timezone.localtime(dt), 'd/m/Y H:i')


def _gerar_secao_monitoramento(resumo_monit, saude_monit, integr_monit):
    badge_estado = {
        'saudavel': ('#27ae60', 'saudavel'),
        'atencao': ('#e67e22', 'atencao'),
        'incidente': ('#c0392b', 'incidente'),
        'sem_dado': ('#999', 'sem dado'),
    }
    rows_integr = ''
    for i in integr_monit:
        c, label = badge_estado.get(i['estado'], ('#999', i['estado']))
        rows_integr += f'''
        <tr>
          <td style="padding:6px 12px;border-bottom:1px solid #f0f0f0;">{i['nome']}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #f0f0f0;text-align:center;">
            <span style="background:{c};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;">{label}</span>
          </td>
          <td style="padding:6px 12px;border-bottom:1px solid #f0f0f0;text-align:center;">{i['erros_24h']}</td>
        </tr>'''

    saude_ok = saude_monit.get('db') and saude_monit.get('cache')

    return f'''
    <h2 style="margin:0 0 12px;font-size:15px;color:#333;border-bottom:2px solid #f0f0f0;padding-bottom:8px;">Monitoramento (Erros 5xx e Integracoes)</h2>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <tr><td style="padding:6px 12px;">Erros 5xx (24h)</td><td style="padding:6px 12px;text-align:center;font-weight:600;">{resumo_monit.get('total_24h', 0)}</td></tr>
      <tr><td style="padding:6px 12px;">Erros 5xx (7 dias)</td><td style="padding:6px 12px;text-align:center;font-weight:600;">{resumo_monit.get('total_7d', 0)}</td></tr>
      <tr><td style="padding:6px 12px;">Falhas de checkout (7 dias)</td><td style="padding:6px 12px;text-align:center;font-weight:600;">{resumo_monit.get('checkout_7d', 0)}</td></tr>
      <tr><td style="padding:6px 12px;">Falhas de integracao (7 dias)</td><td style="padding:6px 12px;text-align:center;font-weight:600;">{resumo_monit.get('integracoes_7d', 0)}</td></tr>
      <tr><td style="padding:6px 12px;">Banco de dados / cache</td><td style="padding:6px 12px;text-align:center;">{'OK' if saude_ok else 'FALHA'}</td></tr>
      <tr><td style="padding:6px 12px;">Disco em uso</td><td style="padding:6px 12px;text-align:center;">{saude_monit.get('disco_pct', '?')}%</td></tr>
      <tr><td style="padding:6px 12px;">Memoria em uso</td><td style="padding:6px 12px;text-align:center;">{saude_monit.get('mem_pct', '?')}%</td></tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px;">
      <tr style="background:#f8f8f8;"><th style="padding:6px 12px;text-align:left;">Integracao</th><th style="padding:6px 12px;text-align:center;">Estado</th><th style="padding:6px 12px;text-align:center;">Erros 24h</th></tr>
      {rows_integr}
    </table>
    <p style="margin:12px 0 0;font-size:12px;color:#999;">
      Detalhes completos: <a href="https://www.dellainstore.com/painel/monitoramento/" style="color:#c9a96e;">Visao geral</a> &middot;
      <a href="https://www.dellainstore.com/painel/monitoramento/erros/" style="color:#c9a96e;">Erros 5xx</a> &middot;
      <a href="https://www.dellainstore.com/painel/monitoramento/checkout/" style="color:#c9a96e;">Checkout</a>
    </p>
    '''


def _gerar_html(seg, guni, f2b, forms, nivel, cor, motivos, horas, agora, resumo_monit, saude_monit, integr_monit):
    desde = agora - timedelta(hours=horas)

    icone = {'VERDE': '✅', 'AMARELO': '⚠️', 'VERMELHO': '🔴'}[nivel]

    # Linhas da tabela de resumo
    linhas_resumo = [
        ('Tentativas de login mal sucedidas (painel)', len(seg['falhas_login_painel']),
         'AMARELO' if seg['falhas_login_painel'] else 'VERDE'),
        ('Bloqueios de login (painel)', len(seg['bloqueios_painel']),
         'VERMELHO' if seg['bloqueios_painel'] else 'VERDE'),
        ('Tentativas de login mal sucedidas (loja)', len(seg['falhas_login_loja']),
         'AMARELO' if len(seg['falhas_login_loja']) >= LIMIAR_FALHAS_LOJA_AMARELO else 'VERDE'),
        ('Bloqueios de login (loja)', len(seg['bloqueios_loja']),
         'AMARELO' if len(seg['bloqueios_loja']) >= LIMIAR_BLOQUEIOS_LOJA_AMARELO else 'VERDE'),
        ('Capturas de honeypot (formulario)', len(seg['honeypot']),
         'AMARELO' if seg['honeypot'] else 'VERDE'),
        ('Hosts falsos bloqueados (DisallowedHost)', len(seg['disallowed']),
         'AMARELO' if len(seg['disallowed']) > 5 else 'VERDE'),
        ('Requisicoes de varredura (scanner)', len(guni['scanners']),
         'AMARELO' if guni['scanners'] else 'VERDE'),
        ('Erros 404/400 totais', guni['total_404'],
         'AMARELO' if guni['total_404'] > 200 else 'VERDE'),
        ('IPs banidos pelo fail2ban', len(f2b),
         'AMARELO' if f2b else 'VERDE'),
        ('Formularios de contato recebidos', forms['total'], 'VERDE'),
        ('Formularios suspeitos (idioma/padrao)', len(forms['suspeitos']),
         'AMARELO' if forms['suspeitos'] else 'VERDE'),
    ]

    cores_badge = {'VERDE': '#27ae60', 'AMARELO': '#e67e22', 'VERMELHO': '#c0392b'}

    def badge(nivel_cel):
        c = cores_badge.get(nivel_cel, '#888')
        return f'<span style="background:{c};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;">{nivel_cel}</span>'

    rows_resumo = ''
    for label, qtd, n_cel in linhas_resumo:
        bg = '#fff5f5' if n_cel == 'VERMELHO' else ('#fffbf0' if n_cel == 'AMARELO' else '#fff')
        rows_resumo += f'''
        <tr style="background:{bg};">
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;">{label}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;text-align:center;font-weight:600;">{qtd}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;text-align:center;">{badge(n_cel)}</td>
        </tr>'''

    # Secao de detalhes
    detalhes = ''

    if seg['bloqueios_painel']:
        items = '<br>'.join(
            re.sub(r'\*+', '[ocultado]', b)[:200] for b in seg['bloqueios_painel'][-5:]
        )
        detalhes += f'<h3 style="color:#c0392b;">Bloqueios de Login no PAINEL (Axes)</h3><p style="font-family:monospace;font-size:12px;background:#fff5f5;padding:10px;border-radius:4px;">{items}</p>'

    if seg['bloqueios_loja']:
        items = '<br>'.join(
            re.sub(r'\*+', '[ocultado]', b)[:200] for b in seg['bloqueios_loja'][-5:]
        )
        detalhes += f'<h3 style="color:#e67e22;">Bloqueios de Login na Loja (clientes)</h3><p style="font-family:monospace;font-size:12px;background:#fffbf0;padding:10px;border-radius:4px;">{items}</p>'

    if seg['honeypot']:
        items = '<br>'.join(h[:200] for h in seg['honeypot'][-5:])
        detalhes += f'<h3 style="color:#e67e22;">Capturas de Honeypot</h3><p style="font-family:monospace;font-size:12px;background:#fffbf0;padding:10px;border-radius:4px;">{items}</p>'

    if f2b:
        por_jail: dict[str, list] = {}
        for b in f2b:
            por_jail.setdefault(b['jail'], []).append(b['ip'])
        rows_f2b = ''
        for jail, ips in por_jail.items():
            for ip in ips[-10:]:
                rows_f2b += f'<tr><td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">{ip}</td><td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">{jail}</td></tr>'
        detalhes += f'''<h3 style="color:#e67e22;">IPs Banidos pelo Fail2ban</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <tr style="background:#f8f8f8;"><th style="padding:5px 10px;text-align:left;">IP</th><th style="padding:5px 10px;text-align:left;">Regra</th></tr>
          {rows_f2b}
        </table>'''

    if forms['suspeitos']:
        rows_s = ''
        for c in forms['suspeitos'][:5]:
            rows_s += f'<tr><td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">{c.nome[:40]}</td><td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">{c.email[:50]}</td><td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">{(c.mensagem or "")[:80]}...</td></tr>'
        detalhes += f'''<h3 style="color:#e67e22;">Formularios de Contato Suspeitos</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <tr style="background:#f8f8f8;"><th style="padding:5px 10px;text-align:left;">Nome</th><th style="padding:5px 10px;text-align:left;">E-mail</th><th style="padding:5px 10px;text-align:left;">Mensagem</th></tr>
          {rows_s}
        </table>'''

    if guni['ua_suspeitos']:
        uas = '<br>'.join(guni['ua_suspeitos'][:5])
        detalhes += f'<h3 style="color:#e67e22;">User-Agents de Scanner Detectados</h3><p style="font-family:monospace;font-size:12px;background:#fffbf0;padding:10px;border-radius:4px;">{uas}</p>'

    # Acao recomendada
    if nivel == 'VERDE':
        acao = 'Nenhuma acao necessaria. O site esta operando normalmente.'
    elif nivel == 'AMARELO':
        acao = ('Situacao de atencao. Revisite os detalhes abaixo. '
                'O fail2ban e os controles automaticos ja estao atuando. '
                'Se houver formularios suspeitos, marque como spam no painel.')
    elif seg['bloqueios_painel']:
        acao = ('ATENCAO: Atividade de alto risco detectada NO PAINEL ADMINISTRATIVO. '
                'Verifique imediatamente os bloqueios de login no painel '
                '(/painel/axes/accessattempt/) e considere reforcar a senha do admin.')
    else:
        acao = ('ATENCAO: Atividade de alto risco detectada (fora do login do painel). '
                'Revise os detalhes abaixo -- fail2ban ou outro sinal disparou o alerta.')

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:24px 0;">
  <tr><td align="center">
    <table width="620" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">

      <!-- Header -->
      <tr><td style="background:{cor};padding:24px 32px;text-align:center;">
        <p style="margin:0;font-size:28px;">{icone}</p>
        <h1 style="margin:8px 0 4px;color:#fff;font-size:22px;font-weight:700;">Relatorio de Seguranca e Monitoramento</h1>
        <p style="margin:0;color:rgba(255,255,255,.85);font-size:14px;">
          D&apos;ELLA Instore &mdash; {_fmt_hora(desde)} ate {_fmt_hora(agora)}
        </p>
        <p style="margin:8px 0 0;background:rgba(0,0,0,.15);display:inline-block;padding:4px 16px;border-radius:20px;color:#fff;font-size:13px;font-weight:700;">
          RISCO: {nivel}
        </p>
      </td></tr>

      <!-- Motivos -->
      <tr><td style="padding:20px 32px 0;">
        <p style="margin:0;font-size:14px;color:#555;line-height:1.6;">{acao}</p>
        <ul style="margin:12px 0 0;padding-left:20px;font-size:13px;color:#444;line-height:1.8;">
          {''.join(f'<li>{m}</li>' for m in motivos)}
        </ul>
      </td></tr>

      <!-- Tabela resumo -->
      <tr><td style="padding:20px 32px;">
        <h2 style="margin:0 0 12px;font-size:15px;color:#333;border-bottom:2px solid #f0f0f0;padding-bottom:8px;">Resumo do Periodo</h2>
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px;">
          <tr style="background:#f8f8f8;">
            <th style="padding:8px 12px;text-align:left;font-weight:600;">Evento</th>
            <th style="padding:8px 12px;text-align:center;font-weight:600;">Qtd</th>
            <th style="padding:8px 12px;text-align:center;font-weight:600;">Status</th>
          </tr>
          {rows_resumo}
        </table>
      </td></tr>

      <!-- Monitoramento -->
      <tr><td style="padding:0 32px 20px;">{_gerar_secao_monitoramento(resumo_monit, saude_monit, integr_monit)}</td></tr>

      <!-- Detalhes -->
      {'<tr><td style="padding:0 32px 20px;">' + detalhes + '</td></tr>' if detalhes else ''}

      <!-- Footer -->
      <tr><td style="background:#f8f8f8;padding:16px 32px;text-align:center;border-top:1px solid #eee;">
        <p style="margin:0;font-size:11px;color:#aaa;">
          Gerado automaticamente &mdash; D&apos;ELLA Instore &mdash; {_fmt_hora(agora)}<br>
          Periodo analisado: ultimas {horas} horas &mdash;
          <a href="https://www.dellainstore.com/painel/" style="color:#c9a96e;">Acessar painel</a>
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


# --------------------------------------------------------------------------- #
# Command                                                                      #
# --------------------------------------------------------------------------- #

class Command(BaseCommand):
    help = 'Gera e envia relatorio diario de seguranca por e-mail.'

    def add_arguments(self, parser):
        parser.add_argument('--horas', type=int, default=24,
                            help='Janela de analise em horas (padrao: 24)')
        parser.add_argument('--email', type=str, default='',
                            help='Destinatario (padrao: CONTATO_NOTIF_EMAILS)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Gera o relatorio mas nao envia o e-mail')

    def handle(self, *args, **options):
        horas    = options['horas']
        dry_run  = options['dry_run']
        agora    = timezone.now()
        desde    = agora - timedelta(hours=horas)

        self.stdout.write(f'Analisando ultimas {horas}h...')

        seg   = _analisar_security_log(desde)
        guni  = _analisar_gunicorn(desde)
        f2b   = _analisar_fail2ban(desde)
        forms = _analisar_formularios(desde)

        nivel, cor, motivos = _calcular_risco(seg, guni, f2b, forms)

        from apps.core_utils import monitoramento as monit
        resumo_monit = monit.resumo_geral()
        saude_monit  = monit.saude_sistema()
        integr_monit = monit.status_integracoes()
        nivel_monit, motivos_monit = _calcular_risco_monitoramento(resumo_monit, saude_monit, integr_monit)

        if _ORDEM_RISCO[nivel_monit] > _ORDEM_RISCO[nivel]:
            nivel = nivel_monit
            cor = {'VERDE': '#27ae60', 'AMARELO': '#e67e22', 'VERMELHO': '#c0392b'}[nivel]
        motivos = motivos + motivos_monit

        self.stdout.write(f'Risco: {nivel}')
        for m in motivos:
            self.stdout.write(f'  - {m}')

        html = _gerar_html(seg, guni, f2b, forms, nivel, cor, motivos, horas, agora,
                            resumo_monit, saude_monit, integr_monit)

        if dry_run:
            self.stdout.write('--dry-run: e-mail nao enviado.')
            return

        notif_raw = options['email'] or getattr(settings, 'SECURITY_NOTIF_EMAILS', '')
        to_list   = [e.strip() for e in notif_raw.split(',') if e.strip()]
        if not to_list:
            to_list = ['financeiro@dellainstore.com.br']

        icones = {'VERDE': '[OK]', 'AMARELO': '[ATENCAO]', 'VERMELHO': '[ALERTA]'}
        assunto = f"{icones[nivel]} Seguranca D'ELLA - {date_format(timezone.localtime(agora), 'd/m/Y')}"

        texto = (
            f"Relatorio de Seguranca D'ELLA Instore\n"
            f"Periodo: ultimas {horas} horas\n"
            f"Risco: {nivel}\n\n"
            + '\n'.join(f'- {m}' for m in motivos)
        )

        msg = EmailMultiAlternatives(
            subject    = assunto,
            body       = texto,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to         = [to_list[0]],
            bcc        = to_list[1:],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send()

        self.stdout.write(self.style.SUCCESS(f'E-mail enviado para {to_list}'))
