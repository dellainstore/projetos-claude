"""
Módulo de banco de dados da Liga Quarta Scaff.
Gerencia schema SQLite e todas as operações CRUD.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "liga_scaff.db"


def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer'
            );

            CREATE TABLE IF NOT EXISTS temporadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                ano INTEGER NOT NULL,
                n_rodadas INTEGER DEFAULT 8,
                n_descartadas INTEGER DEFAULT 2,
                ativa INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS jogadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT,
                whatsapp TEXT,
                ativo INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS jogadores_temporada (
                jogador_id INTEGER REFERENCES jogadores(id),
                temporada_id INTEGER REFERENCES temporadas(id),
                PRIMARY KEY (jogador_id, temporada_id)
            );

            CREATE TABLE IF NOT EXISTS rodadas_liga (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                temporada_id INTEGER REFERENCES temporadas(id),
                numero INTEGER NOT NULL,
                data DATE NOT NULL,
                n_jogadores INTEGER,
                status TEXT DEFAULT 'pendente'
            );

            CREATE TABLE IF NOT EXISTS visitantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rodada_id INTEGER REFERENCES rodadas_liga(id),
                nome TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sorteios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rodada_id INTEGER REFERENCES rodadas_liga(id),
                numero INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ativo INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS jogos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sorteio_id INTEGER REFERENCES sorteios(id),
                rodada_interna INTEGER NOT NULL,
                quadra INTEGER NOT NULL,
                dupla1_j1 INTEGER REFERENCES jogadores(id),
                dupla1_j2 INTEGER REFERENCES jogadores(id),
                dupla2_j1 INTEGER REFERENCES jogadores(id),
                dupla2_j2 INTEGER REFERENCES jogadores(id),
                dupla1_j1_nome TEXT,
                dupla1_j2_nome TEXT,
                dupla2_j1_nome TEXT,
                dupla2_j2_nome TEXT
            );

            CREATE TABLE IF NOT EXISTS resultados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jogo_id INTEGER UNIQUE REFERENCES jogos(id),
                games_dupla1 INTEGER NOT NULL,
                games_dupla2 INTEGER NOT NULL,
                tiebreak INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS pontuacao_rodada (
                jogador_id INTEGER REFERENCES jogadores(id),
                rodada_id INTEGER REFERENCES rodadas_liga(id),
                pontos INTEGER DEFAULT 0,
                jogos_ganhos INTEGER DEFAULT 0,
                jogos_perdidos INTEGER DEFAULT 0,
                tem_beer INTEGER DEFAULT 0,
                PRIMARY KEY (jogador_id, rodada_id)
            );

            CREATE TABLE IF NOT EXISTS finais_liga (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                temporada_id INTEGER REFERENCES temporadas(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pendente'
            );

            CREATE TABLE IF NOT EXISTS jogos_final (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                final_id INTEGER REFERENCES finais_liga(id),
                serie TEXT NOT NULL,
                fase TEXT NOT NULL,
                dupla1_p1 INTEGER REFERENCES jogadores(id),
                dupla1_p2 INTEGER REFERENCES jogadores(id),
                dupla2_p1 INTEGER REFERENCES jogadores(id),
                dupla2_p2 INTEGER REFERENCES jogadores(id),
                games_d1 INTEGER,
                games_d2 INTEGER,
                vencedor INTEGER
            );
        """)
        # Migração: adiciona colunas de nomes para visitantes se não existirem
        colunas = [r["name"] for r in conn.execute("PRAGMA table_info(jogos)").fetchall()]
        for col in ["dupla1_j1_nome", "dupla1_j2_nome", "dupla2_j1_nome", "dupla2_j2_nome"]:
            if col not in colunas:
                conn.execute(f"ALTER TABLE jogos ADD COLUMN {col} TEXT")


# ── USERS ─────────────────────────────────────────────────────────────────────

def get_user(username: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)
        ).fetchone()


def create_user(username: str, password_hash: str, role: str = "viewer") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
            (username, password_hash, role),
        )


def list_users() -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT id, username, role FROM users ORDER BY username").fetchall()


def delete_user(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def update_user_role(user_id: int, role: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def update_user_password(user_id: int, password_hash: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def has_any_user() -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()
        return row["c"] > 0


# ── TEMPORADAS ────────────────────────────────────────────────────────────────

def list_temporadas() -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM temporadas ORDER BY ano DESC").fetchall()


def get_temporada(temporada_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM temporadas WHERE id = ?", (temporada_id,)).fetchone()


def get_temporada_ativa() -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM temporadas WHERE ativa = 1 ORDER BY ano DESC LIMIT 1").fetchone()


def create_temporada(nome: str, ano: int, n_rodadas: int = 8, n_descartadas: int = 2) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO temporadas (nome, ano, n_rodadas, n_descartadas) VALUES (?,?,?,?)",
            (nome, ano, n_rodadas, n_descartadas),
        )
        return cur.lastrowid


def set_temporada_ativa(temporada_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE temporadas SET ativa = 0")
        conn.execute("UPDATE temporadas SET ativa = 1 WHERE id = ?", (temporada_id,))


# ── JOGADORES ─────────────────────────────────────────────────────────────────

def list_jogadores(apenas_ativos: bool = True) -> list[dict]:
    with get_conn() as conn:
        if apenas_ativos:
            return conn.execute("SELECT * FROM jogadores WHERE ativo = 1 ORDER BY nome").fetchall()
        return conn.execute("SELECT * FROM jogadores ORDER BY nome").fetchall()


def get_jogador(jogador_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM jogadores WHERE id = ?", (jogador_id,)).fetchone()


def create_jogador(nome: str, email: str = "", whatsapp: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO jogadores (nome, email, whatsapp) VALUES (?,?,?)",
            (nome, email or None, whatsapp or None),
        )
        return cur.lastrowid


def update_jogador(jogador_id: int, nome: str, email: str, whatsapp: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE jogadores SET nome=?, email=?, whatsapp=? WHERE id=?",
            (nome, email or None, whatsapp or None, jogador_id),
        )


def delete_jogador(jogador_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM jogadores_temporada WHERE jogador_id = ?", (jogador_id,))
        conn.execute("DELETE FROM jogadores WHERE id = ?", (jogador_id,))


def toggle_jogador_ativo(jogador_id: int, ativo: bool) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE jogadores SET ativo=? WHERE id=?", (int(ativo), jogador_id))


def list_jogadores_temporada(temporada_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute("""
            SELECT j.* FROM jogadores j
            JOIN jogadores_temporada jt ON j.id = jt.jogador_id
            WHERE jt.temporada_id = ? AND j.ativo = 1
            ORDER BY j.nome
        """, (temporada_id,)).fetchall()


def add_jogador_temporada(jogador_id: int, temporada_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO jogadores_temporada (jogador_id, temporada_id) VALUES (?,?)",
            (jogador_id, temporada_id),
        )


def remove_jogador_temporada(jogador_id: int, temporada_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM jogadores_temporada WHERE jogador_id=? AND temporada_id=?",
            (jogador_id, temporada_id),
        )


# ── RODADAS DA LIGA ───────────────────────────────────────────────────────────

def list_rodadas(temporada_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM rodadas_liga WHERE temporada_id = ? ORDER BY numero",
            (temporada_id,),
        ).fetchall()


def get_rodada(rodada_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM rodadas_liga WHERE id = ?", (rodada_id,)).fetchone()


def create_rodada(temporada_id: int, numero: int, data: str, n_jogadores: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO rodadas_liga (temporada_id, numero, data, n_jogadores) VALUES (?,?,?,?)",
            (temporada_id, numero, data, n_jogadores),
        )
        return cur.lastrowid


def update_rodada(rodada_id: int, numero: int, data: str, n_jogadores: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE rodadas_liga SET numero=?, data=?, n_jogadores=? WHERE id=?",
            (numero, data, n_jogadores, rodada_id),
        )


def update_rodada_status(rodada_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE rodadas_liga SET status=? WHERE id=?", (status, rodada_id))


def delete_rodada(rodada_id: int) -> None:
    """Remove rodada e tudo que depende dela (sorteios, jogos, resultados, pontuações, visitantes)."""
    with get_conn() as conn:
        sorteios = conn.execute(
            "SELECT id FROM sorteios WHERE rodada_id = ?", (rodada_id,)
        ).fetchall()
        for s in sorteios:
            conn.execute("DELETE FROM resultados WHERE jogo_id IN (SELECT id FROM jogos WHERE sorteio_id = ?)", (s["id"],))
            conn.execute("DELETE FROM jogos WHERE sorteio_id = ?", (s["id"],))
        conn.execute("DELETE FROM sorteios WHERE rodada_id = ?", (rodada_id,))
        conn.execute("DELETE FROM pontuacao_rodada WHERE rodada_id = ?", (rodada_id,))
        conn.execute("DELETE FROM visitantes WHERE rodada_id = ?", (rodada_id,))
        conn.execute("DELETE FROM rodadas_liga WHERE id = ?", (rodada_id,))


def delete_temporada(temporada_id: int) -> None:
    """Remove temporada e todos os dados associados."""
    with get_conn() as conn:
        rodadas = conn.execute(
            "SELECT id FROM rodadas_liga WHERE temporada_id = ?", (temporada_id,)
        ).fetchall()
        for r in rodadas:
            sorteios = conn.execute(
                "SELECT id FROM sorteios WHERE rodada_id = ?", (r["id"],)
            ).fetchall()
            for s in sorteios:
                conn.execute("DELETE FROM resultados WHERE jogo_id IN (SELECT id FROM jogos WHERE sorteio_id = ?)", (s["id"],))
                conn.execute("DELETE FROM jogos WHERE sorteio_id = ?", (s["id"],))
            conn.execute("DELETE FROM sorteios WHERE rodada_id = ?", (r["id"],))
            conn.execute("DELETE FROM pontuacao_rodada WHERE rodada_id = ?", (r["id"],))
            conn.execute("DELETE FROM visitantes WHERE rodada_id = ?", (r["id"],))
        conn.execute("DELETE FROM rodadas_liga WHERE temporada_id = ?", (temporada_id,))
        conn.execute("DELETE FROM jogadores_temporada WHERE temporada_id = ?", (temporada_id,))
        conn.execute("DELETE FROM temporadas WHERE id = ?", (temporada_id,))


# ── HISTÓRICO DE JOGOS ────────────────────────────────────────────────────────

def get_historico_jogos_rodadas(rodada_id: int, n: int = 2) -> list[dict]:
    """
    Retorna os jogos dos últimos N sorteios oficiais concluídos ANTES da rodada informada,
    dentro da mesma temporada. Usado pelo motor de sorteio para evitar repetições históricas.
    """
    with get_conn() as conn:
        rodada = conn.execute(
            "SELECT temporada_id, numero FROM rodadas_liga WHERE id = ?", (rodada_id,)
        ).fetchone()
        if not rodada:
            return []

        rodadas_ant = conn.execute("""
            SELECT id FROM rodadas_liga
            WHERE temporada_id = ? AND numero < ? AND status = 'concluida'
            ORDER BY numero DESC LIMIT ?
        """, (rodada["temporada_id"], rodada["numero"], n)).fetchall()

        if not rodadas_ant:
            return []

        ids = [r["id"] for r in rodadas_ant]
        placeholders = ",".join("?" * len(ids))
        return conn.execute(f"""
            SELECT j.dupla1_j1, j.dupla1_j2, j.dupla2_j1, j.dupla2_j2
            FROM jogos j
            JOIN sorteios s ON j.sorteio_id = s.id
            WHERE s.rodada_id IN ({placeholders}) AND s.ativo = 1
        """, ids).fetchall()


# ── VISITANTES ────────────────────────────────────────────────────────────────

def list_visitantes(rodada_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM visitantes WHERE rodada_id = ? ORDER BY nome", (rodada_id,)
        ).fetchall()


def add_visitante(rodada_id: int, nome: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO visitantes (rodada_id, nome) VALUES (?,?)", (rodada_id, nome)
        )
        return cur.lastrowid


def delete_visitante(visitante_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM visitantes WHERE id = ?", (visitante_id,))


# ── SORTEIOS ──────────────────────────────────────────────────────────────────

def list_sorteios(rodada_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM sorteios WHERE rodada_id = ? ORDER BY numero", (rodada_id,)
        ).fetchall()


def get_sorteio_ativo(rodada_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM sorteios WHERE rodada_id = ? AND ativo = 1", (rodada_id,)
        ).fetchone()


def create_sorteio(rodada_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(numero), 0) + 1 as next_num FROM sorteios WHERE rodada_id = ?",
            (rodada_id,),
        ).fetchone()
        cur = conn.execute(
            "INSERT INTO sorteios (rodada_id, numero, ativo) VALUES (?,?,0)",
            (rodada_id, row["next_num"]),
        )
        return cur.lastrowid


def set_sorteio_ativo(sorteio_id: int, rodada_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE sorteios SET ativo = 0 WHERE rodada_id = ?", (rodada_id,))
        conn.execute("UPDATE sorteios SET ativo = 1 WHERE id = ?", (sorteio_id,))


def delete_sorteio(sorteio_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM jogos WHERE sorteio_id = ?", (sorteio_id,))
        conn.execute("DELETE FROM sorteios WHERE id = ?", (sorteio_id,))


# ── JOGOS ─────────────────────────────────────────────────────────────────────

def insert_jogo(
    sorteio_id: int,
    rodada_interna: int,
    quadra: int,
    d1j1: int | None,
    d1j2: int | None,
    d2j1: int | None,
    d2j2: int | None,
    d1j1_nome: str | None = None,
    d1j2_nome: str | None = None,
    d2j1_nome: str | None = None,
    d2j2_nome: str | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO jogos
               (sorteio_id, rodada_interna, quadra,
                dupla1_j1, dupla1_j2, dupla2_j1, dupla2_j2,
                dupla1_j1_nome, dupla1_j2_nome, dupla2_j1_nome, dupla2_j2_nome)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (sorteio_id, rodada_interna, quadra, d1j1, d1j2, d2j1, d2j2,
             d1j1_nome, d1j2_nome, d2j1_nome, d2j2_nome),
        )
        return cur.lastrowid


def list_jogos_sorteio(sorteio_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jogos WHERE sorteio_id = ? ORDER BY rodada_interna, quadra",
            (sorteio_id,),
        ).fetchall()


def list_jogos_rodada(rodada_id: int) -> list[dict]:
    """Retorna jogos do sorteio ativo de uma rodada."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT j.* FROM jogos j
            JOIN sorteios s ON j.sorteio_id = s.id
            WHERE s.rodada_id = ? AND s.ativo = 1
            ORDER BY j.rodada_interna, j.quadra
        """, (rodada_id,)).fetchall()


# ── RESULTADOS ────────────────────────────────────────────────────────────────

def get_resultado(jogo_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM resultados WHERE jogo_id = ?", (jogo_id,)
        ).fetchone()


def upsert_resultado(jogo_id: int, games_d1: int, games_d2: int, tiebreak: int = 0) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO resultados (jogo_id, games_dupla1, games_dupla2, tiebreak)
            VALUES (?,?,?,?)
            ON CONFLICT(jogo_id) DO UPDATE SET
                games_dupla1 = excluded.games_dupla1,
                games_dupla2 = excluded.games_dupla2,
                tiebreak = excluded.tiebreak
        """, (jogo_id, games_d1, games_d2, tiebreak))


def list_resultados_rodada(rodada_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute("""
            SELECT r.*, j.dupla1_j1, j.dupla1_j2, j.dupla2_j1, j.dupla2_j2,
                   j.rodada_interna, j.quadra
            FROM resultados r
            JOIN jogos j ON r.jogo_id = j.id
            JOIN sorteios s ON j.sorteio_id = s.id
            WHERE s.rodada_id = ? AND s.ativo = 1
        """, (rodada_id,)).fetchall()


# ── PONTUAÇÃO ─────────────────────────────────────────────────────────────────

def delete_pontuacao_rodada(rodada_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM pontuacao_rodada WHERE rodada_id = ?", (rodada_id,))


def upsert_pontuacao(
    jogador_id: int,
    rodada_id: int,
    pontos: int,
    jogos_ganhos: int,
    jogos_perdidos: int,
    tem_beer: int,
) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO pontuacao_rodada
                (jogador_id, rodada_id, pontos, jogos_ganhos, jogos_perdidos, tem_beer)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(jogador_id, rodada_id) DO UPDATE SET
                pontos = excluded.pontos,
                jogos_ganhos = excluded.jogos_ganhos,
                jogos_perdidos = excluded.jogos_perdidos,
                tem_beer = excluded.tem_beer
        """, (jogador_id, rodada_id, pontos, jogos_ganhos, jogos_perdidos, tem_beer))


def get_pontuacao_rodada(rodada_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute("""
            SELECT p.*, j.nome FROM pontuacao_rodada p
            JOIN jogadores j ON p.jogador_id = j.id
            WHERE p.rodada_id = ?
            ORDER BY p.pontos DESC
        """, (rodada_id,)).fetchall()


def get_pontuacoes_temporada(temporada_id: int) -> list[dict]:
    """Retorna todas as pontuações de todas as rodadas de uma temporada."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT p.*, j.nome, r.numero as rodada_numero
            FROM pontuacao_rodada p
            JOIN jogadores j ON p.jogador_id = j.id
            JOIN rodadas_liga r ON p.rodada_id = r.id
            WHERE r.temporada_id = ? AND r.status = 'concluida'
            ORDER BY r.numero, p.pontos DESC
        """, (temporada_id,)).fetchall()


def update_jogo_players(
    jogo_id: int,
    id1, id2, id3, id4,
    nv1, nv2, nv3, nv4,
) -> None:
    """Atualiza jogadores e nomes de visitantes de um jogo."""
    with get_conn() as conn:
        conn.execute("""
            UPDATE jogos SET
                dupla1_j1=?, dupla1_j2=?, dupla2_j1=?, dupla2_j2=?,
                dupla1_j1_nome=?, dupla1_j2_nome=?, dupla2_j1_nome=?, dupla2_j2_nome=?
            WHERE id=?
        """, (id1, id2, id3, id4, nv1, nv2, nv3, nv4, jogo_id))


# ── FINAIS ────────────────────────────────────────────────────────────────────

def get_final(temporada_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM finais_liga WHERE temporada_id = ? ORDER BY id DESC LIMIT 1",
            (temporada_id,)
        ).fetchone()


def create_final(temporada_id: int, ranking: list[dict]) -> int:
    """Cria chaveamento de finais a partir do ranking."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO finais_liga (temporada_id, status) VALUES (?, 'pendente')",
            (temporada_id,)
        )
        final_id = cur.lastrowid

        def _pid(entry): return entry["jogador_id"]

        ouro = [r for r in ranking if r["posicao"] <= 8]
        prata = [r for r in ranking if 9 <= r["posicao"] <= 16]

        # Ouro: SF1 (1+2 vs 7+8), SF2 (3+4 vs 5+6)
        if len(ouro) >= 8:
            conn.execute(
                "INSERT INTO jogos_final (final_id,serie,fase,dupla1_p1,dupla1_p2,dupla2_p1,dupla2_p2) VALUES (?,?,?,?,?,?,?)",
                (final_id, "ouro", "semi1", _pid(ouro[0]), _pid(ouro[1]), _pid(ouro[6]), _pid(ouro[7]))
            )
            conn.execute(
                "INSERT INTO jogos_final (final_id,serie,fase,dupla1_p1,dupla1_p2,dupla2_p1,dupla2_p2) VALUES (?,?,?,?,?,?,?)",
                (final_id, "ouro", "semi2", _pid(ouro[2]), _pid(ouro[3]), _pid(ouro[4]), _pid(ouro[5]))
            )

        # Prata: SF1 (9+10 vs 15+16), SF2 (11+12 vs 13+14)
        if len(prata) >= 8:
            conn.execute(
                "INSERT INTO jogos_final (final_id,serie,fase,dupla1_p1,dupla1_p2,dupla2_p1,dupla2_p2) VALUES (?,?,?,?,?,?,?)",
                (final_id, "prata", "semi1", _pid(prata[0]), _pid(prata[1]), _pid(prata[6]), _pid(prata[7]))
            )
            conn.execute(
                "INSERT INTO jogos_final (final_id,serie,fase,dupla1_p1,dupla1_p2,dupla2_p1,dupla2_p2) VALUES (?,?,?,?,?,?,?)",
                (final_id, "prata", "semi2", _pid(prata[2]), _pid(prata[3]), _pid(prata[4]), _pid(prata[5]))
            )

        return final_id


def get_jogos_final(final_id: int) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jogos_final WHERE final_id = ? ORDER BY serie, fase",
            (final_id,)
        ).fetchall()


def upsert_resultado_final(jogo_final_id: int, g1: int, g2: int) -> None:
    vencedor = 1 if g1 > g2 else 2
    with get_conn() as conn:
        conn.execute(
            "UPDATE jogos_final SET games_d1=?, games_d2=?, vencedor=? WHERE id=?",
            (g1, g2, vencedor, jogo_final_id)
        )


def gerar_fase_final(final_id: int, serie: str) -> bool:
    """Gera a partida final a partir dos vencedores das semis. Retorna True se gerado."""
    with get_conn() as conn:
        sf1 = conn.execute(
            "SELECT * FROM jogos_final WHERE final_id=? AND serie=? AND fase='semi1'",
            (final_id, serie)
        ).fetchone()
        sf2 = conn.execute(
            "SELECT * FROM jogos_final WHERE final_id=? AND serie=? AND fase='semi2'",
            (final_id, serie)
        ).fetchone()

        if not sf1 or not sf2:
            return False
        if sf1["vencedor"] is None or sf2["vencedor"] is None:
            return False

        # Já existe final?
        existe = conn.execute(
            "SELECT id FROM jogos_final WHERE final_id=? AND serie=? AND fase='final'",
            (final_id, serie)
        ).fetchone()
        if existe:
            return True

        # Pega jogadores vencedores
        if sf1["vencedor"] == 1:
            w1p1, w1p2 = sf1["dupla1_p1"], sf1["dupla1_p2"]
        else:
            w1p1, w1p2 = sf1["dupla2_p1"], sf1["dupla2_p2"]

        if sf2["vencedor"] == 1:
            w2p1, w2p2 = sf2["dupla1_p1"], sf2["dupla1_p2"]
        else:
            w2p1, w2p2 = sf2["dupla2_p1"], sf2["dupla2_p2"]

        conn.execute(
            "INSERT INTO jogos_final (final_id,serie,fase,dupla1_p1,dupla1_p2,dupla2_p1,dupla2_p2) VALUES (?,?,?,?,?,?,?)",
            (final_id, serie, "final", w1p1, w1p2, w2p1, w2p2)
        )
        return True


def delete_final(final_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM jogos_final WHERE final_id = ?", (final_id,))
        conn.execute("DELETE FROM finais_liga WHERE id = ?", (final_id,))
