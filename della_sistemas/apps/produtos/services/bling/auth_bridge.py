import sys
from pathlib import Path
from apps.produtos.services.config import BLING_AUTH_DIR

def get_access_token() -> str:
    auth_dir = Path(BLING_AUTH_DIR)
    auth_file = auth_dir / "bling_auth_core.py"

    if not auth_file.exists():
        raise FileNotFoundError(
            f"Não encontrei bling_auth_core.py em: {auth_file}\n"
            f"Confira BLING_AUTH_DIR no .env"
        )

    # Permite importar o módulo do seu auth existente
    if str(auth_dir) not in sys.path:
        sys.path.insert(0, str(auth_dir))

    import bling_auth_core  # type: ignore

    return bling_auth_core.get_access_token()
