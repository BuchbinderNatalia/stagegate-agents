# SPDX-License-Identifier: Apache-2.0
# Hidden acceptance tests: never shown to the agents.
import pytest
from bookshelf import Book, Catalog


@pytest.fixture
def catalog() -> Catalog:
    c = Catalog()
    for i, title in enumerate(["Saga A", "Saga B", "Saga C", "Other"]):
        c.add(Book(str(i), title, "Author", 2000 + i))
    return c


def test_backwards_compatible(catalog: Catalog) -> None:
    assert [b.title for b in catalog.search("saga")] == ["Saga A", "Saga B", "Saga C"]


def test_offset_and_limit(catalog: Catalog) -> None:
    assert [b.title for b in catalog.search("saga", limit=1, offset=1)] == ["Saga B"]
    assert [b.title for b in catalog.search("saga", offset=2)] == ["Saga C"]
    assert [b.title for b in catalog.search("saga", limit=2)] == ["Saga A", "Saga B"]


def test_past_the_end(catalog: Catalog) -> None:
    assert catalog.search("saga", offset=10) == []


@pytest.mark.parametrize(("limit", "offset"), [(-1, 0), (None, -1)])
def test_negative_rejected(catalog: Catalog, limit: int | None, offset: int) -> None:
    with pytest.raises(ValueError):
        catalog.search("saga", limit=limit, offset=offset)
