"""Atualização sob demanda dos dados do painel de Metas.

Quem de fato atualiza o CSV que o painel lê (vendas_atendidas_<ano>.csv) é o
job standalone `jobs/vendas_atendidas.py`, chamado pelo cron (4x/dia + mês
anterior + backfill) e, agora, também pelo botão "Atualizar" do painel. O
lock real contra execução concorrente mora no próprio job (flock em
data/.metas_atualizacao.lock) — ele é o único ponto de verdade, então cron e
botão manual nunca rodam ao mesmo tempo, não importa quem chegou primeiro.

Este módulo só lê o status.json que o job escreve (pra UI) e dispara o job
em background quando o usuário aperta "Atualizar" — sem bloquear a request.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

BASE_DIR = Path("/var/www/della-sistemas")
STATUS_PATH = BASE_DIR / "data" / "metas_atualizacao_status.json"
BLING_ENV = Path("/etc/della/bling.env")
PYTHON_BIN = BASE_DIR / "projetos-claude" / "della_sistemas" / ".venv" / "bin" / "python"

# Só evita disparar 2 threads no mesmo worker Gunicorn num double-click bem
# rápido; a garantia de verdade contra concorrência é o flock do job.
_START_LOCK = threading.Lock()


def ler_status() -> dict:
    try:
        with open(STATUS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"running": False, "concluido_em": None, "sucesso": None, "erro": None}


def disparar_atualizacao(usuario: str) -> tuple[bool, str]:
    """Dispara a atualização em background. Retorna (iniciou, motivo)."""
    with _START_LOCK:
        status = ler_status()
        if status.get("running"):
            return False, "ja_rodando"

        def _run() -> None:
            comando = (
                f"set -a && . {BLING_ENV} && set +a && "
                f'"{PYTHON_BIN}" run_jobs.py vendas_atendidas '
                f"--inicio \"$(date +%Y-%m-01)\" --fim \"$(date +%Y-%m-%d)\" "
                f">> data/vendas_atendidas_runner.log 2>&1"
            )
            env = dict(os.environ)
            env["METAS_ATUALIZACAO_ORIGEM"] = "manual"
            env["METAS_ATUALIZACAO_USUARIO"] = usuario
            subprocess.run(["bash", "-c", comando], cwd=str(BASE_DIR), env=env)

        threading.Thread(target=_run, daemon=True).start()
        return True, "iniciado"
