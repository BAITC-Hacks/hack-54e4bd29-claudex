"""Разбор книг Excel в режиме только для чтения.

openpyxl открывается с read_only=True: книга не перезаписывается и не
держится в памяти целиком. Отдельно фиксируются особенности вёрстки —
объединённые ячейки, пустые верхние строки, формулы, несколько таблиц на
одном листе. Такие книги нельзя принимать в pipeline как обычную таблицу,
и проблема должна быть видна в отчёте, а не всплыть при загрузке.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet._read_only import ReadOnlyWorksheet

# Сколько верхних строк осматривается в поисках строки заголовков.
HEADER_SCAN_ROWS = 25
# Сколько строк просматривается для поиска формул и разрывов таблиц.
BODY_SCAN_ROWS = 400


@dataclass(slots=True)
class SheetProfile:
    sheet_name: str
    used_rows: int
    used_columns: int
    header_row_index: int | None
    headers: list[str]
    leading_empty_rows: int
    merged_ranges: int
    formula_cells: int
    blank_separator_rows: list[int] = field(default_factory=list)
    likely_multiple_tables: bool = False
    looks_like_reference: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WorkbookProfile:
    dataset: str
    file: str
    size_bytes: int
    sheet_count: int
    sheets: list[SheetProfile]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["sheets"] = [asdict(s) for s in self.sheets]
        return payload


def _row_is_empty(row: tuple[object, ...]) -> bool:
    return all(cell is None or str(cell).strip() == "" for cell in row)


def _profile_sheet(sheet: ReadOnlyWorksheet, has_formulas: bool) -> SheetProfile:
    rows = list(sheet.iter_rows(max_row=HEADER_SCAN_ROWS, values_only=True))

    leading_empty = 0
    for row in rows:
        if _row_is_empty(row):
            leading_empty += 1
        else:
            break

    header_index: int | None = None
    headers: list[str] = []
    if leading_empty < len(rows):
        header_index = leading_empty + 1
        headers = [
            str(cell).strip() if cell is not None else "" for cell in rows[leading_empty]
        ]
        while headers and headers[-1] == "":
            headers.pop()

    blank_rows: list[int] = []
    formula_cells = 0
    for index, row in enumerate(
        sheet.iter_rows(max_row=BODY_SCAN_ROWS, values_only=True), start=1
    ):
        if index > leading_empty + 1 and _row_is_empty(row):
            blank_rows.append(index)
        if has_formulas:
            formula_cells += sum(
                1 for cell in row if isinstance(cell, str) and cell.startswith("=")
            )

    notes: list[str] = []
    if leading_empty:
        notes.append(
            f"перед заголовками {leading_empty} пустых строк: "
            "строка заголовка не первая"
        )
    if not headers:
        notes.append("строку заголовков определить не удалось")
    if any(h == "" for h in headers):
        notes.append("часть заголовков пуста: вероятны объединённые ячейки шапки")

    merged = len(getattr(sheet, "merged_cells", []) or [])
    if merged:
        notes.append(
            f"объединённых диапазонов: {merged}; прямое чтение как таблицы "
            "даст пропуски в заголовках"
        )

    # Пустая строка в середине листа чаще всего разделяет две таблицы.
    interior_blanks = [r for r in blank_rows if r < (sheet.max_row or 0)]
    multiple_tables = len(interior_blanks) > 1

    used_rows = int(sheet.max_row or 0)
    used_columns = int(sheet.max_column or 0)
    reference = used_rows <= 200 and used_columns <= 5

    return SheetProfile(
        sheet_name=sheet.title,
        used_rows=used_rows,
        used_columns=used_columns,
        header_row_index=header_index,
        headers=headers,
        leading_empty_rows=leading_empty,
        merged_ranges=merged,
        formula_cells=formula_cells,
        blank_separator_rows=interior_blanks[:20],
        likely_multiple_tables=multiple_tables,
        looks_like_reference=reference,
        notes=notes,
    )


def profile_workbook(dataset: str, path: Path) -> WorkbookProfile:
    """Описать книгу, не изменяя её."""
    notes: list[str] = []
    sheets: list[SheetProfile] = []

    # Два открытия: со значениями (для данных) и с формулами (чтобы
    # отличить вычисляемый столбец от введённого вручную).
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        formula_book = load_workbook(path, read_only=True, data_only=False)
    except (OSError, ValueError):  # pragma: no cover — защита от битой книги
        formula_book = None
        notes.append("Формулы прочитать не удалось; отчёт построен по значениям")

    try:
        for sheet in workbook.worksheets:
            formula_sheet = (
                formula_book[sheet.title]
                if formula_book is not None and sheet.title in formula_book.sheetnames
                else None
            )
            profile = _profile_sheet(sheet, has_formulas=False)
            if formula_sheet is not None:
                with_formulas = _profile_sheet(formula_sheet, has_formulas=True)
                profile.formula_cells = with_formulas.formula_cells
                if profile.formula_cells:
                    profile.notes.append(
                        f"ячеек с формулами: {profile.formula_cells}; "
                        "значения вычисляемые, а не исходные"
                    )
            sheets.append(profile)
    finally:
        workbook.close()
        if formula_book is not None:
            formula_book.close()

    if len(sheets) > 1:
        notes.append(
            "В книге несколько листов: каждый требует отдельного контракта " "загрузки"
        )

    return WorkbookProfile(
        dataset=dataset,
        file=path.name,
        size_bytes=path.stat().st_size,
        sheet_count=len(sheets),
        sheets=sheets,
        notes=notes,
    )
