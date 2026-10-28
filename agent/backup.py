"""Export et restauration contrôlée des données SQLite du Pouletier."""
from datetime import datetime, timezone
import json

from .db import connect

TABLES = ("flocks", "stock", "expenses", "sales", "tasks", "agent_events")
FORMAT_VERSION = 1


def create_backup():
    """Retourne une sauvegarde JSON portable de toutes les tables métier."""
    tables = {}
    with connect() as con:
        for table in TABLES:
            rows = con.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
            tables[table] = [dict(row) for row in rows]
    return {
        "format": "le-pouletier-intelligence-backup",
        "format_version": FORMAT_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "tables": tables,
    }


def restore_backup(payload, confirmed=False):
    """Restaure une sauvegarde valide. L'opération remplace les données existantes."""
    if not confirmed:
        raise ValueError("Confirme explicitement la restauration avant de continuer.")
    if not isinstance(payload, dict):
        raise ValueError("Le fichier de sauvegarde doit contenir un objet JSON.")
    if payload.get("format") != "le-pouletier-intelligence-backup":
        raise ValueError("Ce fichier n'est pas une sauvegarde Le Pouletier Intelligence.")
    if payload.get("format_version") != FORMAT_VERSION:
        raise ValueError("Version de sauvegarde non prise en charge.")
    tables = payload.get("tables")
    if not isinstance(tables, dict) or set(tables) != set(TABLES):
        raise ValueError("La sauvegarde est incomplète ou contient une structure inconnue.")
    for table in TABLES:
        if not isinstance(tables[table], list):
            raise ValueError(f"La table {table} doit être une liste.")
        if any(not isinstance(row, dict) for row in tables[table]):
            raise ValueError(f"La table {table} contient une ligne invalide.")

    # Vérifier les colonnes avant de toucher aux données existantes.
    with connect() as con:
        expected_columns = {
            table: {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
            for table in TABLES
        }
        for table in TABLES:
            for row in tables[table]:
                if set(row) != expected_columns[table]:
                    raise ValueError(f"Les colonnes de la table {table} ne correspondent pas à cette version de l'application.")

        # La transaction garantit un retour arrière si une ligne est invalide.
        for table in reversed(TABLES):
            con.execute(f"DELETE FROM {table}")
        for table in TABLES:
            columns = sorted(expected_columns[table], key=lambda col: next(
                i for i, info in enumerate(con.execute(f"PRAGMA table_info({table})").fetchall()) if info["name"] == col
            ))
            if not columns:
                continue
            placeholders = ",".join("?" for _ in columns)
            col_sql = ",".join(f'"{col}"' for col in columns)
            sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
            for row in tables[table]:
                con.execute(sql, tuple(row[col] for col in columns))
        # Repositionner les compteurs AUTOINCREMENT après restauration.
        for table in TABLES:
            con.execute("DELETE FROM sqlite_sequence WHERE name=?", (table,))
            max_id = con.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}").fetchone()[0]
            if max_id:
                con.execute("INSERT INTO sqlite_sequence(name,seq) VALUES(?,?)", (table, max_id))

    return {table: len(tables[table]) for table in TABLES}


def backup_json_text():
    return json.dumps(create_backup(), ensure_ascii=False, indent=2)
