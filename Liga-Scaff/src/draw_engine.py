"""
Motor de sorteio da Liga Quarta Scaff.

Gera 4 rodadas internas por dia onde:
- Cada jogador joga exatamente 4 partidas
- Nenhum jogador repete parceiro ou adversário no mesmo dia  (regra 1 — obrigatória)
- Evita ao máximo que alguém jogue junto e contra a mesma pessoa na mesma noite
  (regra 2 — soft, prioridade alta)
- Minimiza repetições dos últimos N sorteios históricos, priorizando evitar
  repetições da rodada imediatamente anterior                         (regra 3 — soft)
- Suporta 16, 20, 24, 28 e 32 jogadores
"""

import random
import time
from typing import Callable, Optional

# Tipo: lista de rodadas internas, cada uma com lista de matches
# match = ((j1_id, j2_id), (j3_id, j4_id))
Rodada = list[tuple[tuple[int, int], tuple[int, int]]]
Sorteio = list[Rodada]
ProgressCallback = Callable[[dict], None]


def _tentar_rodada(
    jogadores: list[int],
    parceiros_usados: dict[int, set[int]],
    adversarios_usados: dict[int, set[int]],
    parceiros_ultima_rodada: dict[int, set[int]] | None = None,
    adversarios_noite: dict[int, set[int]] | None = None,
) -> Optional[Rodada]:
    """
    Tenta montar uma rodada interna sem violar as restrições obrigatórias.
    Regras hard aplicadas aqui:
      1. Ninguém repete parceiro na mesma noite.
      2. Ninguém repete adversário na mesma noite.
      3. Ninguém joga contra alguém com quem já fez dupla na mesma noite.
      4. Ninguém repete parceiro da rodada oficial imediatamente anterior.
    Retorna None se não encontrar composição válida.
    """
    n = len(jogadores)
    n_quadras = n // 4
    disponiveis = jogadores.copy()
    random.shuffle(disponiveis)
    matches: Rodada = []

    def _viola_regras_hard(j1: int, j2: int, j3: int, j4: int) -> bool:
        """True se esta combinação violar alguma regra obrigatória."""
        if parceiros_ultima_rodada is not None:
            if j2 in parceiros_ultima_rodada.get(j1, set()):
                return True
            if j4 in parceiros_ultima_rodada.get(j3, set()):
                return True
        if adversarios_noite is None:
            return False
        # Parceiro novo já foi adversário nesta noite.
        if j2 in adversarios_noite.get(j1, set()):
            return True
        if j4 in adversarios_noite.get(j3, set()):
            return True
        # Adversário novo já foi parceiro nesta noite.
        for p1, p2 in [(j1, j3), (j1, j4), (j2, j3), (j2, j4)]:
            if p2 in parceiros_usados.get(p1, set()):
                return True
        return False

    def backtrack(idx: int, restantes: list[int]) -> bool:
        if idx == n_quadras:
            return True

        for i in range(len(restantes)):
            for j in range(i + 1, len(restantes)):
                j1, j2 = restantes[i], restantes[j]
                if j2 in parceiros_usados[j1]:
                    continue
                if parceiros_ultima_rodada is not None and j2 in parceiros_ultima_rodada.get(j1, set()):
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

                        if _viola_regras_hard(j1, j2, j3, j4):
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


def _score_sorteio(
    sorteio: Sorteio,
    hist_parceiros: dict[int, dict[int, int]],
    hist_adversarios: dict[int, dict[int, int]],
) -> tuple[int, int]:
    """
    Pontua um sorteio gerado.
    Retorna (score_r2, score_historico) onde menor = melhor.

    score_r2:   legado de compatibilidade. Como as regras da mesma noite agora
                são obrigatórias, este score tende a zero.
    score_hist: repetições históricas dos últimos N sorteios.
                Como parceiro da rodada anterior virou regra hard, o histórico
                passa a atuar principalmente na redução de adversários repetidos.

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
            # Mantido por compatibilidade, embora agora deva ficar zerado.
            for p1, p2 in [(j1, j3), (j1, j4), (j2, j3), (j2, j4)]:
                if p2 in parceiros_acum[p1]:
                    score_r2 += 1
                    viols_por_pessoa[p1] += 1
                    viols_por_pessoa[p2] += 1

            # Mantido por compatibilidade, embora agora deva ficar zerado.
            if j2 in adversarios_acum[j1]:
                score_r2 += 1
                viols_por_pessoa[j1] += 1
                viols_por_pessoa[j2] += 1
            if j4 in adversarios_acum[j3]:
                score_r2 += 1
                viols_por_pessoa[j3] += 1
                viols_por_pessoa[j4] += 1

            # Regra 3: repetição histórica
            score_hist += hist_parceiros.get(j1, {}).get(j2, 0)
            score_hist += hist_parceiros.get(j3, {}).get(j4, 0)
            for p in (j1, j2):
                score_hist += hist_adversarios.get(p, {}).get(j3, 0)
                score_hist += hist_adversarios.get(p, {}).get(j4, 0)

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
    max_tentativas: int = 10000,
    progress_callback: ProgressCallback | None = None,
) -> Sorteio:
    """
    Gera um sorteio completo para o dia (4 rodadas internas).

    Prioridade das regras:
      1. [Obrigatória] Nenhum jogador repete parceiro ou adversário na mesma noite.
      2. [Obrigatória] Ninguém repete parceiro da rodada oficial imediatamente anterior.
      3. [Soft - alta] Minimiza repetições de adversários da rodada anterior.
      4. [Soft - normal] Minimiza repetições históricas remanescentes.

    Args:
        jogadores:       lista de IDs dos jogadores confirmados (múltiplo de 4)
        historico_jogos: jogos dos últimos N sorteios concluídos (dicts com
                         dupla1_j1, dupla1_j2, dupla2_j1, dupla2_j2).
                         Usado para bloquear parceiros da última rodada e
                         minimizar repetições históricas remanescentes.
        max_tentativas:  número máximo de tentativas completas

    Returns:
        Lista de 4 rodadas, cada uma com N/4 matches

    Raises:
        ValueError: se não conseguir gerar em max_tentativas tentativas
    """
    n = len(jogadores)
    if n < 4 or n % 4 != 0:
        raise ValueError(f"Número de jogadores ({n}) deve ser múltiplo de 4 e >= 4")

    # ── Constrói histórico de pares ────────────────────────────────────────────
    hist_p: dict[int, dict[int, int]] = {}
    hist_a: dict[int, dict[int, int]] = {}
    parceiros_ultima_rodada: dict[int, set[int]] = {}

    def _peso_historico(jogo: dict) -> tuple[int, int]:
        # A última rodada concluída pesa mais do que a penúltima.
        rodada_num = jogo.get("rodada_numero")
        if rodada_num is None:
            return 0, 5
        rodada_nums = [j.get("rodada_numero") for j in historico_jogos or [] if j.get("rodada_numero") is not None]
        ordem = list(dict.fromkeys(rodada_nums))
        idx = ordem.index(rodada_num) if rodada_num in ordem else None
        if idx == 0:
            return 0, 40
        return 60, 10

    rodada_nums_hist = [j.get("rodada_numero") for j in historico_jogos or [] if j.get("rodada_numero") is not None]
    ordem_rodadas_hist = list(dict.fromkeys(rodada_nums_hist))

    if historico_jogos:
        for jogo in historico_jogos:
            j1 = jogo.get("dupla1_j1")
            j2 = jogo.get("dupla1_j2")
            j3 = jogo.get("dupla2_j1")
            j4 = jogo.get("dupla2_j2")
            if not all(x is not None for x in (j1, j2, j3, j4)):
                continue
            rodada_num = jogo.get("rodada_numero")
            idx = ordem_rodadas_hist.index(rodada_num) if rodada_num in ordem_rodadas_hist else None
            if idx == 0:
                parceiros_ultima_rodada.setdefault(j1, set()).add(j2)
                parceiros_ultima_rodada.setdefault(j2, set()).add(j1)
                parceiros_ultima_rodada.setdefault(j3, set()).add(j4)
                parceiros_ultima_rodada.setdefault(j4, set()).add(j3)
            peso_parceiro, peso_adversario = _peso_historico(jogo)
            hist_p.setdefault(j1, {})[j2] = max(hist_p.setdefault(j1, {}).get(j2, 0), peso_parceiro)
            hist_p.setdefault(j2, {})[j1] = max(hist_p.setdefault(j2, {}).get(j1, 0), peso_parceiro)
            hist_p.setdefault(j3, {})[j4] = max(hist_p.setdefault(j3, {}).get(j4, 0), peso_parceiro)
            hist_p.setdefault(j4, {})[j3] = max(hist_p.setdefault(j4, {}).get(j3, 0), peso_parceiro)
            for p in (j1, j2):
                hist_a.setdefault(p, {})[j3] = max(hist_a.setdefault(p, {}).get(j3, 0), peso_adversario)
                hist_a.setdefault(p, {})[j4] = max(hist_a.setdefault(p, {}).get(j4, 0), peso_adversario)
            for p in (j3, j4):
                hist_a.setdefault(p, {})[j1] = max(hist_a.setdefault(p, {}).get(j1, 0), peso_adversario)
                hist_a.setdefault(p, {})[j2] = max(hist_a.setdefault(p, {}).get(j2, 0), peso_adversario)

    # ── Loop de tentativas ────────────────────────────────────────────────────
    best_sorteio: Sorteio | None = None
    best_r2: int = 999_999
    best_hist: int = 999_999
    validos_encontrados: int = 0

    max_validos = 500
    started_at = time.perf_counter()

    def _report_progress(tentativa: int, *, done: bool = False, message: str | None = None) -> None:
        if progress_callback is None:
            return
        elapsed = max(time.perf_counter() - started_at, 0.001)
        progresso_tentativas = tentativa / max_tentativas if max_tentativas else 0.0
        progresso_validos = (
            validos_encontrados / max_validos if max_validos else 0.0
        )
        progresso = 1.0 if done else min(max(progresso_tentativas, progresso_validos), 0.99)
        eta_tentativas = 0.0
        eta_validos = 0.0
        if not done and tentativa > 0:
            ritmo_tentativas = elapsed / tentativa
            eta_tentativas = max((max_tentativas - tentativa) * ritmo_tentativas, 0.0)
        if not done and validos_encontrados > 0:
            ritmo_validos = elapsed / validos_encontrados
            eta_validos = max((max_validos - validos_encontrados) * ritmo_validos, 0.0)
        etas = [eta for eta in (eta_tentativas, eta_validos) if eta > 0]
        eta_seconds = min(etas) if etas else 0.0
        progress_callback({
            "attempt": tentativa,
            "max_attempts": max_tentativas,
            "valid_found": validos_encontrados,
            "max_valid_found": max_validos,
            "best_rule2": best_r2,
            "best_history": best_hist,
            "elapsed_seconds": elapsed,
            "eta_seconds": eta_seconds,
            "progress": progresso,
            "done": done,
            "message": message,
        })

    _report_progress(0, message="Preparando busca do sorteio...")

    for tentativa in range(1, max_tentativas + 1):
        random.shuffle(jogadores)
        parceiros: dict[int, set[int]] = {j: set() for j in jogadores}
        adversarios: dict[int, set[int]] = {j: set() for j in jogadores}
        sorteio: Sorteio = []
        falhou = False

        # adversarios_noite: acumula quem já foi adversário na noite atual
        # (passado como dica para o backtracking evitar parcerias conflitantes)
        adversarios_noite: dict[int, set[int]] = {j: set() for j in jogadores}

        for _ in range(4):
            rodada = _tentar_rodada(
                jogadores,
                parceiros,
                adversarios,
                parceiros_ultima_rodada=parceiros_ultima_rodada,
                adversarios_noite=adversarios_noite,
            )
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

        if tentativa == 1 or tentativa % 100 == 0:
            _report_progress(tentativa, message="Buscando a melhor combinacao...")

        # Sai cedo se encontrou solução perfeita ou após avaliar muitas soluções válidas.
        if (best_r2 == 0 and best_hist == 0) or validos_encontrados >= max_validos:
            _report_progress(
                tentativa,
                done=True,
                message="Sorteio encontrado. Finalizando..."
            )
            return best_sorteio

    if best_sorteio:
        _report_progress(
            max_tentativas,
            done=True,
            message="Melhor sorteio disponivel encontrado. Finalizando..."
        )
        return best_sorteio

    _report_progress(
        max_tentativas,
        done=True,
        message="Nao foi possivel encontrar um sorteio valido."
    )
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
