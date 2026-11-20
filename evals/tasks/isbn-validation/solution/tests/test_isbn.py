# SPDX-License-Identifier: Apache-2.0
import pytest
from bookshelf import Book, Catalog, InvalidIsbnError


def test_invalid_isbn() -> None:
    with pytest.raises(InvalidIsbnError):
        Catalog().add(Book("9780441013594", "T", "A", 2000))
