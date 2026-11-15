import openpyxl
import sqlite3
import re
from database import get_connection


def clean_text(text):
    if not text:
        return ""
    return str(text).strip().replace('\n', ' ')


def find_teacher_id(db, name):
    if not name or name.lower() == "вакансия":
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
    if not name_value:
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


def import_week(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)

    target_sheets = {
        "26год пон": "2026-09-01",
        "ВТ 02.09": "2026-09-02",
        "ср.03.09": "2026-09-03",
        "чт.04.09.25": "2026-09-04",
        "пт 05.09.": "2026-09-05"
    }

    with get_connection() as db:
        for sheet_name, current_date in target_sheets.items():
            if sheet_name not in wb.sheetnames:
                continue

            print(f"Обработка листа: {sheet_name}...")
            sheet = wb[sheet_name]

            # Начинаем читать с 12-й строки (там, где начинаются данные)
            # и идем до конца листа
            current_group = None
            current_room = "Не указана"
            rows_added = 0

            for row in sheet.iter_rows(min_row=12, values_only=True):
                # Проверяем, не пустая ли строка
                if not row or len(row) < 6:
                    continue

                # 1. Группа (колонка A, индекс 0)
                group_cell = row[0]
                if group_cell and isinstance(group_cell, str):
                    clean_group = clean_text(group_cell)
                    # Если это похоже на группу (есть дефис и короткое)
                    if "-" in clean_group and len(clean_group) < 15:
                        current_group = clean_group.replace(" ", "").upper()
                        current_room = "Не указана"  # Сбрасываем аудиторию

                if not current_group:
                    continue

                # 2. Время (колонка C, индекс 2)
                time_cell = row[2]
                if not time_cell:
                    continue

                time_str = clean_text(time_cell).replace(" ", "")
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

                # 3. Предмет (колонка D, индекс 3)
                subject_cell = row[3]
                subject_name = clean_text(subject_cell)
                if not subject_name or subject_name.lower() == "нет":
                    continue

                # 4. Преподаватель (колонка E, индекс 4)
                teacher_cell = row[4]
                teacher_name = clean_text(teacher_cell)
                teacher_name = " ".join(teacher_name.split())

                # 5. Аудитория (колонка F, индекс 5)
                room_cell = row[5]
                room_name = clean_text(room_cell)

                if room_name:
                    # Берем только цифры в конце (например, "0 эт.каб.05" -> "05")
                    match_room = re.search(r'(\d+|[A-Za-zА-Яа-я]+)$', room_name)
                    if match_room:
                        current_room = match_room.group(1)
                else:
                    # Если пусто, берем из памяти
                    room_name = current_room

                course = 1
                match_course = re.search(r'\d', current_group)
                if match_course:
                    course = int(match_course.group(0))

                group_id = get_or_create(db, "groups", "name", current_group, {"students_count": 25, "course": course})
                teacher_id = find_teacher_id(db, teacher_name)
                if not teacher_id:
                    continue

                requires_pc = 1 if "информат" in subject_name.lower() or "программ" in subject_name.lower() else 0
                lang = detect_language(subject_name)
                subject_id = get_or_create(db, "subjects", "name", subject_name,
                                           {"requires_computers": requires_pc, "language": lang})
                room_id = get_or_create(db, "rooms", "name", room_name, {"capacity": 30, "has_computers": requires_pc})

                # Проверка на дубликат (группа + дата + время)
                existing = db.execute("""
                    SELECT id FROM lessons 
                    WHERE group_id = ? AND lesson_date = ? AND start_time = ?
                """, (group_id, current_date, start_time)).fetchone()

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

            print(f"  -> Добавлено пар: {rows_added}")

        print("Импорт с листов Пн-Пт завершен!")


if __name__ == "__main__":
    import_week("расписание на 26-27 уч.год.xlsx")