# SPDX-License-Identifier: Apache-2.0
import pytest
from bookshelf import Book, BookNotFoundError, Catalog


def test_remove() -> None:
    c = Catalog()
    b = Book("9780441013593", "Dune", "Frank Herbert", 1965)
    c.add(b)
    assert c.remove(b.isbn) == b and c.all() == []


def test_remove_missing() -> None:
    with pytest.raises(BookNotFoundError):
        Catalog().remove("x")
