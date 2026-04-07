"""
Motor de sorteio da Liga Quarta Scaff.

Gera 4 rodadas internas por dia onde:
- Cada jogador joga exatamente 4 partidas
- Nenhum jogador repete parceiro ou adversário no mesmo dia  (regra obrigatória)
- Minimiza repetições dos últimos N sorteios históricos      (regra soft / melhor esforço)
- Suporta 16, 20, 24, 28 e 32 jogadores
"""

import random
from typing import Optional

# Tipo: lista de rodadas internas, cada uma com lista de matches
# match = ((j1_id, j2_id), (j3_id, j4_id))
Rodada = list[tuple[tuple[int, int], tuple[int, int]]]
Sorteio = list[Rodada]


def _tentar_rodada(
    jogadores: list[int],
    parceiros_usados: dict[int, set[int]],
    adversarios_usados: dict[int, set[int]],
) -> Optional[Rodada]:
    """
    Tenta montar uma rodada interna sem violar restrições obrigatórias (mesmo dia).
    Usa backtracking simples com embaralhamento.
    Retorna None se impossível.
    """
    n = len(jogadores)
    n_quadras = n // 4
    disponiveis = jogadores.copy()
    random.shuffle(disponiveis)
    matches: Rodada = []

    def backtrack(idx: int, restantes: list[int]) -> bool:
        if idx == n_quadras:
            return True

        for i in range(len(restantes)):
            for j in range(i + 1, len(restantes)):
                for k in range(len(restantes)):
                    if k in (i, j):
                        continue
                    for l in range(k + 1, len(restantes)):
                        if l in (i, j):
                            continue
                        j1, j2, j3, j4 = restantes[i], restantes[j], restantes[k], restantes[l]

                        if j2 in parceiros_usados[j1] or j1 in parceiros_usados[j2]:
                            continue
                        if j4 in parceiros_usados[j3] or j3 in parceiros_usados[j4]:
                            continue
                        if j3 in adversarios_usados[j1] or j4 in adversarios_usados[j1]:
                            continue
                        if j3 in adversarios_usados[j2] or j4 in adversarios_usados[j2]:
                            continue
                        if j1 in adversarios_usados[j3] or j2 in adversarios_usados[j3]:
                            continue
                        if j1 in adversarios_usados[j4] or j2 in adversarios_usados[j4]:
                            continue

                        novos_restantes = [
                            p for idx2, p in enumerate(restantes)
                            if idx2 not in (i, j, k, l)
                        ]
                        matches.append(((j1, j2), (j3, j4)))
                        if backtrack(idx + 1, novos_restantes):
                            return True
                        matches.pop()

        return False

    if backtrack(0, disponiveis):
        return matches
    return None


def _score_historico(
    sorteio: Sorteio,
    hist_parceiros: dict[int, set[int]],
    hist_adversarios: dict[int, set[int]],
) -> int:
    """
    Pontuação de repetição histórica (menor = melhor).
    Repetição de parceiro vale 2 pontos; repetição de adversário vale 1.
    """
    score = 0
    for rodada in sorteio:
        for (j1, j2), (j3, j4) in rodada:
            if j2 in hist_parceiros.get(j1, set()):
                score += 2
            if j4 in hist_parceiros.get(j3, set()):
                score += 2
            for p in (j1, j2):
                if j3 in hist_adversarios.get(p, set()):
                    score += 1
                if j4 in hist_adversarios.get(p, set()):
                    score += 1
    return score


def gerar_sorteio(
    jogadores: list[int],
    historico_jogos: list[dict] | None = None,
    max_tentativas: int = 2000,
) -> Sorteio:
    """
    Gera um sorteio completo para o dia (4 rodadas internas).

    Args:
        jogadores:       lista de IDs dos jogadores confirmados (múltiplo de 4)
        historico_jogos: jogos dos últimos N sorteios concluídos (dicts com
                         dupla1_j1, dupla1_j2, dupla2_j1, dupla2_j2).
                         Usado como restrição soft para minimizar repetições.
        max_tentativas:  número máximo de tentativas completas

    Returns:
        Lista de 4 rodadas, cada uma com N/4 matches

    Raises:
        ValueError: se não conseguir gerar em max_tentativas tentativas
    """
    n = len(jogadores)
    if n < 4 or n % 4 != 0:
        raise ValueError(f"Número de jogadores ({n}) deve ser múltiplo de 4 e >= 4")

    # ── Constrói histórico de pares (restrição soft) ───────────────────────────
    hist_p: dict[int, set[int]] = {}
    hist_a: dict[int, set[int]] = {}

    if historico_jogos:
        for jogo in historico_jogos:
            j1 = jogo.get("dupla1_j1")
            j2 = jogo.get("dupla1_j2")
            j3 = jogo.get("dupla2_j1")
            j4 = jogo.get("dupla2_j2")
            if not all(x is not None for x in (j1, j2, j3, j4)):
                continue
            hist_p.setdefault(j1, set()).add(j2)
            hist_p.setdefault(j2, set()).add(j1)
            hist_p.setdefault(j3, set()).add(j4)
            hist_p.setdefault(j4, set()).add(j3)
            for p in (j1, j2):
                hist_a.setdefault(p, set()).add(j3)
                hist_a.setdefault(p, set()).add(j4)
            for p in (j3, j4):
                hist_a.setdefault(p, set()).add(j1)
                hist_a.setdefault(p, set()).add(j2)

    usar_historico = bool(hist_p)

    # ── Loop de tentativas ─────────────────────────────────────────────────────
    best_sorteio: Sorteio | None = None
    best_score: int = 999_999
    validos_encontrados: int = 0

    for _ in range(max_tentativas):
        random.shuffle(jogadores)
        parceiros: dict[int, set[int]] = {j: set() for j in jogadores}
        adversarios: dict[int, set[int]] = {j: set() for j in jogadores}
        sorteio: Sorteio = []
        falhou = False

        for _ in range(4):
            rodada = _tentar_rodada(jogadores, parceiros, adversarios)
            if rodada is None:
                falhou = True
                break

            for (j1, j2), (j3, j4) in rodada:
                parceiros[j1].add(j2); parceiros[j2].add(j1)
                parceiros[j3].add(j4); parceiros[j4].add(j3)
                for p in (j1, j2):
                    adversarios[p].add(j3); adversarios[p].add(j4)
                for p in (j3, j4):
                    adversarios[p].add(j1); adversarios[p].add(j2)

            sorteio.append(rodada)

        if falhou:
            continue

        # Sem histórico: retorna a primeira solução válida (comportamento original)
        if not usar_historico:
            return sorteio

        # Com histórico: pontua e guarda o melhor
        sc = _score_historico(sorteio, hist_p, hist_a)
        if sc < best_score:
            best_score = sc
            best_sorteio = sorteio

        validos_encontrados += 1

        # Sai cedo se encontrou solução perfeita ou avaliou 150 soluções válidas
        if best_score == 0 or validos_encontrados >= 150:
            return best_sorteio

    if best_sorteio:
        return best_sorteio

    raise ValueError(
        f"Não foi possível gerar sorteio válido após {max_tentativas} tentativas. "
        "Verifique se o número de jogadores é compatível."
    )


def validar_sorteio(sorteio: Sorteio, jogadores: list[int]) -> list[str]:
    """
    Valida um sorteio gerado e retorna lista de violações encontradas.
    Lista vazia = sorteio válido.
    """
    erros: list[str] = []
    parceiros: dict[int, set[int]] = {j: set() for j in jogadores}
    adversarios: dict[int, set[int]] = {j: set() for j in jogadores}
    jogos_por_jogador: dict[int, int] = {j: 0 for j in jogadores}

    for r_idx, rodada in enumerate(sorteio):
        jogando_agora: set[int] = set()
        for (j1, j2), (j3, j4) in rodada:
            for j in (j1, j2, j3, j4):
                if j in jogando_agora:
                    erros.append(f"Rodada {r_idx+1}: jogador {j} aparece em mais de uma quadra")
                jogando_agora.add(j)
                jogos_por_jogador[j] += 1

            if j2 in parceiros[j1]:
                erros.append(f"Rodada {r_idx+1}: dupla {j1}/{j2} já jogou juntos")
            if j4 in parceiros[j3]:
                erros.append(f"Rodada {r_idx+1}: dupla {j3}/{j4} já jogou juntos")
            for p in (j1, j2):
                if j3 in adversarios[p] or j4 in adversarios[p]:
                    erros.append(f"Rodada {r_idx+1}: {p} já enfrentou {j3} ou {j4}")

            parceiros[j1].add(j2); parceiros[j2].add(j1)
            parceiros[j3].add(j4); parceiros[j4].add(j3)
            for p in (j1, j2):
                adversarios[p].add(j3); adversarios[p].add(j4)
            for p in (j3, j4):
                adversarios[p].add(j1); adversarios[p].add(j2)

    for j, n in jogos_por_jogador.items():
        if n != 4:
            erros.append(f"Jogador {j} jogou {n} jogos (esperado 4)")

    return erros


def sorteio_para_tabela(
    sorteio: Sorteio, nomes: dict[int, str]
) -> list[dict]:
    """
    Converte sorteio para lista de dicts para exibição/persistência.

    Retorna lista de dicts com:
    - rodada_interna: 1-4
    - quadra: número da quadra
    - dupla1: "Nome1 / Nome2"
    - dupla2: "Nome3 / Nome4"
    - dupla1_j1, dupla1_j2, dupla2_j1, dupla2_j2: IDs
    """
    resultado = []
    for rodada_idx, rodada in enumerate(sorteio, start=1):
        for quadra_idx, ((j1, j2), (j3, j4)) in enumerate(rodada, start=1):
            resultado.append({
                "rodada_interna": rodada_idx,
                "quadra": quadra_idx,
                "dupla1": f"{nomes.get(j1, str(j1))} / {nomes.get(j2, str(j2))}",
                "dupla2": f"{nomes.get(j3, str(j3))} / {nomes.get(j4, str(j4))}",
                "dupla1_j1": j1,
                "dupla1_j2": j2,
                "dupla2_j1": j3,
                "dupla2_j2": j4,
            })
    return resultado
