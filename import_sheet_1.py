import openpyxl
import sqlite3
import re
from database import get_connection


def clean_text(text):
    if not text:
        return ""
    return str(text).strip().replace('\n', ' ')


def find_teacher_id(db, name):
    """Ищет препода в базе. Если нет — возвращает ID Вакансии."""
    if not name or name.lower() == "вакансия":
        row = db.execute("SELECT id FROM teachers WHERE full_name = 'Вакансия'").fetchone()
        return row["id"] if row else None

    # 1. Точное совпадение
    row = db.execute("SELECT id FROM teachers WHERE full_name = ?", (name,)).fetchone()
    if row:
        return row["id"]

    # 2. По фамилии (первому слову)
    surname = name.split()[0].replace(".", "").lower()
    all_t = db.execute("SELECT id, full_name FROM teachers").fetchall()
    for t in all_t:
        db_surname = str(t["full_name"]).split()[0].replace(".", "").lower()
        if db_surname == surname:
            return t["id"]

    # 3. Если не нашли — Вакансия
    row = db.execute("SELECT id FROM teachers WHERE full_name = 'Вакансия'").fetchone()
    return row["id"] if row else None


def get_or_create(db, table, name_column, name_value, extra_fields=None):
    if not name_value:
        return None

    # 1. Пытаемся найти точное совпадение
    row = db.execute(f"SELECT id FROM {table} WHERE {name_column} = ?", (name_value,)).fetchone()
    if row:
        return row["id"]

    # 2. Для преподавателей: если нет точного — ищем по фамилии, если нет — Вакансия
    if table == "teachers":
        search_surname = name_value.split()[0].replace(".", "").lower()
        all_teachers = db.execute(f"SELECT id, {name_column} FROM {table}").fetchall()
        for t in all_teachers:
            db_name = str(t[name_column]).strip()
            if not db_name: continue
            db_surname = db_name.split()[0].replace(".", "").lower()
            if db_surname == search_surname:
                return t["id"]

        # Если не нашли препода — возвращаем ID Вакансии
        row = db.execute("SELECT id FROM teachers WHERE full_name = 'Вакансия'").fetchone()
        return row["id"] if row else None

    # 3. Для ВСЕХ ОСТАЛЬНЫХ (группы, предметы, аудитории) — создаем новую запись, если нет
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


def import_sheet_1(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)
    if "1" not in wb.sheetnames:
        print("Лист '1' не найден!")
        return

    sheet = wb["1"]

    with get_connection() as db:
        current_group = None
        current_date = "2026-09-01"
        rows_added = 0

        for row in sheet.iter_rows(min_row=5, values_only=True):
            group_val = row[0] if len(row) > 0 else None
            if group_val and isinstance(group_val, str):
                clean_group = clean_text(group_val)
                if "-" in clean_group and len(clean_group) < 10:
                    current_group = clean_group.replace(" ", "").upper()

            if not current_group:
                continue

            time_val = row[2] if len(row) > 2 else None
            if not time_val:
                continue

            time_str = clean_text(time_val).replace(" ", "")
            match = re.search(r'(\d{1,2})[:\.](\d{2})\s*[-—]\s*(\d{1,2})[:\.\-](\d{2})', time_str)
            if not match:
                continue

            h1, m1 = int(match.group(1)), int(match.group(2))
            h2, m2 = int(match.group(3)), int(match.group(4))
            start_time = f"{h1:02d}:{m1:02d}"
            end_time = f"{h2:02d}:{m2:02d}"

            if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59:
                continue

            if start_time >= end_time:
                continue

            subject_val = row[3] if len(row) > 3 else None
            subject_name = clean_text(subject_val)
            if not subject_name or subject_name.lower() == "нет":
                continue

            teacher_val = row[4] if len(row) > 4 else None
            teacher_name = clean_text(teacher_val)
            teacher_name = " ".join(teacher_name.split())

            room_val = row[5] if len(row) > 5 else None
            room_name = clean_text(room_val)
            if not room_name:
                room_name = "Не указана"
            else:
                match_room = re.search(r'(\d+|[A-Za-zА-Яа-я]+)$', room_name)
                if match_room:
                    room_name = match_room.group(1)

            course = 1
            match_course = re.search(r'\d', current_group)
            if match_course:
                course = int(match_course.group(0))

            group_id = get_or_create(db, "groups", "name", current_group, {"students_count": 25, "course": course})
            teacher_id = find_teacher_id(db, teacher_name)

            # Если препода нет в базе, find_teacher_id вернул ID Вакансии
            if not teacher_id:
                continue

            requires_pc = 1 if "информат" in subject_name.lower() or "программ" in subject_name.lower() else 0
            lang = detect_language(subject_name)
            subject_id = get_or_create(db, "subjects", "name", subject_name,
                                       {"requires_computers": requires_pc, "language": lang})
            room_id = get_or_create(db, "rooms", "name", room_name, {"capacity": 30, "has_computers": requires_pc})

            existing = db.execute("""
                SELECT id FROM lessons 
                WHERE group_id = ? AND lesson_date = ? AND start_time = ? AND subject_id = ?
            """, (group_id, current_date, start_time, subject_id)).fetchone()

            if existing:
                continue

            try:
                db.execute("""
                    INSERT INTO lessons (group_id, teacher_id, subject_id, room_id, lesson_date, start_time, end_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (group_id, teacher_id, subject_id, room_id, current_date, start_time, end_time))
                rows_added += 1
            except sqlite3.IntegrityError:
                pass

        print(f"Импорт с листа '1' завершен! Добавлено пар: {rows_added}")


if __name__ == "__main__":
    import_sheet_1("расписание на 26-27 уч.год.xlsx")