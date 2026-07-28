"""
Registro estruturado de erros 5xx e falhas de integracao.

Objetivos de seguranca (NAO regredir):
- Nunca gravar query string, corpo de POST, cookies, Authorization, CSRF,
  token PagBank, cartao, CVV, CPF, endereco, e-mail ou telefone.
- Nunca gravar direto no banco dentro do caminho de erro (o banco pode ser a
  causa do 500). Usamos log estruturado JSONL append-only + rotacao. O painel
  de Monitoramento agrega esse arquivo (somente leitura).
- Nunca levantar excecao a partir do proprio registro (falha de log e engolida).

Formato: uma linha JSON por evento em logs/erros_5xx.jsonl (rotacionado pelo
handler file_erros5xx configurado em settings). Deduplicacao e rate limit por
chave para nao inundar o log quando um erro repete.
"""
import hashlib
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from django.conf import settings
from django.core.cache import cache

# Logger dedicado — handler file_erros5xx (RotatingFileHandler) definido em
# core/settings/production.py. Em dev cai no console.
_logger = logging.getLogger('apps.core_utils.erros')

# Rate limit: no maximo N gravacoes por chave de deduplicacao a cada janela.
_JANELA_S = 60
_MAX_POR_JANELA = 20


def novo_correlation_id() -> str:
    return uuid.uuid4().hex[:16]


def _hash_sessao(session_key: str) -> str:
    if not session_key:
        return ''
    salt = getattr(settings, 'SECRET_KEY', '')
    return hashlib.sha256(f'{salt}{session_key}'.encode()).hexdigest()[:12]


_UA_BROWSERS = (
    ('Edg', 'Edge'),
    ('OPR', 'Opera'),
    ('Chrome', 'Chrome'),
    ('CriOS', 'Chrome'),
    ('Firefox', 'Firefox'),
    ('FxiOS', 'Firefox'),
    ('Instagram', 'Instagram'),
    ('FBAN', 'Facebook'),
    ('FBAV', 'Facebook'),
    ('Version', 'Safari'),  # Safari mostra "Version/x Safari"
    ('Safari', 'Safari'),
)


def classificar_ua(ua: str) -> dict:
    """Extrai familia de navegador e tipo de dispositivo, sem guardar a UA crua."""
    ua = ua or ''
    familia = 'Outro'
    for marcador, nome in _UA_BROWSERS:
        if marcador in ua:
            familia = nome
            break
    is_mobile = bool(re.search(r'Mobi|Android|iPhone|iPad|iPod', ua))
    so = 'Outro'
    if 'Android' in ua:
        so = 'Android'
    elif re.search(r'iPhone|iPad|iPod', ua):
        so = 'iOS'
    elif 'Windows' in ua:
        so = 'Windows'
    elif 'Mac OS' in ua:
        so = 'macOS'
    elif 'Linux' in ua:
        so = 'Linux'
    return {'navegador': familia, 'dispositivo': 'mobile' if is_mobile else 'desktop', 'so': so}


def _sanitizar_resumo(texto: str, limite: int = 300) -> str:
    """Remove tokens obvios de dado sensivel de uma mensagem antes de gravar."""
    if not texto:
        return ''
    t = str(texto)[:limite * 2]
    # CPF/CNPJ, cartoes, e-mails, telefones, CEP com digitos longos
    t = re.sub(r'\b\d{11,16}\b', '[num]', t)
    t = re.sub(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b', '[cpf]', t)
    t = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', '[email]', t)
    t = re.sub(r'\bBearer\s+[A-Za-z0-9._-]+', 'Bearer [token]', t)
    return t[:limite]


def _rate_ok(chave_dedup: str) -> tuple[bool, int]:
    """Retorna (pode_gravar, ocorrencias_na_janela). Usa cache atomico."""
    ck = f'erro5xx:rl:{chave_dedup}'
    try:
        # incr atomico; se ausente, cria com TTL da janela.
        try:
            n = cache.incr(ck)
        except ValueError:
            cache.set(ck, 1, _JANELA_S)
            n = 1
        return (n <= _MAX_POR_JANELA, n)
    except Exception:
        # Cache indisponivel: nao bloquear o registro do erro.
        return (True, 1)


def registrar_evento_erro(
    *,
    status: int,
    fonte: str,
    app: str = 'site',
    metodo: str = '',
    caminho: str = '',
    endpoint: str = '',
    duracao_ms: int | None = None,
    exc_tipo: str = '',
    resumo: str = '',
    correlation_id: str = '',
    cf_ray: str = '',
    upstream_status: str = '',
    ua: str = '',
    session_key: str = '',
    integracao: str = '',
    extra: dict | None = None,
    ts: datetime | None = None,
) -> None:
    """Grava um evento de erro sanitizado no log estruturado. Nunca levanta.

    `ts` permite carimbar o momento real do evento em vez de "agora". Serve
    para coletores que leem uma fonte externa em lote (ex: o log do nginx, que
    e varrido a cada N minutos e traz erros ja ocorridos). Sem `ts`, usa agora.
    """
    try:
        # caminho: descarta querystring inteira (pode conter PII/UTM).
        caminho = (caminho or '').split('?', 1)[0][:300]
        chave_dedup = f'{status}:{app}:{endpoint or caminho}:{exc_tipo}'
        pode, ocorrencias = _rate_ok(chave_dedup)
        if not pode:
            return  # excesso na janela: nao inunda (contador ja registrou o pico)

        info_ua = classificar_ua(ua)
        quando = ts or datetime.now(timezone.utc)
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone.utc)
        registro = {
            'ts': quando.astimezone(timezone.utc).isoformat(timespec='seconds'),
            'status': status,
            'fonte': fonte,            # django | integracao | checkout | webhook
            'app': app,
            'metodo': metodo[:8],
            'caminho': caminho,
            'endpoint': (endpoint or '')[:120],
            'duracao_ms': duracao_ms,
            'exc': (exc_tipo or '')[:120],
            'resumo': _sanitizar_resumo(resumo),
            'cid': correlation_id[:16],
            'cf_ray': (cf_ray or '')[:32],
            'upstream': (upstream_status or '')[:16],
            'navegador': info_ua['navegador'],
            'dispositivo': info_ua['dispositivo'],
            'so': info_ua['so'],
            'sess': _hash_sessao(session_key),
            'integracao': (integracao or '')[:40],
            'dedup': chave_dedup[:200],
            'ocorr_janela': ocorrencias,
        }
        if extra:
            # Somente chaves de allowlist e valores curtos/nao sensiveis.
            for k in ('etapa', 'gateway', 'servico', 'pedido'):
                if k in extra and extra[k] is not None:
                    registro[k] = str(extra[k])[:60]
        _logger.error(json.dumps(registro, ensure_ascii=False))
    except Exception:
        # Registro de erro nunca pode gerar um segundo erro.
        pass


def registrar_erro_integracao(integracao: str, resumo: str, *, status: int = 502,
                              endpoint: str = '', correlation_id: str = '',
                              extra: dict | None = None) -> None:
    """Atalho para falhas de PagBank/Bling/Melhor Envio/Correios/Brevo/Meta."""
    registrar_evento_erro(
        status=status, fonte='integracao', integracao=integracao,
        endpoint=endpoint or integracao, resumo=resumo,
        correlation_id=correlation_id or novo_correlation_id(), extra=extra,
    )
