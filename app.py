import sqlite3
import re
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, abort, session
from werkzeug.security import generate_password_hash, check_password_hash

from database import init_db, get_connection

app = Flask(__name__)
app.secret_key = 'super_secret_key_12345'  # Обязательно для сессий (можно любую строку)
init_db()

# --- ПАРОЛЬ АДМИНИСТРАТОРА ---
# Логин: admin
# Пароль: admin123 (в реальной жизни это не пишут в коде, но для защиты проекта пойдет)
ADMIN_LOGIN = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("admin123")


# Проверка: если в сессии нет ключа admin, значит пользователь — гость
@app.context_processor
def inject_readonly():
    is_admin = session.get('is_admin', False)
    return dict(is_readonly=not is_admin)


# Блокировка POST-запросов, если пользователь не авторизован
@app.before_request
def restrict_access():
    # Пропускаем страницы входа/выхода и статические файлы
    if request.path.startswith('/static/') or request.path in ['/login', '/logout']:
        return

    # Если это не админ и запрос на изменение (POST) — запрещаем
    if not session.get('is_admin') and request.method == "POST":
        abort(403, description="Вы не авторизованы. Войдите как администратор.")


# --- АВТОРИЗАЦИЯ ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if username == ADMIN_LOGIN and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['is_admin'] = True
            return redirect(url_for("index"))
        else:
            return "Неверный логин или пароль", 403

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop('is_admin', None)
    return redirect(url_for("index"))

@app.template_filter('to_date_weekday')
def to_date_weekday(date_str):
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.weekday()
    except Exception:
        return 0


@app.errorhandler(400)
def handle_bad_request(e):
    return render_template("error.html", message=e.description), 400


@app.route("/")
def index():
    with get_connection() as db:
        rooms_count = db.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        groups_count = db.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
        teachers_count = db.execute("SELECT COUNT(*) FROM teachers").fetchone()[0]
    return render_template(
        "index.html",
        rooms_count=rooms_count,
        groups_count=groups_count,
        teachers_count=teachers_count,
    )


# --- УПРАВЛЕНИЕ АУДИТОРИЯМИ ---

@app.route("/rooms")
def rooms():
    search = request.args.get("search", "").strip()
    floor_filter = request.args.get("floor", "")

    with get_connection() as db:
        query = "SELECT * FROM rooms WHERE 1=1"
        params = []

        if search:
            query += " AND name LIKE ?"
            params.append(f"%{search}%")

        if floor_filter:
            query += " AND CAST(SUBSTR(name, 1, 1) AS INTEGER) = ?"
            params.append(int(floor_filter))

        query += " ORDER BY name"

        all_rooms = db.execute(query, params).fetchall()

    return render_template("rooms.html", rooms=all_rooms, search=search, current_floor=floor_filter)


@app.route("/rooms/add", methods=["POST"])
def add_room():
    name = request.form.get("name", "").strip()
    has_board = 1 if request.form.get("has_board") == "on" else 0
    has_projector = 1 if request.form.get("has_projector") == "on" else 0

    try:
        capacity = int(request.form.get("capacity", "0"))
    except ValueError:
        return "Вместимость должна быть числом.", 400

    if not name or capacity <= 0:
        return "Проверьте введённые данные.", 400

    with get_connection() as db:
        try:
            db.execute(
                "INSERT INTO rooms (name, capacity, has_board, has_projector) VALUES (?, ?, ?, ?)",
                (name, capacity, has_board, has_projector)
            )
        except sqlite3.IntegrityError:
            return "Аудитория с таким номером уже существует.", 400

    return redirect(url_for("rooms"))

@app.route("/rooms/delete/<int:room_id>", methods=["POST"])
def delete_room(room_id):
    with get_connection() as db:
        try:
            db.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        except sqlite3.IntegrityError:
            return "Нельзя удалить аудиторию, к которой привязаны занятия.", 400
    return redirect(url_for("rooms"))


@app.route("/rooms/edit/<int:room_id>", methods=["GET"])
def edit_room(room_id):
    with get_connection() as db:
        room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if not room:
        return "Аудитория не найдена", 404
    return render_template("room_edit.html", room=room)


@app.route("/rooms/edit/<int:room_id>", methods=["POST"])
def update_room(room_id):
    name = request.form.get("name", "").strip()
    has_board = 1 if request.form.get("has_board") == "on" else 0
    has_projector = 1 if request.form.get("has_projector") == "on" else 0

    try:
        capacity = int(request.form.get("capacity", "0"))
    except ValueError:
        return "Вместимость должна быть числом.", 400

    if not name or capacity <= 0:
        return "Проверьте введённые данные.", 400

    with get_connection() as db:
        try:
            db.execute("""
                UPDATE rooms 
                SET name = ?, capacity = ?, has_board = ?, has_projector = ?
                WHERE id = ?
            """, (name, capacity, has_board, has_projector, room_id))
        except sqlite3.IntegrityError:
            return "Аудитория с таким номером уже существует.", 400

    return redirect(url_for("rooms"))


@app.route("/rooms/<int:room_id>/view")
def view_room(room_id):
    with get_connection() as db:
        room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if not room:
            return "Аудитория не найдена", 404

        seats_rows = db.execute("SELECT * FROM seats WHERE room_id = ? ORDER BY id", (room_id,)).fetchall()

        seats = []
        for row in seats_rows:
            seats.append({
                "id": row["id"],
                "seat_number": row["seat_number"],
                "type": row["type"],
                "pos_x": row["pos_x"],
                "pos_y": row["pos_y"], # <--- ДОБАВИЛИ ЭТУ СТРОКУ
                "pos_z": row["pos_z"] if "pos_z" in row.keys() else 0,
                "rotation": row["rotation"] if "rotation" in row.keys() else 0
            })

    return render_template("room_view.html", room=room, seats=seats)


@app.route("/rooms/<int:room_id>/seats/save", methods=["POST"])
def save_seats(room_id):
    data = request.json
    with get_connection() as db:
        db.execute("DELETE FROM seats WHERE room_id = ?", (room_id,))

        for item in data:
            db.execute("""
                INSERT INTO seats (room_id, seat_number, type, pos_x, pos_y, pos_z, rotation)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (room_id, item['number'], item['type'], item['x'], item['y'], item.get('z', 0),
                  item.get('rotation', 0)))

    return {"status": "ok"}

@app.route("/rooms/<int:room_id>/seats/edit")
def edit_seats(room_id):
    with get_connection() as db:
        room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if not room:
            return "Аудитория не найдена", 404
        seats = db.execute("SELECT * FROM seats WHERE room_id = ? ORDER BY id", (room_id,)).fetchall()
    return render_template("room_seats_edit.html", room=room, seats=seats)


@app.route("/rooms/<int:room_id>/seats/add", methods=["POST"])
def add_seat(room_id):
    seat_number = request.form.get("seat_number", "").strip()
    has_socket = 1 if request.form.get("has_socket") == "on" else 0
    is_computer = 1 if request.form.get("is_computer") == "on" else 0

    if not seat_number:
        return "Введите номер места.", 400

    with get_connection() as db:
        db.execute("""
            INSERT INTO seats (room_id, seat_number, has_socket, is_computer)
            VALUES (?, ?, ?, ?)
        """, (room_id, seat_number, has_socket, is_computer))
    return redirect(url_for("edit_seats", room_id=room_id))


@app.route("/rooms/<int:room_id>/seats/delete/<int:seat_id>", methods=["POST"])
def delete_seat(room_id, seat_id):
    with get_connection() as db:
        db.execute("DELETE FROM seats WHERE id = ? AND room_id = ?", (seat_id, room_id))
    return redirect(url_for("edit_seats", room_id=room_id))

# --- УПРАВЛЕНИЕ ГРУППАМИ ---

@app.route("/groups")
def groups():
    course_filter = request.args.get("course", "")
    search = request.args.get("search", "").strip()

    with get_connection() as db:
        query = "SELECT * FROM groups WHERE 1=1"
        params = []

        if course_filter:
            query += " AND course = ?"
            params.append(int(course_filter))

        if search:
            query += " AND name LIKE ?"
            params.append(f"%{search}%")

        query += " ORDER BY course ASC, CAST(REPLACE(SUBSTR(name, INSTR(name, '-') + 1), ' ', '') AS INTEGER) ASC"

        all_groups = db.execute(query, params).fetchall()

    return render_template("groups.html", groups=all_groups, current_course=course_filter, search=search)


@app.route("/groups/add", methods=["POST"])
def add_group():
    name = request.form.get("name", "").strip()
    try:
        students_count = int(request.form.get("students_count", "0"))
    except ValueError:
        return "Количество студентов должно быть числом.", 400

    if not name or students_count <= 0:
        return "Проверьте введённые данные.", 400

    course = 1
    match = re.search(r'\d', name)
    if match:
        course = int(match.group(0))

    with get_connection() as db:
        try:
            db.execute("INSERT INTO groups (name, students_count, course) VALUES (?, ?, ?)",
                       (name, students_count, course))
        except sqlite3.IntegrityError:
            return "Группа с таким названием уже существует.", 400
    return redirect(url_for("groups"))


@app.route("/groups/delete/<int:group_id>", methods=["POST"])
def delete_group(group_id):
    with get_connection() as db:
        try:
            db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        except sqlite3.IntegrityError:
            return "Нельзя удалить группу, к которой привязаны занятия в расписании.", 400
    return redirect(url_for("groups"))

@app.route("/groups/edit/<int:group_id>", methods=["GET"])
def edit_group(group_id):
    with get_connection() as db:
        group = db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        return "Группа не найдена", 404
    return render_template("group_edit.html", group=group)


@app.route("/groups/edit/<int:group_id>", methods=["POST"])
def update_group(group_id):
    name = request.form.get("name", "").strip()
    try:
        students_count = int(request.form.get("students_count", "0"))
    except ValueError:
        return "Количество студентов должно быть числом.", 400

    if not name or students_count <= 0:
        return "Проверьте введённые данные.", 400

    # Пересчитываем курс при изменении названия
    course = 1
    match = re.search(r'\d', name)
    if match:
        course = int(match.group(0))

    with get_connection() as db:
        try:
            db.execute("""
                UPDATE groups 
                SET name = ?, students_count = ?, course = ?
                WHERE id = ?
            """, (name, students_count, course, group_id))
        except sqlite3.IntegrityError:
            return "Группа с таким названием уже существует.", 400

    return redirect(url_for("groups"))


# --- УПРАВЛЕНИЕ ПРЕПОДАВАТЕЛЯМИ ---

@app.route("/teachers")
def teachers():
    search = request.args.get("search", "").strip()
    with get_connection() as db:
        if search:
            all_teachers = db.execute("SELECT * FROM teachers WHERE full_name LIKE ? ORDER BY full_name", (f"%{search}%",)).fetchall()
        else:
            all_teachers = db.execute("SELECT * FROM teachers ORDER BY full_name").fetchall()
    return render_template("teachers.html", teachers=all_teachers, search=search)


@app.route("/teachers/add", methods=["POST"])
def add_teacher():
    full_name = request.form.get("full_name", "").strip()
    if not full_name:
        return "Введите имя преподавателя.", 400

    with get_connection() as db:
        db.execute("INSERT INTO teachers (full_name) VALUES (?)", (full_name,))
    return redirect(url_for("teachers"))


@app.route("/teachers/delete/<int:teacher_id>", methods=["POST"])
def delete_teacher(teacher_id):
    with get_connection() as db:
        try:
            db.execute("DELETE FROM teachers WHERE id = ?", (teacher_id,))
        except sqlite3.IntegrityError:
            return "Нельзя удалить преподавателя, у которого есть занятия в расписании.", 400
    return redirect(url_for("teachers"))


# --- УПРАВЛЕНИЕ ПРЕДМЕТАМИ ---

@app.route("/subjects")
def subjects():
    search = request.args.get("search", "").strip()
    with get_connection() as db:
        # Сложная сортировка: сначала всё, что НЕ начинается с ПМ/КМ/БМ/ООМ, потом остальные
        query = """
            SELECT * FROM subjects 
            WHERE name LIKE ?
            ORDER BY 
                CASE 
                    WHEN name LIKE 'ПМ%' OR name LIKE 'КМ%' OR name LIKE 'БМ%' OR name LIKE 'ООМ%' THEN 1 
                    ELSE 0 
                END,
                name ASC
        """
        all_subjects = db.execute(query, (f"%{search}%",)).fetchall()
    return render_template("subjects.html", subjects=all_subjects, search=search)


@app.route("/subjects/add", methods=["POST"])
def add_subject():
    name = request.form.get("name", "").strip()
    requires_board = 1 if request.form.get("requires_board") == "on" else 0
    requires_projector = 1 if request.form.get("requires_projector") == "on" else 0
    language = request.form.get("language", "ru")

    if not name:
        return "Введите название предмета.", 400

    with get_connection() as db:
        try:
            db.execute(
                "INSERT INTO subjects (name, requires_board, requires_projector, language) VALUES (?, ?, ?, ?)",
                (name, requires_board, requires_projector, language)
            )
        except sqlite3.IntegrityError:
            return "Такой предмет уже существует.", 400
    return redirect(url_for("subjects"))


@app.route("/subjects/delete/<int:subject_id>", methods=["POST"])
def delete_subject(subject_id):
    with get_connection() as db:
        try:
            db.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
        except sqlite3.IntegrityError:
            return "Нельзя удалить предмет, который привязан к занятиям.", 400
    return redirect(url_for("subjects"))

@app.route("/subjects/edit/<int:subject_id>", methods=["GET"])
def edit_subject(subject_id):
    with get_connection() as db:
        subject = db.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    if not subject:
        return "Предмет не найден", 404
    return render_template("subject_edit.html", subject=subject)


@app.route("/subjects/edit/<int:subject_id>", methods=["POST"])
def update_subject(subject_id):
    name = request.form.get("name", "").strip()
    requires_board = 1 if request.form.get("requires_board") == "on" else 0
    requires_projector = 1 if request.form.get("requires_projector") == "on" else 0
    language = request.form.get("language", "ru")

    if not name:
        return "Введите название предмета.", 400

    with get_connection() as db:
        try:
            db.execute("""
                UPDATE subjects 
                SET name = ?, requires_board = ?, requires_projector = ?, language = ?
                WHERE id = ?
            """, (name, requires_board, requires_projector, language, subject_id))
        except sqlite3.IntegrityError:
            return "Такой предмет уже существует.", 400

    return redirect(url_for("subjects"))

# --- РАСПИСАНИЕ ---

def has_conflict(db, lesson_date, start_time, end_time, field, value):
    allowed_fields = {"room_id", "group_id", "teacher_id"}
    if field not in allowed_fields:
        raise ValueError("Недопустимое поле")

    query = f"""
        SELECT id FROM lessons
        WHERE lesson_date = ?
          AND {field} = ?
          AND start_time < ?
          AND end_time > ?
    """
    result = db.execute(query, (lesson_date, value, end_time, start_time)).fetchone()
    return result is not None


@app.route("/schedule")
def schedule():
    group_filter = request.args.get("group", "")
    teacher_filter = request.args.get("teacher", "")

    with get_connection() as db:
        groups = db.execute("SELECT * FROM groups ORDER BY name").fetchall()
        teachers = db.execute("SELECT * FROM teachers ORDER BY full_name").fetchall()
        subjects = db.execute("SELECT * FROM subjects ORDER BY name").fetchall()
        rooms = db.execute("SELECT * FROM rooms WHERE is_available = 1 ORDER BY name").fetchall()

        query = """
            SELECT 
                lessons.*, 
                groups.name AS group_name, 
                teachers.full_name AS teacher_name, 
                subjects.name AS subject_name, 
                rooms.name AS room_name,
                CAST(strftime('%w', lesson_date) AS INTEGER) as weekday
            FROM lessons
            JOIN groups ON groups.id = lessons.group_id
            JOIN teachers ON teachers.id = lessons.teacher_id
            JOIN subjects ON subjects.id = lessons.subject_id
            JOIN rooms ON rooms.id = lessons.room_id
            WHERE CAST(strftime('%w', lesson_date) AS INTEGER) BETWEEN 1 AND 5
        """

        conditions = []
        params = []

        if group_filter:
            conditions.append("groups.name = ?")
            params.append(group_filter)
        if teacher_filter:
            conditions.append("teachers.full_name = ?")
            params.append(teacher_filter)

        if conditions:
            query += " AND " + " AND ".join(conditions)

        query += " ORDER BY weekday ASC, groups.name ASC, start_time ASC"

        lessons = db.execute(query, params).fetchall()

    return render_template("schedule.html",
                           groups=groups,
                           teachers=teachers,
                           subjects=subjects,
                           rooms=rooms,
                           lessons=lessons,
                           current_group=group_filter,
                           current_teacher=teacher_filter)

@app.route("/schedule/add", methods=["POST"])
def add_lesson():
    group_id = request.form.get("group_id")
    teacher_id = request.form.get("teacher_id")
    subject_id = request.form.get("subject_id")
    room_id = request.form.get("room_id")
    lesson_date = request.form.get("lesson_date")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")

    if not all([group_id, teacher_id, subject_id, room_id, lesson_date, start_time, end_time]):
        return "Заполните все поля.", 400

    if start_time >= end_time:
        return "Время начала должно быть раньше времени окончания.", 400

    with get_connection() as db:
        if has_conflict(db, lesson_date, start_time, end_time, "group_id", group_id):
            return "Конфликт: у этой группы уже есть занятие в это время.", 400
        if has_conflict(db, lesson_date, start_time, end_time, "teacher_id", teacher_id):
            return "Конфликт: этот преподаватель уже занят в это время.", 400
        if has_conflict(db, lesson_date, start_time, end_time, "room_id", room_id):
            return "Конфликт: эта аудитория уже занята в это время.", 400

        room = db.execute("SELECT capacity, has_board, has_projector FROM rooms WHERE id = ?", (room_id,)).fetchone()
        group = db.execute("SELECT students_count FROM groups WHERE id = ?", (group_id,)).fetchone()
        subject = db.execute("SELECT requires_board, requires_projector FROM subjects WHERE id = ?", (subject_id,)).fetchone()

        if room["capacity"] < group["students_count"]:
            return f"Ошибка: вместимость аудитории ({room['capacity']}) меньше, чем студентов в группе ({group['students_count']}).", 400

        if subject["requires_board"] and not room["has_board"]:
            return "Ошибка: для этого предмета требуется доска, а в аудитории её нет.", 400

        if subject["requires_projector"] and not room["has_projector"]:
            return "Ошибка: для этого предмета требуется проектор, а в аудитории его нет.", 400


@app.route("/schedule/delete/<int:lesson_id>", methods=["POST"])
def delete_lesson(lesson_id):
    with get_connection() as db:
        db.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    return redirect(url_for("schedule"))


# --- СВОБОДНЫЕ АУДИТОРИИ ---

@app.route("/free-rooms")
def free_rooms():
    return render_template("free_rooms.html")


@app.route("/free-rooms/search", methods=["POST"])
def search_free_rooms():
    lesson_date = request.form.get("lesson_date")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")
    students_count = request.form.get("students_count", 0)
    requires_computers = 1 if request.form.get("requires_computers") == "on" else 0

    if not lesson_date or not start_time or not end_time:
        return "Заполните дату и время.", 400
    if start_time >= end_time:
        return "Время начала должно быть раньше времени окончания.", 400

    try:
        students_count = int(students_count)
    except ValueError:
        students_count = 0

    with get_connection() as db:
        query = """
            SELECT * FROM rooms
            WHERE is_available = 1
              AND capacity >= ?
              AND (? = 0 OR has_computers = 1)
              AND id NOT IN (
                  SELECT room_id FROM lessons
                  WHERE lesson_date = ?
                    AND start_time < ?
                    AND end_time > ?
              )
            ORDER BY capacity ASC, name ASC
        """
        free = db.execute(query, (students_count, requires_computers, lesson_date, end_time, start_time)).fetchall()

    return render_template("free_rooms.html",
                           free_rooms=free,
                           lesson_date=lesson_date,
                           start_time=start_time,
                           end_time=end_time,
                           students_count=students_count,
                           requires_computers=requires_computers)


# --- СТАТИСТИКА ---

@app.route("/stats")
def stats():
    with get_connection() as db:
        query = """
            SELECT 
                rooms.name,
                COUNT(lessons.id) AS lesson_count
            FROM rooms
            LEFT JOIN lessons ON lessons.room_id = rooms.id
            GROUP BY rooms.id
            ORDER BY lesson_count DESC
        """
        data = db.execute(query).fetchall()
        room_names = [row["name"] for row in data]
        lesson_counts = [row["lesson_count"] for row in data]

    return render_template("stats.html", room_names=room_names, lesson_counts=lesson_counts)


if __name__ == "__main__":
    app.run(debug=True)
