import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "instance"
DB_PATH = DB_DIR / "smartroom.db"


def get_connection():
    DB_DIR.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with get_connection() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                capacity INTEGER NOT NULL CHECK(capacity > 0),
                has_computers INTEGER NOT NULL DEFAULT 0, -- оставляем (мало ли пригодится)
                has_board INTEGER NOT NULL DEFAULT 0,     -- НОВОЕ
                has_projector INTEGER NOT NULL DEFAULT 0, -- НОВОЕ
                room_type TEXT NOT NULL DEFAULT 'обычная',
                is_available INTEGER NOT NULL DEFAULT 1
            );


            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                students_count INTEGER NOT NULL CHECK(students_count > 0),
                course INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                requires_computers INTEGER NOT NULL DEFAULT 0, -- оставляем
                requires_board INTEGER NOT NULL DEFAULT 0,     -- НОВОЕ
                requires_projector INTEGER NOT NULL DEFAULT 0, -- НОВОЕ
                language TEXT NOT NULL DEFAULT 'ru'
            );

            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                teacher_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                room_id INTEGER NOT NULL,
                lesson_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                CHECK(start_time < end_time),
                FOREIGN KEY (group_id) REFERENCES groups(id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(id),
                FOREIGN KEY (subject_id) REFERENCES subjects(id),
                FOREIGN KEY (room_id) REFERENCES rooms(id)
            );
            
            CREATE TABLE IF NOT EXISTS seats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                seat_number TEXT NOT NULL,
                has_socket INTEGER NOT NULL DEFAULT 0,
                is_computer INTEGER NOT NULL DEFAULT 0,
                pos_x INTEGER NOT NULL DEFAULT 0,
                pos_y INTEGER NOT NULL DEFAULT 0,
                pos_z INTEGER NOT NULL DEFAULT 0,
                type TEXT NOT NULL DEFAULT 'seat', -- 'seat', 'socket', 'ac', 'board', 'projector'
                rotation REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (room_id) REFERENCES rooms(id)
            );

            CREATE TABLE IF NOT EXISTS seats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                seat_number TEXT NOT NULL,
                has_socket INTEGER NOT NULL DEFAULT 0,
                is_computer INTEGER NOT NULL DEFAULT 0,
                pos_x INTEGER NOT NULL DEFAULT 0,
                pos_y INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (room_id) REFERENCES rooms(id)
            );
        """)


if __name__ == "__main__":
    init_db()
    print("База данных SmartRoom создана!")