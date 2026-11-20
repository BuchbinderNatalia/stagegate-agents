# SPDX-License-Identifier: Apache-2.0
from bookshelf import Book, Catalog


def test_page() -> None:
    c = Catalog()
    for i in range(3):
        c.add(Book(str(i), f"T{i}", "A", 2000))
    assert [b.isbn for b in c.search("t", limit=1, offset=1)] == ["1"]
