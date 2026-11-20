# SPDX-License-Identifier: Apache-2.0
import pytest
from bookshelf import Book, Catalog, InvalidIsbnError


def test_invalid_isbn() -> None:
    with pytest.raises(InvalidIsbnError):
        Catalog().add(Book("9780441013594", "T", "A", 2000))


def test_same_isbn_other_format_is_duplicate() -> None:
    from bookshelf import DuplicateBookError

    c = Catalog()
    c.add(Book("9780441013593", "T", "A", 2000))
    with pytest.raises(DuplicateBookError):
        c.add(Book("978-0-441-01359-3", "T", "A", 2000))
