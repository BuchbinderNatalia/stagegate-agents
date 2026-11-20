# bookshelf — sample app for stagegate-agents

A deliberately small Python app (standard library only) for trying the factory and for its
tests. It has a catalogue (`bookshelf/catalog.py`) with tests, and one **open feature idea**:

> Export the catalogue as CSV (columns `isbn,title,author,year`, sorted like `Catalog.all()`),
> so users can open it in a spreadsheet.

Try it:
```bash
cp -r examples/sample-app /tmp/bookshelf && cd /tmp/bookshelf && git init -q && git add -A && git commit -qm init
/path/to/stagegate-agents/scripts/install.sh .
claude            # then: /feature-factory export the catalogue as CSV
```
