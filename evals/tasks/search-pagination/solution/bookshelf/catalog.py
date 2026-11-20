# SPDX-License-Identifier: Apache-2.0
"""Book catalogue: add, find, search and list books."""

from __future__ import annotations

from dataclasses import dataclass


class DuplicateBookError(ValueError):
    """Raised when a book with the same ISBN is already in the catalogue."""


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
        if book.isbn in self._books:
            raise DuplicateBookError(book.isbn)
        self._books[book.isbn] = book

    def get(self, isbn: str) -> Book | None:
        return self._books.get(isbn)

    def search(self, text: str, limit: int | None = None, offset: int = 0) -> list[Book]:
        if offset < 0 or (limit is not None and limit < 0):
            raise ValueError("limit and offset must not be negative")
        needle = text.casefold()
        found = [
            b for b in self.all() if needle in b.title.casefold() or needle in b.author.casefold()
        ]
        end = None if limit is None else offset + limit
        return found[offset:end]

    def all(self) -> list[Book]:
        """Every book, sorted by title then ISBN (stable order for callers and exports)."""
        return sorted(self._books.values(), key=lambda b: (b.title.casefold(), b.isbn))
