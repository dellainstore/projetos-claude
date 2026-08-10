"""Baixa/atualiza os bancos GeoLite2-City e GeoLite2-ASN (MaxMind).

City resolve a cidade aproximada do visitante. ASN resolve o provedor/rede do
IP -- usado para detectar trafego de datacenter/hosting (Google Cloud, AWS,
Azure, OVH etc.), que nunca e cliente real de loja de roupa.

Nao guarda IP bruto em lugar nenhum: o .mmdb fica local no servidor e a
resolucao acontece em memoria no momento da requisicao (ver services.py).

Requer MAXMIND_ACCOUNT_ID e MAXMIND_LICENSE_KEY no .env (cadastro gratuito em
maxmind.com/en/geolite2/signup). Licenca gratuita permite atualizacao mensal.

Exemplo (cron mensal):
  python manage.py sincronizar_geoip --settings=core.settings.production
"""

import io
import tarfile

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

EDICOES = {
    'City': {
        'url': 'https://download.maxmind.com/geoip/databases/GeoLite2-City/download?suffix=tar.gz',
        'destino_setting': 'GEOIP_DB_PATH',
    },
    'ASN': {
        'url': 'https://download.maxmind.com/geoip/databases/GeoLite2-ASN/download?suffix=tar.gz',
        'destino_setting': 'GEOIP_ASN_DB_PATH',
    },
}


class Command(BaseCommand):
    help = 'Baixa/atualiza os bancos GeoLite2-City.mmdb e GeoLite2-ASN.mmdb da MaxMind'

    def handle(self, *args, **options):
        account_id = settings.MAXMIND_ACCOUNT_ID
        license_key = settings.MAXMIND_LICENSE_KEY
        if not account_id or not license_key:
            raise CommandError(
                'MAXMIND_ACCOUNT_ID / MAXMIND_LICENSE_KEY nao configurados no .env'
            )

        for nome, cfg in EDICOES.items():
            destino = getattr(settings, cfg['destino_setting'])
            destino.parent.mkdir(parents=True, exist_ok=True)

            self.stdout.write(f'Baixando GeoLite2-{nome} da MaxMind...')
            resp = requests.get(cfg['url'], auth=(account_id, license_key), timeout=60)
            resp.raise_for_status()

            with tarfile.open(fileobj=io.BytesIO(resp.content), mode='r:gz') as tar:
                membro_mmdb = next(
                    (m for m in tar.getmembers() if m.name.endswith('.mmdb')), None
                )
                if not membro_mmdb:
                    raise CommandError(f'Nenhum arquivo .mmdb encontrado no pacote GeoLite2-{nome}')

                extraido = tar.extractfile(membro_mmdb)
                conteudo = extraido.read()

            # Escrita atomica: grava em arquivo temporario e renomeia por cima do
            # atual, para nunca deixar o Reader (em memoria nos workers) apontando
            # para um arquivo parcialmente escrito.
            tmp = destino.with_suffix('.mmdb.tmp')
            tmp.write_bytes(conteudo)
            tmp.replace(destino)

            self.stdout.write(self.style.SUCCESS(
                f'GeoLite2-{nome}.mmdb atualizado ({len(conteudo) / 1024 / 1024:.1f} MB) em {destino}'
            ))
