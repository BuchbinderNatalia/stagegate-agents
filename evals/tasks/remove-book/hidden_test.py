# SPDX-License-Identifier: Apache-2.0
# Hidden acceptance tests: never shown to the agents.
import pytest
from bookshelf import Book, BookNotFoundError, Catalog

DUNE = Book("9780441013593", "Dune", "Frank Herbert", 1965)


def test_remove_returns_book_and_deletes_it() -> None:
    c = Catalog()
    c.add(DUNE)
    assert c.remove(DUNE.isbn) == DUNE
    assert c.get(DUNE.isbn) is None
    assert c.all() == []


def test_remove_unknown_raises_keyerror_subclass() -> None:
    assert issubclass(BookNotFoundError, KeyError)
    with pytest.raises(BookNotFoundError):
        Catalog().remove("missing")


def test_can_re_add_after_remove() -> None:
    c = Catalog()
    c.add(DUNE)
    c.remove(DUNE.isbn)
    c.add(DUNE)
    assert c.get(DUNE.isbn) == DUNE
