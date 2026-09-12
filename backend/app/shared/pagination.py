"""Постраничная выдача и сортировка.

Неограниченная выдача не поддерживается ни одним эндпоинтом: запрос
вида `?page_size=1000000` должен отклоняться, а не исполняться
(API.md, раздел 1.1).

Сортировка ограничена списком разрешённых полей. Приём произвольного
имени поля позволил бы влиять на запрос извне.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from app.core.exceptions import ValidationError

ItemT = TypeVar("ItemT")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class PageRequest:
    """Запрос страницы с проверенными параметрами."""

    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    sort_by: str | None = None
    sort_desc: bool = True

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def build_page_request(
    *,
    page: int,
    page_size: int,
    sort_by: str | None,
    sort_desc: bool,
    allowed_sort_fields: frozenset[str],
    default_sort_field: str,
) -> PageRequest:
    """Проверить параметры страницы и сортировки.

    Предел размера страницы применяется отказом, а не молчаливым
    усечением: клиент должен узнать, что его запрос не выполнен так,
    как он рассчитывал.
    """
    if page < 1:
        raise ValidationError(
            "Номер страницы должен быть не меньше 1", details={"page": page}
        )
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ValidationError(
            f"Размер страницы должен быть от 1 до {MAX_PAGE_SIZE}",
            details={"page_size": page_size, "max_page_size": MAX_PAGE_SIZE},
        )

    field = sort_by or default_sort_field
    if field not in allowed_sort_fields:
        raise ValidationError(
            "Сортировка по этому полю не поддерживается",
            details={
                "sort_by": field,
                "allowed": sorted(allowed_sort_fields),
            },
        )

    return PageRequest(page=page, page_size=page_size, sort_by=field, sort_desc=sort_desc)


@dataclass(frozen=True, slots=True)
class Page(Generic[ItemT]):
    """Страница результатов."""

    items: list[ItemT]
    page: int
    page_size: int
    total: int

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total

    @classmethod
    def build(cls, items: list[ItemT], total: int, request: PageRequest) -> Page[ItemT]:
        return cls(
            items=items,
            page=request.page,
            page_size=request.page_size,
            total=total,
        )
