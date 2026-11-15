import sqlite3
from pathlib import Path

DB_PATH = Path("instance") / "smartroom.db"
DUMP_PATH = Path("dump.sql")

def make_dump():
    if not DB_PATH.exists():
        print(f"❌ Файл базы данных не найден: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    sql_dump = "\n".join(conn.iterdump())
    conn.close()

    with open(DUMP_PATH, "w", encoding="utf-8") as f:
        f.write(sql_dump)

    print(f"✅ Дамп сохранен в {DUMP_PATH}")
    print(f"   Размер файла: {DUMP_PATH.stat().st_size} байт")

if __name__ == "__main__":
    make_dump()