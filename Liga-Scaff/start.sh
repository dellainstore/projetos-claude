#!/bin/bash
# Inicia a Liga Quarta Scaff
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "Criando ambiente virtual..."
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
fi

echo "Iniciando Liga Quarta Scaff em http://localhost:8510"
.venv/bin/streamlit run app.py --server.port 8510 --server.address 0.0.0.0
