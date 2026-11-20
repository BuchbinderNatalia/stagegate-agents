# SPDX-License-Identifier: Apache-2.0
# Hidden acceptance tests: never shown to the agents.
from bookshelf import Book, Catalog
from bookshelf.export import to_csv


def test_header_and_rows_in_order() -> None:
    c = Catalog()
    c.add(Book("2", "Emma", "Jane Austen", 1815))
    c.add(Book("1", "Dune", "Frank Herbert", 1965))
    assert to_csv(c).splitlines() == [
        "isbn,title,author,year",
        "1,Dune,Frank Herbert,1965",
        "2,Emma,Jane Austen,1815",
    ]


def test_empty_catalogue() -> None:
    assert to_csv(Catalog()) == "isbn,title,author,year\n"


def test_escaping() -> None:
    c = Catalog()
    c.add(Book("3", 'Say "Hi", World', "A, B", 2000))
    assert to_csv(c).splitlines()[1] == '3,"Say ""Hi"", World","A, B",2000'


def test_same_title_ordered_by_isbn() -> None:
    c = Catalog()
    c.add(Book("b", "Same", "X", 1))
    c.add(Book("a", "Same", "Y", 2))
    assert [line.split(",")[0] for line in to_csv(c).splitlines()[1:]] == ["a", "b"]
