"""Mapeamento de IDs de situação Bling → nome legível.

IDs obtidos em Bling Admin → Cadastros → Situações de Pedidos.
"""

ATENDIDO_IDS: dict[int, str] = {
    9:      "Atendido",
    18723:  "Atendido - Site",
    47579:  "Atendido - Anacã",
    102406: "Atendido - Atacado",
    114939: "Atendido - Instagram",
    150640: "Atendido - Londrina",
    446048: "Atendido - Vinhedo",
    446834: "Atacado - Vinhedo",
}

CANCELADO_IDS: dict[int, str] = {
    12: "Cancelado",
}

EM_ABERTO_IDS: dict[int, str] = {
    6: "Em aberto",
}

EM_ANDAMENTO_IDS: dict[int, str] = {
    15:     "Em andamento",
    47881:  "Em andamento - Anacã",
    150639: "Em andamento - Londrina",
    446051: "Em andamento - Vinhedo",
    754756: "Em andamento - Site",
}

PERMUTA_IDS: dict[int, str] = {
    15762:  "Permuta - Show Room",
    102742: "Permuta - Anacã",
    451967: "Permuta - Londrina",
}

OUTROS_IDS: dict[int, str] = {
    18:    "Venda Agenciada",
    21:    "Em digitação",
    24:    "Verificado",
    23087: "Aguardando Pagamento",
    23088: "Aguardando Envio",
}

ALL_IDS: dict[int, str] = {
    **ATENDIDO_IDS,
    **CANCELADO_IDS,
    **EM_ABERTO_IDS,
    **EM_ANDAMENTO_IDS,
    **PERMUTA_IDS,
    **OUTROS_IDS,
}


def situacao_label(situacao_id: int) -> str:
    return ALL_IDS.get(situacao_id, f"Situação ID:{situacao_id}")
