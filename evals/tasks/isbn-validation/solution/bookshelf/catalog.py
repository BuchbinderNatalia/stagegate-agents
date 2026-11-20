# SPDX-License-Identifier: Apache-2.0
"""Book catalogue: add, find, search and list books."""

from __future__ import annotations

from dataclasses import dataclass


class DuplicateBookError(ValueError):
    """Raised when a book with the same ISBN is already in the catalogue."""


class InvalidIsbnError(ValueError):
    """Raised when an ISBN is not a valid ISBN-13."""


def is_valid_isbn13(isbn: str) -> bool:
    digits = isbn.replace("-", "").replace(" ", "")
    if len(digits) != 13 or not digits.isdigit():
        return False
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:12]))
    return (10 - total % 10) % 10 == int(digits[12])


@dataclass(frozen=True)
class Book:
    isbn: str
    title: str
    author: str
    year: int


class Catalog:
    def __init__(self) -> None:
        self._books: dict[str, Book] = {}

    def add(self, book: Book) -> None:
        if not book.isbn.strip():
            raise ValueError("isbn must not be empty")
        if not is_valid_isbn13(book.isbn):
            raise InvalidIsbnError(book.isbn)
        if book.isbn in self._books:
            raise DuplicateBookError(book.isbn)
        self._books[book.isbn] = book

    def get(self, isbn: str) -> Book | None:
        return self._books.get(isbn)

    def search(self, text: str) -> list[Book]:
        needle = text.casefold()
        return [
            b for b in self.all() if needle in b.title.casefold() or needle in b.author.casefold()
        ]

    def all(self) -> list[Book]:
        """Every book, sorted by title then ISBN (stable order for callers and exports)."""
        return sorted(self._books.values(), key=lambda b: (b.title.casefold(), b.isbn))
