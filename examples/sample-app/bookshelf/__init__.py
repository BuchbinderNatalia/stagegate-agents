# SPDX-License-Identifier: Apache-2.0
"""bookshelf: a tiny in-memory book catalogue used to demo stagegate-agents."""

from bookshelf.catalog import Book, Catalog, DuplicateBookError

__all__ = ["Book", "Catalog", "DuplicateBookError"]
