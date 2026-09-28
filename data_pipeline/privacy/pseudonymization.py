"""Псевдонимизация идентификаторов.

Применяется HMAC-SHA256 с секретом из окружения, а не обычный SHA-256.
Причина конкретная: код случая госпитализации имеет предсказуемую
структуру «регион.организация.профиль.номер», и пространство возможных
значений мало. Обычный хеш такого значения подбирается перебором за
минуты, то есть не защищает ничего. Секрет делает перебор бесполезным
для того, у кого его нет.

Псевдоним детерминирован: одно и то же значение при одном и том же
секрете даёт один и тот же результат. Без этого нельзя было бы связать
записи одного случая между поставками. Смена секрета обрывает эту связь,
и это осознанная цена: секрет меняют, когда его считают
скомпрометированным, а сохранять связуемость с утёкшим ключом
бессмысленно.

Модуль не пишет секрет ни в журнал, ни в исключение, ни в отчёт.
"""

from __future__ import annotations

import hashlib
import hmac
import unicodedata
from dataclasses import dataclass

# Длина псевдонима в шестнадцатеричных знаках. 32 знака — это 128 бит:
# столкновений на масштабе миллионов записей не ожидается, а строка
# вдвое короче полного SHA-256.
PSEUDONYM_LENGTH = 32

MIN_KEY_LENGTH = 32

# Значения, встречавшиеся в примерах конфигурации. Ни одно из них
# не является секретом и не должно им притворяться.
INSECURE_KEYS: frozenset[str] = frozenset(
    {
        "",
        "change_me",
        "changeme",
        "secret",
        "local_dev_only",
        "medsignal",
    }
)


class InsecurePseudonymizationKeyError(Exception):
    """Ключ псевдонимизации отсутствует или непригоден.

    Сообщение никогда не содержит самого значения ключа.
    """


def validate_key(key: str, *, allow_short: bool = False) -> None:
    """Проверить пригодность ключа. Значение ключа наружу не попадает."""
    if key.strip().lower() in INSECURE_KEYS:
        raise InsecurePseudonymizationKeyError(
            "DATA_PSEUDONYMIZATION_KEY не задан или содержит значение "
            "из примера конфигурации"
        )
    if not allow_short and len(key) < MIN_KEY_LENGTH:
        raise InsecurePseudonymizationKeyError(
            f"DATA_PSEUDONYMIZATION_KEY короче {MIN_KEY_LENGTH} символов"
        )


def normalize_identifier(value: str) -> str:
    """Привести идентификатор к каноническому виду перед хешированием.

    Без этого «61.01W9.321.72S» и « 61.01w9.321.72s » дали бы разные
    псевдонимы, то есть один случай выглядел бы двумя.
    """
    return unicodedata.normalize("NFKC", value).strip().upper()


@dataclass(frozen=True, slots=True)
class Pseudonymizer:
    """Построитель псевдонимов. Секрет остаётся внутри объекта."""

    _key: bytes

    @classmethod
    def from_secret(cls, key: str, *, allow_short: bool = False) -> Pseudonymizer:
        validate_key(key, allow_short=allow_short)
        return cls(_key=key.encode("utf-8"))

    def pseudonymize(self, value: str) -> str:
        digest = hmac.new(
            self._key, normalize_identifier(value).encode("utf-8"), hashlib.sha256
        )
        return digest.hexdigest()[:PSEUDONYM_LENGTH]

    def pseudonymize_parts(self, *parts: str | None) -> str:
        """Псевдоним составного идентификатора.

        Части соединяются разделителем, который не встречается в данных.
        Простая склейка позволила бы разным наборам частей дать одну
        строку и, значит, один псевдоним на двух разных людей.
        """
        joined = "\x1f".join((part or "") for part in parts)
        return self.pseudonymize(joined)

    def __repr__(self) -> str:  # pragma: no cover — защита от печати секрета
        return "Pseudonymizer(<секрет скрыт>)"

    def __str__(self) -> str:  # pragma: no cover
        return self.__repr__()
