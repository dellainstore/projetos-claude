"""
Sanitização e validação de todos os inputs de usuário.

Uso:
    from apps.core_utils.sanitize import sanitize_text, sanitize_name, validate_cpf

Aplique em:
- Formulários Django (no método clean_*)
- Serializers DRF (no método validate_*)
- Qualquer campo onde o cliente possa digitar texto livre
"""

import re
import unicodedata
import bleach
from django.core.exceptions import ValidationError


# ─── Configuração do bleach ───────────────────────────────────────────────────
# Define exatamente quais tags HTML são permitidas.
# Em campos de texto simples: NENHUMA tag é permitida.
# Em campos de texto rico (ex: descrição do produto pelo admin): lista restrita.

ALLOWED_TAGS_NONE = []           # sem HTML — texto puro
ALLOWED_TAGS_BASIC = [           # apenas formatação básica (não usado em inputs de cliente)
    'b', 'i', 'em', 'strong', 'br', 'p', 'ul', 'ol', 'li',
]
ALLOWED_ATTRIBUTES = {}          # sem atributos — previne href=javascript:, onerror=, etc.


# ─── Funções de sanitização ───────────────────────────────────────────────────

def sanitize_text(value: str, max_length: int = 500) -> str:
    """
    Sanitiza qualquer texto de entrada livre (comentários, mensagens, endereços).
    - Remove todas as tags HTML
    - Remove caracteres de controle
    - Limita o comprimento
    """
    if not value:
        return ''

    # Remove tags HTML — qualquer tentativa de XSS via <script>, <img onerror=>, etc.
    cleaned = bleach.clean(str(value), tags=ALLOWED_TAGS_NONE, attributes=ALLOWED_ATTRIBUTES, strip=True)

    # Remove caracteres de controle (null byte, backspace, etc.)
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)

    # Normaliza unicode (evita bypass com caracteres homoglífos)
    cleaned = unicodedata.normalize('NFKC', cleaned)

    # Remove espaços extras
    cleaned = ' '.join(cleaned.split())

    # Limita comprimento
    return cleaned[:max_length]


def sanitize_name(value: str) -> str:
    """
    Para campos de nome próprio (cliente, remetente).
    Permite apenas letras, espaços, hífens e apóstrofos.
    """
    if not value:
        return ''

    cleaned = sanitize_text(value, max_length=120)

    # Só permite caracteres válidos em nomes
    cleaned = re.sub(r"[^a-zA-ZÀ-ÿ\s'\-]", '', cleaned)
    cleaned = ' '.join(cleaned.split())

    return cleaned.strip()


def sanitize_address(value: str) -> str:
    """Para campos de endereço — permite letras, números, vírgulas, pontos, hífens."""
    if not value:
        return ''

    cleaned = sanitize_text(value, max_length=200)
    cleaned = re.sub(r'[^a-zA-ZÀ-ÿ0-9\s,.\-/°ºª]', '', cleaned)
    return cleaned.strip()


def sanitize_phone(value: str) -> str:
    """Remove tudo que não é número do telefone."""
    if not value:
        return ''
    return re.sub(r'\D', '', str(value))[:20]


def sanitize_cep(value: str) -> str:
    """CEP: apenas 8 dígitos numéricos."""
    if not value:
        return ''
    digits = re.sub(r'\D', '', str(value))
    if len(digits) != 8:
        raise ValidationError('CEP inválido. Informe 8 dígitos.')
    return digits


def sanitize_cpf(value: str) -> str:
    """Remove formatação do CPF e valida estrutura."""
    if not value:
        return ''
    digits = re.sub(r'\D', '', str(value))
    if len(digits) != 11:
        raise ValidationError('CPF inválido.')
    return digits


def sanitize_cnpj(value: str) -> str:
    """Remove formatação do CNPJ e valida estrutura."""
    if not value:
        return ''
    digits = re.sub(r'\D', '', str(value))
    if len(digits) != 14:
        raise ValidationError('CNPJ inválido.')
    return digits


# ─── Validadores de CPF e CNPJ ───────────────────────────────────────────────

def validate_cpf(cpf: str) -> str:
    """Valida dígitos verificadores do CPF."""
    digits = re.sub(r'\D', '', cpf)

    if len(digits) != 11 or len(set(digits)) == 1:
        raise ValidationError('CPF inválido.')

    def calc_digit(digits, factor):
        total = sum(int(d) * f for d, f in zip(digits, range(factor, 1, -1)))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    d1 = calc_digit(digits[:9], 10)
    d2 = calc_digit(digits[:10], 11)

    if digits[-2:] != f'{d1}{d2}':
        raise ValidationError('CPF inválido.')

    return digits


def validate_cnpj(cnpj: str) -> str:
    """Valida dígitos verificadores do CNPJ."""
    digits = re.sub(r'\D', '', cnpj)

    if len(digits) != 14 or len(set(digits)) == 1:
        raise ValidationError('CNPJ inválido.')

    def calc_digit(digits, weights):
        total = sum(int(d) * w for d, w in zip(digits, weights))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    d1 = calc_digit(digits[:12], w1)
    d2 = calc_digit(digits[:13], w2)

    if digits[-2:] != f'{d1}{d2}':
        raise ValidationError('CNPJ inválido.')

    return digits


# ─── Validador de upload de imagem ───────────────────────────────────────────

def validate_image_upload(image_file):
    """
    Valida arquivos de imagem enviados por clientes ou admin.
    Verifica extensão E magic bytes (assinatura real do arquivo).
    Previne upload de arquivos disfarçados com extensão .jpg mas contendo código.
    """
    from django.conf import settings

    ALLOWED_EXTENSIONS = getattr(settings, 'ALLOWED_IMAGE_EXTENSIONS', ['.jpg', '.jpeg', '.png', '.webp'])
    MAX_SIZE_MB = getattr(settings, 'MAX_UPLOAD_SIZE_MB', 5)

    # Verifica extensão
    ext = '.' + image_file.name.rsplit('.', 1)[-1].lower() if '.' in image_file.name else ''
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f'Formato não permitido. Use: {", ".join(ALLOWED_EXTENSIONS)}')

    # Verifica tamanho
    if image_file.size > MAX_SIZE_MB * 1024 * 1024:
        raise ValidationError(f'Imagem muito grande. Máximo: {MAX_SIZE_MB}MB.')

    # Verifica magic bytes (assinatura real do arquivo)
    image_file.seek(0)
    header = image_file.read(12)
    image_file.seek(0)

    MAGIC_BYTES = {
        b'\xff\xd8\xff': 'jpg',           # JPEG
        b'\x89PNG\r\n\x1a\n': 'png',      # PNG
        b'RIFF': 'webp',                   # WebP (também tem WEBP nos bytes 8-12)
    }

    is_valid = False
    for magic, fmt in MAGIC_BYTES.items():
        if header.startswith(magic):
            if fmt == 'webp' and header[8:12] != b'WEBP':
                continue
            is_valid = True
            break

    if not is_valid:
        raise ValidationError('Arquivo inválido. Envie apenas imagens reais (JPG, PNG ou WebP).')

    return image_file
