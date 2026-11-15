import sqlite3
import re
from database import get_connection


def find_teacher_id(db, name):
    if not name or name.lower() == "вакансия" or name == "НЕТ":
        row = db.execute("SELECT id FROM teachers WHERE full_name = 'Вакансия'").fetchone()
        return row["id"] if row else None

    row = db.execute("SELECT id FROM teachers WHERE full_name = ?", (name,)).fetchone()
    if row:
        return row["id"]

    surname = name.split()[0].replace(".", "").lower()
    all_t = db.execute("SELECT id, full_name FROM teachers").fetchall()
    for t in all_t:
        db_surname = str(t["full_name"]).split()[0].replace(".", "").lower()
        if db_surname == surname:
            return t["id"]

    row = db.execute("SELECT id FROM teachers WHERE full_name = 'Вакансия'").fetchone()
    return row["id"] if row else None


def get_or_create(db, table, name_column, name_value, extra_fields=None):
    if not name_value or name_value == "НЕТ":
        return None
    row = db.execute(f"SELECT id FROM {table} WHERE {name_column} = ?", (name_value,)).fetchone()
    if row:
        return row["id"]

    if extra_fields:
        columns = ", ".join(extra_fields.keys())
        placeholders = ", ".join(["?"] * len(extra_fields))
        values = list(extra_fields.values())
        query = f"INSERT INTO {table} ({name_column}, {columns}) VALUES (?, {placeholders})"
        cursor = db.execute(query, [name_value] + values)
    else:
        cursor = db.execute(f"INSERT INTO {table} ({name_column}) VALUES (?)", (name_value,))
    return cursor.lastrowid


def detect_language(text):
    kz_letters = "әғқңөұүһі"
    if any(char in text.lower() for char in kz_letters):
        return "kz"
    return "ru"


def clean_room_name(room_str):
    if not room_str:
        return "Не указана"
    match = re.search(r'(\d+|[A-Za-zА-Яа-я]+)$', room_str.strip())
    if match:
        return match.group(1)
    return "Не указана"


def import_dump():
    with get_connection() as db:
        # 1. Создаем аудиторию "Не указана", если её нет
        db.execute("INSERT OR IGNORE INTO rooms (name, capacity, has_computers) VALUES ('Не указана', 30, 0)")

        # 2. Очищаем старые данные
        db.execute("DELETE FROM lessons")
        #db.execute("DELETE FROM rooms")
        db.execute("DELETE FROM groups")
        db.execute("DELETE FROM subjects")

        # 3. Пересоздаем "Не указана" (потому что DELETE FROM rooms её удалил)
        db.execute("INSERT OR IGNORE INTO rooms (name, capacity, has_computers) VALUES ('Не указана', 30, 0)")

        current_date = None
        rows_added = 0
        errors = []

        with open("dump.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("=== ЛИСТ:"):
                    if "26год пон" in line:
                        current_date = "2026-08-31" # Понедельник
                    elif "ВТ 02.09" in line:
                        current_date = "2026-09-01" # Вторник
                    elif "ср.03.09" in line:
                        current_date = "2026-09-02" # Среда
                    elif "чт.04.09" in line:
                        current_date = "2026-09-03" # Четверг
                    elif "пт 05.09" in line:
                        current_date = "2026-09-04" # Пятница
                    continue

                if "Уақыты" in line or "Пәндер" in line or "Группа" in line:
                    continue

                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 5:
                    continue

                group_name = parts[0]
                time_str = parts[1]
                subject_name = parts[2]
                teacher_name = parts[3]
                room_name = clean_room_name(parts[4])

                # Если аудитория пустая или "НЕТ" — ставим "Не указана"
                if not room_name or room_name == "НЕТ":
                    room_name = "Не указана"

                if "-" not in group_name:
                    continue
                group_name = group_name.replace(" ", "").upper()

                match = re.search(r'(\d{1,2})[:\.](\d{2})\s*[-—]\s*(\d{1,2})[:\.\-](\d{2})', time_str)
                if not match:
                    continue
                h1, m1 = int(match.group(1)), int(match.group(2))
                h2, m2 = int(match.group(3)), int(match.group(4))
                start_time = f"{h1:02d}:{m1:02d}"
                end_time = f"{h2:02d}:{m2:02d}"

                if start_time >= end_time:
                    continue

                course = 1
                match_course = re.search(r'\d', group_name)
                if match_course:
                    course = int(match_course.group(0))

                group_id = get_or_create(db, "groups", "name", group_name, {"students_count": 25, "course": course})
                teacher_id = find_teacher_id(db, teacher_name)
                requires_pc = 1 if "информат" in subject_name.lower() or "программ" in subject_name.lower() else 0
                lang = detect_language(subject_name)
                subject_id = get_or_create(db, "subjects", "name", subject_name,
                                           {"requires_computers": requires_pc, "language": lang})
                room_id = get_or_create(db, "rooms", "name", room_name, {"capacity": 30, "has_computers": requires_pc})

                if not group_id or not teacher_id or not subject_id or not room_id:
                    errors.append(f"Пропущена пара: {group_name} | {time_str} | {subject_name} (не найдены связи)")
                    continue

                try:
                    db.execute("""
                        INSERT INTO lessons (group_id, teacher_id, subject_id, room_id, lesson_date, start_time, end_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (group_id, teacher_id, subject_id, room_id, current_date, start_time, end_time))
                    rows_added += 1
                except sqlite3.IntegrityError as e:
                    errors.append(f"Ошибка БД: {group_name} | {time_str} | {subject_name} -> {e}")

        print(f"Добавлено пар: {rows_added}")
        if errors:
            print("\n--- ОШИБКИ ---")
            for err in errors[:10]:
                print(err)

if __name__ == "__main__":
    import_dump()