"""
Coleta erros de gateway (502/503/504) do log de acesso do nginx e alimenta o
mesmo log estruturado que o painel de Monitoramento ja le.

POR QUE ISSO EXISTE
-------------------
O `Erro5xxMiddleware` so enxerga erro que o Django conseguiu processar. Num
**502 o Django nem chega a rodar** (Gunicorn caiu, esta reiniciando ou nao
respondeu), entao nada e registrado: o painel fica limpo e o alerta diz
"nenhum erro real de cliente" enquanto o cliente toma Bad Gateway na cara.

Foi exatamente esse ponto cego que deixou passar, de 2026-05-19 a 2026-07-28,
um watchdog quebrado que reiniciava o Gunicorn a cada 2 minutos (48 mil
restarts). O unico sintoma visivel era cliente reclamando no WhatsApp. Ver
`scripts/README_watchdog.md` no repo `della-sistemas`.

O QUE ELE FAZ
-------------
Le apenas as linhas NOVAS do log (guarda offset + inode entre execucoes),
filtra status de gateway, agrupa por (status, caminho, navegador) e grava UM
evento por grupo via `registrar_evento_erro(fonte='nginx')`, com a contagem
real e a janela de tempo no resumo. Agrupar evita que uma janela de restart
com centenas de 502 vire centenas de linhas no log estruturado.

Nao coleta 500: esse o Django registra sozinho, com stack trace, e coletar de
novo aqui duplicaria o evento no painel.

PERMISSAO
---------
O log do nginx e `www-data:adm` (modo 640). O usuario que roda o cron precisa
estar no grupo `adm`:

    sudo usermod -aG adm neto

Sem isso o comando termina com aviso claro e exit code 1, sem quebrar o cron.

Uso:
    python manage.py coletar_erros_nginx --settings=core.settings.production
    python manage.py coletar_erros_nginx --dry-run --desde-inicio   # inspecao
"""
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core_utils.erros import classificar_ua, registrar_evento_erro

# Só status de gateway: sao os que o Django, por definicao, nao consegue ver.
STATUS_COLETADOS = (502, 503, 504)

_LOG_PADRAO = '/var/log/nginx/della_site_access.log'

# Formato "combined" do nginx (o site nao define log_format proprio):
#   IP - - [data] "METODO /caminho HTTP/1.1" status bytes "referer" "user-agent"
_LINHA_RE = re.compile(
    r'^(?P<ip>\S*) \S+ \S+ \[(?P<ts>[^\]]+)\] '
    r'"(?P<metodo>[A-Z]+) (?P<caminho>\S*)[^"]*" '
    r'(?P<status>\d{3}) \S+ '
    r'"(?P<referer>[^"]*)" "(?P<ua>[^"]*)"'
)

# %b do strptime depende de locale; o nginx sempre escreve mes em ingles.
_MESES = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
}
_TS_RE = re.compile(
    r'^(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-]\d{2})(\d{2})$'
)

# Teto por execucao, para uma varredura nunca virar um job pesado.
_MAX_LINHAS = 200_000


def _parse_ts(bruto: str) -> datetime | None:
    m = _TS_RE.match(bruto or '')
    if not m:
        return None
    dia, mes_txt, ano, hora, minuto, seg, tz_h, tz_m = m.groups()
    mes = _MESES.get(mes_txt)
    if not mes:
        return None
    try:
        offset = timedelta(hours=int(tz_h), minutes=int(tz_m) * (1 if int(tz_h) >= 0 else -1))
        return datetime(
            int(ano), mes, int(dia), int(hora), int(minuto), int(seg),
            tzinfo=timezone(offset),
        )
    except ValueError:
        return None


class Command(BaseCommand):
    help = 'Coleta 502/503/504 do log do nginx para o painel de Monitoramento.'

    def add_arguments(self, parser):
        parser.add_argument('--log', type=str, default='',
                            help=f'Caminho do access log (padrao: {_LOG_PADRAO})')
        parser.add_argument('--dry-run', action='store_true',
                            help='Mostra o que seria registrado, sem gravar nem mover o offset')
        parser.add_argument('--desde-inicio', action='store_true',
                            help='Le o arquivo inteiro em vez de continuar do offset')

    def handle(self, *args, **options):
        caminho_log = Path(options['log'] or getattr(settings, 'NGINX_ACCESS_LOG', _LOG_PADRAO))
        dry = options['dry_run']
        estado_path = Path(settings.BASE_DIR) / 'logs' / '.coletor_nginx_5xx.json'

        if not caminho_log.exists():
            self.stderr.write(f'Log nao encontrado: {caminho_log}')
            return

        try:
            stat = caminho_log.stat()
        except PermissionError:
            self.stderr.write(self._msg_permissao(caminho_log))
            raise SystemExit(1)

        estado = self._ler_estado(estado_path)

        try:
            with caminho_log.open('r', encoding='utf-8', errors='replace') as fh:
                # Só decide o offset depois de confirmar que da pra ler, senao a
                # mensagem de "primeira execucao" sai junto com a de permissao.
                fh.seek(self._offset_inicial(estado, stat, options['desde_inicio'], caminho_log))
                linhas = []
                for i, linha in enumerate(fh):
                    if i >= _MAX_LINHAS:
                        self.stderr.write(
                            f'Teto de {_MAX_LINHAS} linhas atingido nesta execucao; '
                            f'o restante entra na proxima.'
                        )
                        break
                    linhas.append(linha)
                novo_offset = fh.tell()
        except PermissionError:
            self.stderr.write(self._msg_permissao(caminho_log))
            raise SystemExit(1)

        grupos, lidas, nao_parseadas = self._agrupar(linhas)

        if nao_parseadas and lidas and nao_parseadas / lidas > 0.5:
            # Sinal de que o log_format do nginx mudou e o regex ficou obsoleto.
            self.stderr.write(
                f'ATENCAO: {nao_parseadas}/{lidas} linhas nao casaram com o formato '
                f'"combined" esperado. Conferir log_format do nginx antes de confiar '
                f'nesta coleta.'
            )

        if not grupos:
            self.stdout.write(f'Nenhum {"/".join(map(str, STATUS_COLETADOS))} nas {lidas} linha(s) novas.')
        for chave, g in sorted(grupos.items(), key=lambda kv: kv[1]['count'], reverse=True):
            status, caminho, navegador = chave
            resumo = (
                f'{g["count"]} request(s) com {status} no nginx em {caminho} '
                f'({navegador}), entre {g["primeira"]:%d/%m %H:%M:%S} e '
                f'{g["ultima"]:%d/%m %H:%M:%S}. O Django nao chegou a responder.'
            )
            self.stdout.write(f'  [{status}] {caminho} x{g["count"]} ({navegador})')
            if dry:
                continue
            registrar_evento_erro(
                status=status,
                fonte='nginx',
                metodo=g['metodo'],
                caminho=caminho,
                endpoint=caminho,
                resumo=resumo,
                ua=g['ua'],
                ts=g['ultima'],
            )

        if dry:
            self.stdout.write('dry-run: nada gravado e offset preservado.')
            return

        self._gravar_estado(estado_path, {'inode': stat.st_ino, 'offset': novo_offset})
        self.stdout.write(
            f'{lidas} linha(s) novas lidas, {len(grupos)} grupo(s) de erro registrados.'
        )

    # ---------- helpers ----------

    def _msg_permissao(self, caminho: Path) -> str:
        return (
            f'Sem permissao de leitura em {caminho}.\n'
            f'O log do nginx e www-data:adm (640). Rode uma vez, como root:\n'
            f'    sudo usermod -aG adm $USER\n'
            f'e reinicie a sessao (o cron ja pega o grupo novo na proxima execucao).'
        )

    def _ler_estado(self, path: Path) -> dict:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return {}

    def _gravar_estado(self, path: Path, dados: dict) -> None:
        try:
            path.write_text(json.dumps(dados))
        except OSError as exc:
            self.stderr.write(f'Nao foi possivel gravar o estado do coletor: {exc}')

    def _offset_inicial(self, estado: dict, stat, desde_inicio: bool, caminho_log: Path) -> int:
        if desde_inicio:
            return 0
        if not estado:
            # Primeira execucao: comeca do FIM. Sem isso, o primeiro run
            # importaria todo o historico do arquivo de uma vez e inundaria o
            # painel com erros antigos ja resolvidos.
            self.stdout.write(
                'Primeira execucao: partindo do fim do arquivo '
                '(use --desde-inicio para varrer o historico).'
            )
            return stat.st_size
        if estado.get('inode') != stat.st_ino or stat.st_size < estado.get('offset', 0):
            # Rotacionou (inode novo) ou truncou. Recomeca do zero do arquivo
            # atual; o que ficou no arquivo rotacionado entre a ultima execucao
            # e a rotacao nao e coletado (janela pequena, aceita de proposito
            # para nao ter que rastrear arquivos rotacionados).
            self.stdout.write(f'Rotacao detectada em {caminho_log.name}: recomecando do inicio do arquivo atual.')
            return 0
        return estado.get('offset', 0)

    def _agrupar(self, linhas: list[str]):
        grupos: dict[tuple, dict] = defaultdict(
            lambda: {'count': 0, 'primeira': None, 'ultima': None, 'ua': '', 'metodo': ''}
        )
        lidas = 0
        nao_parseadas = 0
        for linha in linhas:
            linha = linha.strip()
            if not linha:
                continue
            lidas += 1
            m = _LINHA_RE.match(linha)
            if not m:
                nao_parseadas += 1
                continue
            status = int(m.group('status'))
            if status not in STATUS_COLETADOS:
                continue
            quando = _parse_ts(m.group('ts'))
            if quando is None:
                nao_parseadas += 1
                continue
            caminho = m.group('caminho').split('?', 1)[0][:300]
            ua = m.group('ua')
            navegador = classificar_ua(ua)['navegador']

            g = grupos[(status, caminho, navegador)]
            g['count'] += 1
            g['ua'] = ua
            g['metodo'] = m.group('metodo')
            if g['primeira'] is None or quando < g['primeira']:
                g['primeira'] = quando
            if g['ultima'] is None or quando > g['ultima']:
                g['ultima'] = quando
        return grupos, lidas, nao_parseadas
