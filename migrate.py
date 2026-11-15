import sqlite3
from database import get_connection

def migrate():
    with get_connection() as db:
        print("Начинаем миграцию базы данных...")

        # 1. Добавляем колонки в таблицу rooms
        try:
            db.execute("ALTER TABLE rooms ADD COLUMN has_board INTEGER NOT NULL DEFAULT 0")
            db.execute("ALTER TABLE rooms ADD COLUMN has_projector INTEGER NOT NULL DEFAULT 0")
            print("✅ Колонки has_board и has_projector добавлены в таблицу rooms.")
        except sqlite3.OperationalError:
            print("⚠️ Колонки в rooms уже существуют (пропускаем).")

        # 2. Добавляем колонки в таблицу subjects
        try:
            db.execute("ALTER TABLE subjects ADD COLUMN requires_board INTEGER NOT NULL DEFAULT 0")
            db.execute("ALTER TABLE subjects ADD COLUMN requires_projector INTEGER NOT NULL DEFAULT 0")
            print("✅ Колонки requires_board и requires_projector добавлены в таблицу subjects.")
        except sqlite3.OperationalError:
            print("⚠️ Колонки в subjects уже существуют (пропускаем).")

        # 3. Добавляем колонки в таблицу seats (высота и поворот)
        try:
            db.execute("ALTER TABLE seats ADD COLUMN pos_z INTEGER NOT NULL DEFAULT 0")
            print("✅ Колонка pos_z добавлена в таблицу seats.")
        except sqlite3.OperationalError:
            print("⚠️ Колонка pos_z уже существует (пропускаем).")

        try:
            db.execute("ALTER TABLE seats ADD COLUMN rotation REAL NOT NULL DEFAULT 0")
            print("✅ Колонка rotation добавлена в таблицу seats.")
        except sqlite3.OperationalError:
            print("⚠️ Колонка rotation уже существует (пропускаем).")

        print("Миграция завершена!")

if __name__ == "__main__":
    migrate()