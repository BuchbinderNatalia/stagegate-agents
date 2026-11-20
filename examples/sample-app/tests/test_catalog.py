# SPDX-License-Identifier: Apache-2.0
import pytest

from bookshelf import Book, Catalog, DuplicateBookError

DUNE = Book("9780441013593", "Dune", "Frank Herbert", 1965)
EMMA = Book("9780141439587", "Emma", "Jane Austen", 1815)


@pytest.fixture
def catalog() -> Catalog:
    c = Catalog()
    c.add(EMMA)
    c.add(DUNE)
    return c


def test_all_sorted_by_title(catalog: Catalog) -> None:
    assert [b.title for b in catalog.all()] == ["Dune", "Emma"]


def test_get(catalog: Catalog) -> None:
    assert catalog.get(DUNE.isbn) == DUNE
    assert catalog.get("missing") is None


def test_search_title_and_author(catalog: Catalog) -> None:
    assert catalog.search("dune") == [DUNE]
    assert catalog.search("AUSTEN") == [EMMA]
    assert catalog.search("nothing") == []


def test_duplicate_rejected(catalog: Catalog) -> None:
    with pytest.raises(DuplicateBookError):
        catalog.add(DUNE)


def test_empty_isbn_rejected() -> None:
    with pytest.raises(ValueError):
        Catalog().add(Book(" ", "x", "y", 2000))


def test_empty_catalog() -> None:
    assert Catalog().all() == []
