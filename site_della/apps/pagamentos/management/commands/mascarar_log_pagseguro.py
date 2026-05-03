import json
from pathlib import Path

from django.core.management.base import BaseCommand


def _mask_email(value: str) -> str:
    if not value or '@' not in value:
        return value
    user, domain = value.split('@', 1)
    if len(user) <= 2:
        masked_user = user[:1] + '*' * max(0, len(user) - 1)
    else:
        masked_user = user[:2] + '*' * (len(user) - 2)
    return f'{masked_user}@{domain}'


def _mask_digits(value: str, keep_start: int = 3, keep_end: int = 2) -> str:
    if not value:
        return value
    chars = list(value)
    digit_positions = [i for i, ch in enumerate(chars) if ch.isdigit()]
    visible = set(digit_positions[:keep_start] + digit_positions[-keep_end:])
    for i in digit_positions:
        if i not in visible:
            chars[i] = '*'
    return ''.join(chars)


def _mask_name(value: str) -> str:
    if not value:
        return value
    parts = value.split()
    masked = []
    for part in parts:
        if len(part) <= 1:
            masked.append(part)
        else:
            masked.append(part[0] + '*' * (len(part) - 1))
    return ' '.join(masked)


def _mask_address(value: str) -> str:
    if not value:
        return value
    parts = value.split()
    masked = []
    for part in parts:
        if len(part) <= 2:
            masked.append(part[0] + '*' * max(0, len(part) - 1))
        else:
            masked.append(part[:2] + '*' * (len(part) - 2))
    return ' '.join(masked)


def _walk(obj):
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            lowered = key.lower()
            if isinstance(value, str):
                if lowered == 'email':
                    out[key] = _mask_email(value)
                    continue
                if lowered in {'tax_id', 'cpf', 'cpj', 'cnpj'}:
                    out[key] = _mask_digits(value, keep_start=3, keep_end=2)
                    continue
                if lowered in {'number'} and len(''.join(c for c in value if c.isdigit())) >= 8:
                    out[key] = _mask_digits(value, keep_start=2, keep_end=2)
                    continue
                if lowered in {'street', 'locality', 'city', 'complement', 'postal_code'}:
                    out[key] = _mask_address(value)
                    continue
                if lowered == 'name':
                    out[key] = _mask_name(value)
                    continue
            out[key] = _walk(value)
        return out
    if isinstance(obj, list):
        return [_walk(item) for item in obj]
    return obj


class Command(BaseCommand):
    help = 'Cria uma cópia mascarada de um log JSON do PagSeguro para envio ao suporte.'

    def add_arguments(self, parser):
        parser.add_argument('arquivo_origem', help='Caminho do JSON original.')
        parser.add_argument(
            '--arquivo',
            default='',
            help='Caminho opcional do JSON mascarado. Padrão: mesmo nome com sufixo _masked.',
        )

    def handle(self, *args, **options):
        origem = Path(options['arquivo_origem']).expanduser()
        if not origem.exists():
            self.stderr.write(self.style.ERROR(f'Arquivo não encontrado: {origem}'))
            return

        data = json.loads(origem.read_text(encoding='utf-8'))
        masked = _walk(data)

        destino_opt = options['arquivo'].strip()
        destino = Path(destino_opt).expanduser() if destino_opt else origem.with_name(f'{origem.stem}_masked{origem.suffix}')
        destino.write_text(json.dumps(masked, ensure_ascii=False, indent=2), encoding='utf-8')

        self.stdout.write(self.style.SUCCESS(f'Log mascarado salvo em: {destino}'))
