"""
Execucao em segundo plano do sorteio da Liga Quarta Scaff.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import database as db
from src.draw_engine import gerar_sorteio, sorteio_para_tabela, validar_sorteio

_lock = threading.Lock()
_threads: dict[int, threading.Thread] = {}


def _iso_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def is_job_running(rodada_id: int) -> bool:
    with _lock:
        th = _threads.get(rodada_id)
        if th and th.is_alive():
            return True
        if th and not th.is_alive():
            _threads.pop(rodada_id, None)
        return False


def start_sorteio_job(
    rodada_id: int,
    jogadores_ids: list[int],
    nomes_map: dict[int, str],
    historico_jogos: list[dict] | None = None,
) -> bool:
    with _lock:
        th = _threads.get(rodada_id)
        if th and th.is_alive():
            return False

        db.upsert_sorteio_job(
            rodada_id,
            status="queued",
            progress=0,
            message="Sorteio enfileirado.",
            attempt=0,
            max_attempts=0,
            valid_found=0,
            max_valid_found=0,
            eta_seconds=0,
            elapsed_seconds=0,
            best_rule2=None,
            best_history=None,
            error_text=None,
            started_at=_iso_now(),
            finished_at=None,
            updated_at=_iso_now(),
        )
        db.update_rodada_status(rodada_id, "gerando_sorteio")

        th = threading.Thread(
            target=_run_sorteio_job,
            args=(rodada_id, jogadores_ids, nomes_map, historico_jogos or []),
            daemon=True,
            name=f"sorteio_job_{rodada_id}",
        )
        _threads[rodada_id] = th
        th.start()
        return True


def _run_sorteio_job(
    rodada_id: int,
    jogadores_ids: list[int],
    nomes_map: dict[int, str],
    historico_jogos: list[dict],
) -> None:
    rodada = db.get_rodada(rodada_id)
    status_anterior = rodada["status"] if rodada else "pendente"

    def _progress(info: dict) -> None:
        db.upsert_sorteio_job(
            rodada_id,
            status="running" if not info["done"] else "finalizing",
            progress=info["progress"],
            message=info["message"],
            attempt=info["attempt"],
            max_attempts=info["max_attempts"],
            valid_found=info["valid_found"],
            max_valid_found=info["max_valid_found"],
            eta_seconds=info["eta_seconds"],
            elapsed_seconds=info["elapsed_seconds"],
            best_rule2=info["best_rule2"],
            best_history=info["best_history"],
            error_text=None,
            updated_at=_iso_now(),
        )

    try:
        resultado = gerar_sorteio(
            jogadores_ids,
            historico_jogos=historico_jogos,
            progress_callback=_progress,
        )
        erros = validar_sorteio(resultado, jogadores_ids)
        if erros:
            raise ValueError(f"Sorteio invalido: {erros[0]}")

        sorteio_id = db.create_sorteio(rodada_id)
        tabela = sorteio_para_tabela(resultado, nomes_map)
        for jogo in tabela:
            def _id(v): return v if v > 0 else None
            def _nv(v): return nomes_map.get(v) if v < 0 else None
            db.insert_jogo(
                sorteio_id, jogo["rodada_interna"], jogo["quadra"],
                _id(jogo["dupla1_j1"]), _id(jogo["dupla1_j2"]),
                _id(jogo["dupla2_j1"]), _id(jogo["dupla2_j2"]),
                _nv(jogo["dupla1_j1"]), _nv(jogo["dupla1_j2"]),
                _nv(jogo["dupla2_j1"]), _nv(jogo["dupla2_j2"]),
            )
        db.set_sorteio_ativo(sorteio_id, rodada_id)
        db.update_rodada_status(rodada_id, "sorteio_feito")
        db.upsert_sorteio_job(
            rodada_id,
            status="completed",
            progress=1,
            message="Sorteio gerado com sucesso.",
            eta_seconds=0,
            finished_at=_iso_now(),
            updated_at=_iso_now(),
        )
    except Exception as exc:
        db.update_rodada_status(rodada_id, status_anterior if status_anterior != "gerando_sorteio" else "pendente")
        db.upsert_sorteio_job(
            rodada_id,
            status="error",
            progress=0,
            message="Falha ao gerar sorteio.",
            error_text=str(exc),
            finished_at=_iso_now(),
            updated_at=_iso_now(),
        )
    finally:
        with _lock:
            _threads.pop(rodada_id, None)
