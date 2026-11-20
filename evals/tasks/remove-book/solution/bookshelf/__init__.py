# SPDX-License-Identifier: Apache-2.0
"""bookshelf: a tiny in-memory book catalogue used to demo stagegate-agents."""

from bookshelf.catalog import Book, BookNotFoundError, Catalog, DuplicateBookError

__all__ = ["Book", "BookNotFoundError", "Catalog", "DuplicateBookError"]
