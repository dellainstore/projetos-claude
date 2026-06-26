import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.produtos.services.bling.products import get_produto  # noqa


def main():
    raw = input("idProduto (Bling) ou ENTER para sair: ").strip()
    if not raw:
        return

    try:
        pid = int(raw)
    except ValueError:
        print("⚠️ Isso não é número. Use o idProduto do Bling (ex: template_id).")
        return

    try:
        resp = get_produto(pid)
        print(json.dumps(resp, ensure_ascii=False, indent=2))
    except Exception as e:
        print("❌ Erro no GET /produtos/{id}")
        print("Dica: request_id / created_at NÃO são idProduto.")
        print("Erro:", str(e))


if __name__ == "__main__":
    main()
