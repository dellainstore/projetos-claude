"""
Aplica mascaramento de PII em logs JSON do PagSeguro/PagBank para envio ao
suporte (homologação). Gera <arquivo>_masked.json e <arquivo>_masked.txt
preservando o nome original.

Uso:
    python scripts/mascarar_logs_pagseguro.py logs/pagseguro_cartao_2026-0001.json [outro.json ...]
"""
import json
import re
import sys
from pathlib import Path


def _mask_palavra(palavra: str) -> str:
    if len(palavra) <= 1:
        return palavra
    return palavra[0] + '*' * (len(palavra) - 1)


def _mask_palavra_2(palavra: str) -> str:
    if len(palavra) <= 2:
        return palavra
    return palavra[:2] + '*' * (len(palavra) - 2)


def mascarar_nome(valor: str) -> str:
    return ' '.join(_mask_palavra(p) for p in valor.split(' '))


def mascarar_endereco(valor: str) -> str:
    return ' '.join(_mask_palavra_2(p) for p in valor.split(' '))


def mascarar_email(valor: str) -> str:
    if '@' not in valor:
        return valor
    prefixo, dominio = valor.split('@', 1)
    if len(prefixo) <= 2:
        return prefixo + '@' + dominio
    return prefixo[:2] + '*' * (len(prefixo) - 2) + '@' + dominio


def mascarar_cpf(valor: str) -> str:
    digits = re.sub(r'\D', '', valor)
    if len(digits) < 5:
        return valor
    return digits[:3] + '*' * (len(digits) - 5) + digits[-2:]


def mascarar_telefone(valor: str) -> str:
    digits = re.sub(r'\D', '', valor)
    if len(digits) < 4:
        return valor
    return digits[:2] + '*' * (len(digits) - 4) + digits[-2:]


def mascarar_cep(valor: str) -> str:
    digits = re.sub(r'\D', '', valor)
    if len(digits) < 2:
        return valor
    return digits[:2] + '*' * (len(digits) - 2)


CAMPOS = {
    'name':        mascarar_nome,
    'email':       mascarar_email,
    'tax_id':      mascarar_cpf,
    'number':      mascarar_telefone,
    'street':      mascarar_endereco,
    'complement':  mascarar_endereco,
    'locality':    mascarar_endereco,
    'city':        mascarar_endereco,
    'postal_code': mascarar_cep,
}


def aplicar_mascaramento(obj):
    if isinstance(obj, dict):
        return {k: (CAMPOS[k](v) if k in CAMPOS and isinstance(v, str) else aplicar_mascaramento(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [aplicar_mascaramento(it) for it in obj]
    return obj


def main(argv):
    if not argv:
        print('Uso: mascarar_logs_pagseguro.py <arquivo.json> [outros...]')
        sys.exit(1)

    for caminho in argv:
        origem = Path(caminho)
        if not origem.exists():
            print(f'[skip] {origem} não existe')
            continue

        dados = json.loads(origem.read_text(encoding='utf-8'))
        mascarado = aplicar_mascaramento(dados)
        conteudo = json.dumps(mascarado, ensure_ascii=False, indent=2)

        destino_json = origem.with_name(origem.stem + '_masked.json')
        destino_txt  = origem.with_name(origem.stem + '_masked.txt')
        destino_json.write_text(conteudo, encoding='utf-8')
        destino_txt.write_text(conteudo, encoding='utf-8')

        print(f'OK {origem.name} → {destino_json.name} + {destino_txt.name}')


if __name__ == '__main__':
    main(sys.argv[1:])
