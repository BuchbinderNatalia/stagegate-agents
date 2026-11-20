# SPDX-License-Identifier: Apache-2.0
from bookshelf import Book, Catalog
from bookshelf.export import to_csv


# AC-1 [unit]: header row and one row per book, sorted like Catalog.all()
def test_rows_sorted_with_header() -> None:
    c = Catalog()
    c.add(Book("2", "Emma", "Jane Austen", 1815))
    c.add(Book("1", "Dune", "Frank Herbert", 1965))
    assert to_csv(c).splitlines() == [
        "isbn,title,author,year",
        "1,Dune,Frank Herbert,1965",
        "2,Emma,Jane Austen,1815",
    ]


# AC-2 [unit]: empty catalogue exports only the header
def test_empty_catalog() -> None:
    assert to_csv(Catalog()) == "isbn,title,author,year\n"


# AC-3 [unit]: commas and quotes are escaped
def test_escaping() -> None:
    c = Catalog()
    c.add(Book("3", 'Say "Hi", World', "A, B", 2000))
    assert to_csv(c).splitlines()[1] == '3,"Say ""Hi"", World","A, B",2000'
