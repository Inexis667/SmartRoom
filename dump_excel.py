import openpyxl


def dump_excel(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)

    # Берем только нужные листы (Пн-Пт)
    target_sheets = ["26год пон", "ВТ 02.09", "ср.03.09", "чт.04.09.25", "пт 05.09."]

    with open("dump.txt", "w", encoding="utf-8") as f:
        for sheet_name in target_sheets:
            if sheet_name not in wb.sheetnames:
                f.write(f"--- Лист {sheet_name} НЕ НАЙДЕН ---\n")
                continue

            f.write(f"\n=== ЛИСТ: {sheet_name} ===\n")
            sheet = wb[sheet_name]

            # Читаем все строки с 12-й
            current_group = "НЕТ"
            current_room = "НЕТ"

            for row in sheet.iter_rows(min_row=12, values_only=True):
                if not row or len(row) < 6:
                    continue

                # Группа
                g = row[0]
                if g and isinstance(g, str) and "-" in g and len(g) < 15:
                    current_group = g.strip()
                    current_room = "НЕТ"

                # Время
                t = row[2]
                if not t:
                    continue

                # Предмет
                s = row[3]
                if not s or str(s).lower() == "нет":
                    continue

                # Препод
                p = row[4]
                if not p:
                    p = "Вакансия"

                # Аудитория
                r = row[5]
                if r:
                    current_room = str(r).strip()
                else:
                    r = current_room

                # Записываем в файл
                f.write(f"{current_group} | {t} | {s} | {p} | {r}\n")

    print("Готово! Данные записаны в файл dump.txt")


if __name__ == "__main__":
    dump_excel("расписание на 26-27 уч.год.xlsx")