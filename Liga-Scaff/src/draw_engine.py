"""
Motor de sorteio da Liga Quarta Scaff.

Gera 4 rodadas internas por dia onde:
- Cada jogador joga exatamente 4 partidas
- Nenhum jogador repete parceiro ou adversário no mesmo dia  (regra 1 — obrigatória)
- Evita ao máximo que alguém jogue junto e contra a mesma pessoa na mesma noite
  (regra 2 — soft, prioridade alta)
- Minimiza repetições dos últimos N sorteios históricos               (regra 3 — soft)
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
    adversarios_noite: dict[int, set[int]] | None = None,
) -> Optional[Rodada]:
    """
    Tenta montar uma rodada interna sem violar restrições obrigatórias (mesmo dia).
    Usa backtracking com dois passes:
      1. Passa estrita: tenta formar duplas que NÃO sejam adversários desta noite
         (minimiza violações da regra 2).
      2. Passe relaxado: se a passagem estrita falhar, aceita qualquer combinação
         válida pela regra 1 (comportamento original).
    Retorna None se impossível mesmo no passe relaxado.
    """
    n = len(jogadores)
    n_quadras = n // 4
    disponiveis = jogadores.copy()
    random.shuffle(disponiveis)
    matches: Rodada = []

    def _viola_r2(j1: int, j2: int, j3: int, j4: int) -> bool:
        """True se esta combinação criaria uma violação da regra 2."""
        if adversarios_noite is None:
            return False
        # 2b: parceiro novo já foi adversário
        if j2 in adversarios_noite.get(j1, set()):
            return True
        if j4 in adversarios_noite.get(j3, set()):
            return True
        # 2a: adversário novo já foi parceiro
        for p1, p2 in [(j1, j3), (j1, j4), (j2, j3), (j2, j4)]:
            if p2 in parceiros_usados.get(p1, set()):
                return True
        return False

    # Contador de nós explorados no passe estrito
    # Limita a busca estrita para garantir tempo máximo razoável
    _strict_budget = [5_000]

    def backtrack(idx: int, restantes: list[int], strict: bool) -> bool:
        if idx == n_quadras:
            return True

        for i in range(len(restantes)):
            for j in range(i + 1, len(restantes)):
                j1, j2 = restantes[i], restantes[j]
                if j2 in parceiros_usados[j1]:
                    continue
                for k in range(len(restantes)):
                    if k in (i, j):
                        continue
                    for l in range(k + 1, len(restantes)):
                        if l in (i, j):
                            continue
                        j3, j4 = restantes[k], restantes[l]

                        if j4 in parceiros_usados[j3]:
                            continue
                        if j3 in adversarios_usados[j1] or j4 in adversarios_usados[j1]:
                            continue
                        if j3 in adversarios_usados[j2] or j4 in adversarios_usados[j2]:
                            continue
                        if j1 in adversarios_usados[j3] or j2 in adversarios_usados[j3]:
                            continue
                        if j1 in adversarios_usados[j4] or j2 in adversarios_usados[j4]:
                            continue

                        if strict:
                            _strict_budget[0] -= 1
                            if _strict_budget[0] <= 0:
                                return False  # esgotou budget — cai no passe relaxado
                            if _viola_r2(j1, j2, j3, j4):
                                continue

                        novos_restantes = [
                            p for idx2, p in enumerate(restantes)
                            if idx2 not in (i, j, k, l)
                        ]
                        matches.append(((j1, j2), (j3, j4)))
                        if backtrack(idx + 1, novos_restantes, strict):
                            return True
                        matches.pop()

        return False

    # Passe 1: tenta sem violar regra 2 (strict=True, budget limitado)
    if adversarios_noite and backtrack(0, disponiveis, strict=True):
        return matches

    # Passe 2: fallback — aceita violações se necessário
    matches.clear()
    if backtrack(0, disponiveis, strict=False):
        return matches

    return None


def _score_sorteio(
    sorteio: Sorteio,
    hist_parceiros: dict[int, set[int]],
    hist_adversarios: dict[int, set[int]],
) -> tuple[int, int]:
    """
    Pontua um sorteio gerado.
    Retorna (score_r2, score_historico) onde menor = melhor.

    score_r2:   violações da regra 2 — jogador joga JUNTO e CONTRA a mesma
                pessoa na mesma noite (em qualquer ordem):
                  2a) adversário desta rodada foi parceiro em rodada anterior
                  2b) parceiro desta rodada foi adversário em rodada anterior
                Cada par único (A, B) conta no máximo 1 violação por noite.
    score_hist: repetições históricas dos últimos N sorteios
                (parceiro repetido = 2 pts, adversário = 1 pt).

    A comparação é feita como tupla: (score_r2, score_hist),
    garantindo que a regra 2 sempre tem prioridade sobre o histórico.
    """
    todos_jogadores: set[int] = set()
    for rodada in sorteio:
        for (j1, j2), (j3, j4) in rodada:
            todos_jogadores.update((j1, j2, j3, j4))

    # Acumula parceiros E adversários da noite rodada a rodada
    parceiros_acum: dict[int, set[int]] = {j: set() for j in todos_jogadores}
    adversarios_acum: dict[int, set[int]] = {j: set() for j in todos_jogadores}
    # Conta violações por pessoa (para minimizar quem acumula mais de 1)
    viols_por_pessoa: dict[int, int] = {j: 0 for j in todos_jogadores}

    score_r2 = 0
    score_hist = 0

    for rodada in sorteio:
        for (j1, j2), (j3, j4) in rodada:
            # Regra 2a: adversário desta rodada já foi parceiro nesta noite?
            for p1, p2 in [(j1, j3), (j1, j4), (j2, j3), (j2, j4)]:
                if p2 in parceiros_acum[p1]:
                    score_r2 += 1
                    viols_por_pessoa[p1] += 1
                    viols_por_pessoa[p2] += 1

            # Regra 2b: parceiro desta rodada já foi adversário nesta noite?
            # (regra 1 garante que cada par só pode ser parceiro ou adversário
            #  uma vez por noite, então não há dupla-contagem entre 2a e 2b)
            if j2 in adversarios_acum[j1]:
                score_r2 += 1
                viols_por_pessoa[j1] += 1
                viols_por_pessoa[j2] += 1
            if j4 in adversarios_acum[j3]:
                score_r2 += 1
                viols_por_pessoa[j3] += 1
                viols_por_pessoa[j4] += 1

            # Regra 3: repetição histórica
            if j2 in hist_parceiros.get(j1, set()):
                score_hist += 2
            if j4 in hist_parceiros.get(j3, set()):
                score_hist += 2
            for p in (j1, j2):
                if j3 in hist_adversarios.get(p, set()):
                    score_hist += 1
                if j4 in hist_adversarios.get(p, set()):
                    score_hist += 1

            # Atualiza acumulados da noite
            parceiros_acum[j1].add(j2);  parceiros_acum[j2].add(j1)
            parceiros_acum[j3].add(j4);  parceiros_acum[j4].add(j3)
            for p in (j1, j2):
                adversarios_acum[p].add(j3); adversarios_acum[p].add(j4)
            for p in (j3, j4):
                adversarios_acum[p].add(j1); adversarios_acum[p].add(j2)

    # Penalidade extra para quem acumula 2+ violações na mesma noite
    # (incentiva distribuição mais uniforme: cada pessoa com máx. 1 violação)
    max_por_pessoa = max(viols_por_pessoa.values()) if viols_por_pessoa else 0
    score_r2_distrib = score_r2 * 100 + max_por_pessoa

    return score_r2_distrib, score_hist


def gerar_sorteio(
    jogadores: list[int],
    historico_jogos: list[dict] | None = None,
    max_tentativas: int = 2000,
) -> Sorteio:
    """
    Gera um sorteio completo para o dia (4 rodadas internas).

    Prioridade das regras:
      1. [Obrigatória] Nenhum jogador repete parceiro ou adversário na mesma noite.
      2. [Soft - alta] Ninguém enfrenta alguém que foi seu parceiro na mesma noite.
      3. [Soft - normal] Minimiza repetições de parceiros/adversários das últimas
         N rodadas históricas.

    Args:
        jogadores:       lista de IDs dos jogadores confirmados (múltiplo de 4)
        historico_jogos: jogos dos últimos N sorteios concluídos (dicts com
                         dupla1_j1, dupla1_j2, dupla2_j1, dupla2_j2).
                         Usado para minimizar repetições históricas (regra 3).
        max_tentativas:  número máximo de tentativas completas

    Returns:
        Lista de 4 rodadas, cada uma com N/4 matches

    Raises:
        ValueError: se não conseguir gerar em max_tentativas tentativas
    """
    n = len(jogadores)
    if n < 4 or n % 4 != 0:
        raise ValueError(f"Número de jogadores ({n}) deve ser múltiplo de 4 e >= 4")

    # ── Constrói histórico de pares (regra 3) ─────────────────────────────────
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

    # ── Loop de tentativas ────────────────────────────────────────────────────
    best_sorteio: Sorteio | None = None
    best_r2: int = 999_999
    best_hist: int = 999_999
    validos_encontrados: int = 0

    for _ in range(max_tentativas):
        random.shuffle(jogadores)
        parceiros: dict[int, set[int]] = {j: set() for j in jogadores}
        adversarios: dict[int, set[int]] = {j: set() for j in jogadores}
        sorteio: Sorteio = []
        falhou = False

        # adversarios_noite: acumula quem já foi adversário na noite atual
        # (passado como dica para o backtracking evitar parcerias conflitantes)
        adversarios_noite: dict[int, set[int]] = {j: set() for j in jogadores}

        for _ in range(4):
            rodada = _tentar_rodada(jogadores, parceiros, adversarios, adversarios_noite)
            if rodada is None:
                falhou = True
                break

            for (j1, j2), (j3, j4) in rodada:
                parceiros[j1].add(j2); parceiros[j2].add(j1)
                parceiros[j3].add(j4); parceiros[j4].add(j3)
                for p in (j1, j2):
                    adversarios[p].add(j3); adversarios[p].add(j4)
                    adversarios_noite[p].add(j3); adversarios_noite[p].add(j4)
                for p in (j3, j4):
                    adversarios[p].add(j1); adversarios[p].add(j2)
                    adversarios_noite[p].add(j1); adversarios_noite[p].add(j2)

            sorteio.append(rodada)

        if falhou:
            continue

        # Pontua pelas regras 2 e 3 (menor = melhor)
        sc_r2, sc_hist = _score_sorteio(sorteio, hist_p, hist_a)

        # Atualiza melhor sorteio (tupla garante prioridade da regra 2)
        if (sc_r2, sc_hist) < (best_r2, best_hist):
            best_r2 = sc_r2
            best_hist = sc_hist
            best_sorteio = sorteio

        validos_encontrados += 1

        # Sai cedo se encontrou solução perfeita ou avaliou 500 soluções válidas
        if (best_r2 == 0 and best_hist == 0) or validos_encontrados >= 500:
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
