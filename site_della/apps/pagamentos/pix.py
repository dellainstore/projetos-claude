"""
Gerador de QR Code Pix — Padrão EMV QRCPS-MPM (BACEN)
Referência: https://www.bcb.gov.br/content/estabilidadefinanceira/pix/Regulamento_Pix/
"""
import io
import base64
import struct


def _crc16_ccitt(data: str) -> int:
    """CRC-16/CCITT-FALSE conforme especificação EMV."""
    crc = 0xFFFF
    for ch in data.encode('ascii'):
        for _ in range(8):
            bit = (crc ^ (ch << 8)) & 0x8000
            crc = ((crc << 1) & 0xFFFF) ^ (0x1021 if bit else 0)
            ch = (ch << 1) & 0xFF
    return crc


def _campo(id_: str, valor: str) -> str:
    """Formata campo EMV: ID + tamanho 2 dígitos + valor."""
    return f'{id_}{len(valor):02d}{valor}'


def gerar_payload_pix(
    chave: str,
    valor: float,
    nome_recebedor: str,
    cidade: str = 'SAO PAULO',
    txid: str = 'DELLA',
    descricao: str = '',
) -> str:
    """
    Gera o payload texto do Pix Estático conforme padrão EMV.
    O txid é o identificador do pedido (máx. 25 chars, sem espaços).
    """
    # 26 — Merchant Account Information (MAI)
    gui    = _campo('00', 'br.gov.bcb.pix')
    chave_ = _campo('01', chave)
    if descricao:
        desc = _campo('02', descricao[:72])
        mai  = _campo('26', gui + chave_ + desc)
    else:
        mai  = _campo('26', gui + chave_)

    # Campos obrigatórios
    mcc      = _campo('52', '0000')           # Merchant Category Code
    currency = _campo('53', '986')            # BRL
    amount   = _campo('54', f'{valor:.2f}')
    country  = _campo('58', 'BR')

    # Nome: máx 25, sem acentos (simplificado)
    nome_clean = _ascii_safe(nome_recebedor)[:25]
    city_clean = _ascii_safe(cidade)[:15]
    merchant_name = _campo('59', nome_clean)
    merchant_city = _campo('60', city_clean)

    # 62 — Additional Data Field Template
    txid_clean = re.sub(r'[^A-Za-z0-9]', '', txid)[:25] or 'DELLA'
    adf = _campo('62', _campo('05', txid_clean))

    # Monta payload sem CRC
    payload = (
        _campo('00', '01') +
        mai + mcc + currency + amount +
        country + merchant_name + merchant_city + adf +
        '6304'
    )

    crc = _crc16_ccitt(payload)
    return f'{payload}{crc:04X}'


def _ascii_safe(text: str) -> str:
    """Remove acentos e normaliza para ASCII."""
    import unicodedata
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').upper()


def gerar_qrcode_base64(payload: str) -> str:
    """Gera imagem PNG do QR Code e retorna como string base64."""
    import qrcode
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')


import re  # noqa: E402 — import tardio para evitar circularidade
