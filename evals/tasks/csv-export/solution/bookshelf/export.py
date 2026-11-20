# SPDX-License-Identifier: Apache-2.0
"""Export the catalogue as CSV."""

from __future__ import annotations

import csv
import io

from bookshelf.catalog import Catalog

FIELDS = ("isbn", "title", "author", "year")


def to_csv(catalog: Catalog) -> str:
    """CSV with a header row, books in Catalog.all() order."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(FIELDS)
    for book in catalog.all():
        writer.writerow([book.isbn, book.title, book.author, book.year])
    return buf.getvalue()
