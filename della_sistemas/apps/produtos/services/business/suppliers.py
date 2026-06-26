import time
from apps.produtos.services.config import DEFAULT_SUPPLIERS


def normalize_supplier_name(name: str) -> str:
    return " ".join((name or "").strip().upper().split())


def build_supplier_options(extra_names: list[str] | None = None) -> list[str]:
    merged = [normalize_supplier_name(n) for n in DEFAULT_SUPPLIERS]
    for n in (extra_names or []):
        norm = normalize_supplier_name(n)
        if norm:
            merged.append(norm)

    seen = set()
    out = []
    for n in merged:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _ensure_supplier_contacts_table() -> None:
    from apps.produtos.services.db import get_conn
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bling_supplier_contacts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT NOT NULL UNIQUE,
            bling_id    INTEGER NOT NULL,
            created_at  INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_supplier_table_initialized = False


def get_or_create_bling_supplier(supplier_name: str) -> int | None:
    """
    Retorna o bling_contact_id do fornecedor, criando no Bling se necessário.
    Mantém cache local em bling_supplier_contacts.
    """
    global _supplier_table_initialized
    if not _supplier_table_initialized:
        _ensure_supplier_contacts_table()
        _supplier_table_initialized = True

    name = normalize_supplier_name(supplier_name)
    if not name:
        return None

    from apps.produtos.services.db import get_conn
    conn = get_conn()
    row = conn.execute(
        "SELECT bling_id FROM bling_supplier_contacts WHERE nome = ?", (name,)
    ).fetchone()
    conn.close()

    if row:
        return int(row[0])

    # Cria no Bling
    from apps.produtos.services.bling.api import bling_request_raw
    try:
        r = bling_request_raw(
            "POST", "/contatos",
            json={"nome": name, "tipo": "F", "situacao": "A"},
            timeout=10,
        )
        if r.status_code not in (200, 201):
            return None
        bling_id = (r.json().get("data") or {}).get("id")
        if not bling_id:
            return None
        bling_id = int(bling_id)
    except Exception:
        return None

    # Salva no cache local
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO bling_supplier_contacts (nome, bling_id, created_at) VALUES (?, ?, ?)",
        (name, bling_id, int(time.time())),
    )
    conn.commit()
    conn.close()
    return bling_id


def seed_supplier_contacts(contacts: dict[str, int]) -> None:
    """Registra manualmente mapeamentos nome → bling_id (para fornecedores já criados)."""
    _ensure_supplier_contacts_table()
    from apps.produtos.services.db import get_conn
    conn = get_conn()
    now = int(time.time())
    for name, bling_id in contacts.items():
        norm = normalize_supplier_name(name)
        if norm:
            conn.execute(
                "INSERT OR REPLACE INTO bling_supplier_contacts (nome, bling_id, created_at) VALUES (?, ?, ?)",
                (norm, int(bling_id), now),
            )
    conn.commit()
    conn.close()
