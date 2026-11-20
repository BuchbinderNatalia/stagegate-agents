# SPDX-License-Identifier: Apache-2.0
"""Book catalogue: add, find, search and list books."""

from __future__ import annotations

from dataclasses import dataclass


class DuplicateBookError(ValueError):
    """Raised when a book with the same ISBN is already in the catalogue."""


class BookNotFoundError(KeyError):
    """Raised when no book has the requested ISBN."""


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

    def remove(self, isbn: str) -> Book:
        try:
            return self._books.pop(isbn)
        except KeyError:
            raise BookNotFoundError(isbn) from None

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
