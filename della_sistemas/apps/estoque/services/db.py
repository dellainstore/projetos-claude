import sqlite3

from .config import DB_PATH, DATA_DIR


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS estoque_precos (
                produto_id INTEGER PRIMARY KEY,
                preco REAL,
                custo REAL,
                fornecedor TEXT,
                estoque_consolidado REAL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS estoque (
                produto_id INTEGER PRIMARY KEY,
                quantidade REAL NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vendas (
                produto_id INTEGER NOT NULL,
                quantidade REAL NOT NULL,
                data TEXT NOT NULL,
                pedido_id INTEGER,
                situacao_id INTEGER
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vendas_produto ON vendas(produto_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vendas_data ON vendas(data)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vendas_pedido ON vendas(pedido_id)")

        colunas_vendas = {row[1] for row in conn.execute("PRAGMA table_info(vendas)").fetchall()}
        if "valor" not in colunas_vendas:
            conn.execute("ALTER TABLE vendas ADD COLUMN valor REAL")

        conn.commit()
    finally:
        conn.close()
