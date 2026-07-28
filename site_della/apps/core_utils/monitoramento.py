"""
Agregacao (somente leitura) para o painel de Monitoramento.

Le o log estruturado logs/erros_5xx.jsonl (e rotacionados), aplica filtros e
agrega por chave de deduplicacao. Nao escreve nada, nao expoe dado sensivel
(o log ja e sanitizado na origem, em apps.core_utils.erros).

Saude do sistema: metricas baratas (disco, memoria) sao cacheadas para nao
rodar a cada request; banco/cache reaproveitam apps.core_utils.health.
"""
import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

_LOG_BASE = Path(settings.BASE_DIR) / 'logs' / 'erros_5xx.jsonl'
_MAX_LINHAS = 20000  # teto de leitura para nao estourar memoria

INTEGRACOES = ('pagbank', 'melhorenvio', 'bling', 'correios', 'brevo', 'meta_capi', 'ga4')


def _arquivos_log():
    """Arquivo atual + rotacionados (.1 .. .9), do mais novo ao mais antigo."""
    arqs = []
    if _LOG_BASE.exists():
        arqs.append(_LOG_BASE)
    for i in range(1, 10):
        p = _LOG_BASE.with_name(f'{_LOG_BASE.name}.{i}')
        if p.exists():
            arqs.append(p)
    return arqs


def ler_eventos(horas: int = 168, filtros: dict | None = None) -> list[dict]:
    """Le eventos das ultimas `horas`, aplicando filtros opcionais.

    filtros aceita: status (int), fonte, integracao, endpoint_contem, dispositivo.
    """
    filtros = filtros or {}
    corte = datetime.now(timezone.utc) - timedelta(hours=horas)
    eventos: list[dict] = []
    for arq in _arquivos_log():
        try:
            with arq.open('r', encoding='utf-8', errors='replace') as fh:
                for linha in fh:
                    linha = linha.strip()
                    if not linha:
                        continue
                    try:
                        ev = json.loads(linha)
                    except (ValueError, TypeError):
                        continue
                    ts = ev.get('ts', '')
                    try:
                        quando = datetime.fromisoformat(ts)
                        if quando.tzinfo is None:
                            quando = quando.replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        continue
                    if quando < corte:
                        continue
                    if filtros.get('status') and ev.get('status') != filtros['status']:
                        continue
                    if filtros.get('fonte') and ev.get('fonte') != filtros['fonte']:
                        continue
                    if filtros.get('integracao') and ev.get('integracao') != filtros['integracao']:
                        continue
                    if filtros.get('dispositivo') and ev.get('dispositivo') != filtros['dispositivo']:
                        continue
                    ec = filtros.get('endpoint_contem')
                    if ec and ec.lower() not in (ev.get('endpoint', '') + ev.get('caminho', '')).lower():
                        continue
                    eventos.append(ev)
                    if len(eventos) >= _MAX_LINHAS:
                        break
        except OSError:
            continue
    eventos.sort(key=lambda e: e.get('ts', ''), reverse=True)
    return eventos


def agregar(eventos: list[dict]) -> list[dict]:
    """Agrupa por chave de dedup: contagem, primeira/ultima ocorrencia, amostra."""
    grupos: dict[str, dict] = {}
    for ev in eventos:
        chave = ev.get('dedup') or f"{ev.get('status')}:{ev.get('endpoint')}"
        g = grupos.get(chave)
        if g is None:
            grupos[chave] = {
                'dedup': chave,
                'status': ev.get('status'),
                'fonte': ev.get('fonte'),
                'endpoint': ev.get('endpoint') or ev.get('caminho'),
                'exc': ev.get('exc'),
                'integracao': ev.get('integracao'),
                'count': 1,
                'primeira': ev.get('ts'),
                'ultima': ev.get('ts'),
                'amostra': ev,
            }
        else:
            g['count'] += 1
            if ev.get('ts', '') < g['primeira']:
                g['primeira'] = ev.get('ts')
            if ev.get('ts', '') > g['ultima']:
                g['ultima'] = ev.get('ts')
    return sorted(grupos.values(), key=lambda g: (g['count'], g['ultima']), reverse=True)


def resumo_por_status(eventos: list[dict]) -> dict:
    contagem = defaultdict(int)
    for ev in eventos:
        contagem[ev.get('status', 0)] += 1
    return dict(contagem)


def resumo_geral() -> dict:
    """Cards da Visao geral: 5xx em 24h e 7d, e por status."""
    ev7 = ler_eventos(horas=168)
    ev24 = [e for e in ev7 if _dentro(e, 24)]
    checkout = [e for e in ev7 if e.get('fonte') == 'checkout']
    integr = [e for e in ev7 if e.get('fonte') == 'integracao']
    # Gateway (502/503/504): o Django nao chegou a responder, entao esses
    # eventos so existem porque coletar_erros_nginx os le do log do nginx.
    gateway = [e for e in ev7 if e.get('fonte') == 'nginx']
    return {
        'total_24h': len(ev24),
        'total_7d': len(ev7),
        'por_status_24h': resumo_por_status(ev24),
        'checkout_7d': len(checkout),
        'integracoes_7d': len(integr),
        'gateway_7d': len(gateway),
        'gateway_24h': len([e for e in gateway if _dentro(e, 24)]),
        'ultimo': ev7[0] if ev7 else None,
    }


def _dentro(ev: dict, horas: int) -> bool:
    try:
        quando = datetime.fromisoformat(ev.get('ts', ''))
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False
    return quando >= datetime.now(timezone.utc) - timedelta(hours=horas)


def status_integracoes() -> list[dict]:
    """Estado por integracao: ultimo erro conhecido + contagem 24h.

    'Ultimo sucesso' vem de marcadores gravados no cache pelas proprias
    integracoes (registrar_sucesso_integracao); se ausente, fica 'sem dado'.
    """
    eventos = ler_eventos(horas=168)
    por_integr = defaultdict(list)
    for ev in eventos:
        if ev.get('integracao'):
            por_integr[ev['integracao']].append(ev)
    linhas = []
    for nome in INTEGRACOES:
        erros = por_integr.get(nome, [])
        erros_24h = [e for e in erros if _dentro(e, 24)]
        ultimo_sucesso = cache.get(f'monit:sucesso:{nome}')
        if erros_24h:
            estado = 'incidente' if len(erros_24h) >= 3 else 'atencao'
        elif ultimo_sucesso:
            estado = 'saudavel'
        else:
            estado = 'sem_dado'
        linhas.append({
            'nome': nome,
            'estado': estado,
            'erros_24h': len(erros_24h),
            'ultimo_erro': erros[0]['ts'] if erros else None,
            'ultimo_erro_resumo': erros[0].get('resumo') if erros else '',
            'ultimo_sucesso': ultimo_sucesso,
        })
    return linhas


def registrar_sucesso_integracao(nome: str) -> None:
    """Marca ultimo sucesso de uma integracao (chamado pelas integracoes)."""
    try:
        cache.set(f'monit:sucesso:{nome}', datetime.now(timezone.utc).isoformat(timespec='seconds'), 60 * 60 * 24 * 3)
    except Exception:
        pass


def saude_sistema() -> dict:
    """Metricas de saude. Disco/memoria cacheadas por 60s (leitura barata)."""
    from apps.core_utils.health import checar_prontidao
    prontidao = checar_prontidao()

    dados = cache.get('monit:saude_os')
    if dados is None:
        dados = {}
        try:
            total, usado, livre = shutil.disk_usage(str(settings.BASE_DIR))
            dados['disco_pct'] = round(usado / total * 100, 1)
            dados['disco_livre_gb'] = round(livre / (1024 ** 3), 1)
        except Exception:
            dados['disco_pct'] = None
        try:
            # Memoria via /proc/meminfo (Linux), sem dependencia externa.
            meminfo = {}
            with open('/proc/meminfo') as fh:
                for linha in fh:
                    partes = linha.split(':')
                    if len(partes) == 2:
                        meminfo[partes[0].strip()] = int(partes[1].strip().split()[0])
            total_kb = meminfo.get('MemTotal', 0)
            disp_kb = meminfo.get('MemAvailable', 0)
            if total_kb:
                dados['mem_pct'] = round((total_kb - disp_kb) / total_kb * 100, 1)
                dados['mem_disp_mb'] = round(disp_kb / 1024)
        except Exception:
            dados['mem_pct'] = None
        try:
            dados['load1'] = round(os.getloadavg()[0], 2)
        except Exception:
            dados['load1'] = None
        cache.set('monit:saude_os', dados, 60)

    return {
        'db': prontidao['db'],
        'cache': prontidao['cache'],
        **dados,
    }
