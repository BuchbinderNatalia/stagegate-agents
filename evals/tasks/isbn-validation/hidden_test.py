# SPDX-License-Identifier: Apache-2.0
# Hidden acceptance tests: never shown to the agents.
import pytest
from bookshelf import Book, Catalog, DuplicateBookError, InvalidIsbnError


@pytest.mark.parametrize("isbn", ["9780441013593", "978-0-14-143958-7", "978 0316 769488"])
def test_valid(isbn: str) -> None:
    c = Catalog()
    c.add(Book(isbn, "T", "A", 2000))
    assert c.get(isbn) is not None


VALID = "9780441013593"
INVALID = [
    VALID[:-1] + "4",  # wrong check digit
    VALID[:-1],  # too short
    VALID + "1",  # too long
    VALID[:-2] + "X3",  # not all digits
]


@pytest.mark.parametrize("isbn", INVALID)
def test_invalid_rejected_and_not_added(isbn: str) -> None:
    c = Catalog()
    with pytest.raises(InvalidIsbnError):
        c.add(Book(isbn, "T", "A", 2000))
    assert c.all() == []


def test_error_type() -> None:
    assert issubclass(InvalidIsbnError, ValueError)


def test_duplicates_still_rejected() -> None:
    c = Catalog()
    c.add(Book("9780441013593", "Dune", "Frank Herbert", 1965))
    with pytest.raises(DuplicateBookError):
        c.add(Book("9780441013593", "Dune", "Frank Herbert", 1965))
