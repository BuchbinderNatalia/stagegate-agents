# SPDX-License-Identifier: Apache-2.0
# Hidden acceptance tests: never shown to the agents.
import pytest
from bookshelf import Book, Catalog

BOOKS = [
    Book("1", "emma", "Jane Austen", 1815),
    Book("2", "Dune", "Frank Herbert", 1965),
    Book("3", "Anathem", "Neal Stephenson", 2008),
    Book("4", "Alpha", "X", 1965),
]


@pytest.fixture
def catalog() -> Catalog:
    c = Catalog()
    for b in BOOKS:
        c.add(b)
    return c


def test_inclusive_bounds_and_order(catalog: Catalog) -> None:
    assert [b.isbn for b in catalog.by_year(1815, 1965)] == ["1", "4", "2"]


def test_single_year(catalog: Catalog) -> None:
    assert [b.title for b in catalog.by_year(2008, 2008)] == ["Anathem"]


def test_empty_range(catalog: Catalog) -> None:
    assert catalog.by_year(1900, 1950) == []


def test_invalid_range(catalog: Catalog) -> None:
    with pytest.raises(ValueError):
        catalog.by_year(2000, 1999)
