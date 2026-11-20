# SPDX-License-Identifier: Apache-2.0
import pytest
from bookshelf import Book, Catalog


def test_by_year() -> None:
    c = Catalog()
    c.add(Book("1", "B", "x", 2000))
    c.add(Book("2", "A", "y", 2000))
    assert [b.isbn for b in c.by_year(1999, 2000)] == ["2", "1"]
    with pytest.raises(ValueError):
        c.by_year(2, 1)
