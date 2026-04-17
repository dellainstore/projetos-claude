"""
Utilitários gerais da Liga Quarta Scaff.
"""

import re
import unicodedata
from datetime import datetime


def _normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculas para comparação tolerante."""
    sem_acento = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return sem_acento.lower().strip()


def fmt_data(data_str: str) -> str:
    """Converte data de YYYY-MM-DD para DD/MM/YYYY."""
    try:
        return datetime.strptime(str(data_str), "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(data_str)


def parse_lista_whatsapp(texto: str, jogadores: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Extrai nomes de uma lista colada do WhatsApp e faz match com jogadores cadastrados.

    Suporta formatos:
        1 - Fulano
        2- Ciclano
        - Fulano
        • Fulano
        Fulano

    Args:
        texto: texto colado da lista do WhatsApp
        jogadores: lista de dicts com 'id' e 'nome' dos jogadores cadastrados

    Returns:
        (encontrados, nao_encontrados)
        - encontrados: lista de dicts de jogadores que bateram
        - nao_encontrados: lista de nomes que não tiveram match
    """
    # Mapa nome_normalizado -> jogador para busca tolerante a acentos e maiúsculas
    mapa_nomes = {_normalizar(j["nome"]): j for j in jogadores}

    encontrados: list[dict] = []
    nao_encontrados: list[str] = []
    ids_ja_adicionados: set[int] = set()

    for linha in texto.strip().splitlines():
        linha = linha.strip()
        if not linha:
            continue

        # Remove prefixos numéricos e caracteres de lista:
        # "1 - ", "2- ", "- ", "• ", "1. ", "* ", etc.
        nome = re.sub(r'^[\d\s]*[\.\-–•\*]\s*', '', linha).strip()

        if not nome or len(nome) < 2:
            continue

        match = mapa_nomes.get(_normalizar(nome))
        if match:
            if match["id"] not in ids_ja_adicionados:
                encontrados.append(match)
                ids_ja_adicionados.add(match["id"])
        else:
            nao_encontrados.append(nome)

    return encontrados, nao_encontrados


def validar_nome_jogador(nome: str, jogadores: list[dict]) -> dict | None:
    """
    Retorna o jogador cadastrado cujo nome bate (sem acento, case-insensitive).
    Retorna None se não encontrado.
    """
    nome_norm = _normalizar(nome)
    for j in jogadores:
        if _normalizar(j["nome"]) == nome_norm:
            return j
    return None
