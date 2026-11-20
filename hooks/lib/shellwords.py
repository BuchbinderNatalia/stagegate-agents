# SPDX-License-Identifier: Apache-2.0
"""Find the commands a Bash string would actually run.

Shared by every stagegate guard hook. Given the `command` Claude Code is about
to run, `commands()` returns the argv of each simple command that would
execute, with wrappers stripped. Mentions inside quoted strings, commit
messages, echo arguments and heredoc bodies are data, not commands, and are
not returned.

Handled: separators (; && || | & newlines), grouping ({ } ( ) and $( )),
backticks, line continuations, shell keywords (if/then/while/do/!/...),
wrappers (command, builtin, exec, env, sudo, nohup, time, timeout, nice,
xargs) and their value-taking options, VAR=value prefixes, programs called by
path (/usr/bin/gh), nested shells (sh/bash/zsh/dash -c "...") and eval,
recursively up to MAX_DEPTH.

Not handled (documented limits; guards are guardrails, not a sandbox):
variable/alias/function expansion, `env -S`, scripts that call a tool
internally, and commands assembled at runtime. Unparseable input (e.g. an
unclosed quote) falls back to a naive split, which errs towards matching.

Known false positive (fails safe, i.e. blocks): quotes NESTED inside a quoted
command substitution, as in  git commit -m "$(msg "title" "use `gh pr merge 1`")".
shlex can't nest quotes, so the inner strings look unquoted and their text looks
like commands. Write such messages to a file (git commit -F file) or a heredoc
(heredoc bodies are ignored). Pinned by test_known_false_positive_nested_quotes.
"""

from __future__ import annotations

import os
import re
import shlex

MAX_DEPTH = 3
SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", ";;", "|&"}
KEYWORDS = {"{", "}", "if", "then", "else", "elif", "fi", "do", "done", "while", "until", "!"}
WRAPPERS = {
    "command",
    "builtin",
    "exec",
    "env",
    "sudo",
    "nohup",
    "time",
    "timeout",
    "nice",
    "xargs",
}
# Wrapper options that consume the next word (`sudo -u USER`, `xargs -I {}`, `nice -n 10`).
WRAPPER_VALUE_FLAGS = {"-u", "-g", "-C", "-D", "-p", "-I", "-n", "-P", "-S", "-s", "-k", "-L"}
SHELLS = {"sh", "bash", "zsh", "dash"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
DURATION = re.compile(r"^\d+(\.\d+)?[smhd]?$")


def strip_heredocs(src: str) -> str:
    """Drop heredoc bodies (they are data) and join backslash-newline continuations."""
    out: list[str] = []
    lines = src.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        delimiters = [m.group(2) for m in HEREDOC.finditer(line)]
        i += 1
        for delim in delimiters:
            while i < len(lines) and lines[i].strip() != delim:
                i += 1
            i += 1  # skip the delimiter line itself
    return "\n".join(out).replace("\\\n", " ")


def _normalise(src: str) -> str:
    # Newlines and backticks separate commands, as in bash. Inside quotes the
    # inserted " ; " stays part of the quoted word, so mentions stay inert.
    return strip_heredocs(src).replace("`", " ; ").replace("\n", " ; ")


def _tokens(src: str) -> list[str]:
    lex = shlex.shlex(src, posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    lex.commenters = ""  # '#' inside words (URLs, issue refs) is not a comment
    return list(lex)


def _fallback_tokens(src: str) -> list[str]:
    # Unbalanced quotes: split naively so a real command is still seen.
    spaced = re.sub(r"(&&|\|\||[;&|()])", r" \1 ", src)
    return [t.strip("'\"") for t in spaced.split() if t.strip("'\"")]


def _split_simple_commands(tokens: list[str]) -> list[list[str]]:
    cmds: list[list[str]] = []
    cur: list[str] = []
    for tok in tokens:
        if tok in SEPARATORS or (not cur and tok in KEYWORDS) or tok in {"}", "fi", "done"}:
            if cur:
                cmds.append(cur)
            cur = []
            continue
        if tok == "$":  # "$(" tokenises as "$" + "(": treat as a subshell opener
            continue
        cur.append(tok)
    if cur:
        cmds.append(cur)
    return cmds


def _strip_wrappers(argv: list[str]) -> list[str]:
    i = 0
    while i < len(argv):
        word = argv[i]
        base = os.path.basename(word)
        if ASSIGNMENT.match(word) or word in KEYWORDS:
            i += 1
            continue
        if base in WRAPPERS:
            i += 1
            while i < len(argv) and (argv[i].startswith("-") or ASSIGNMENT.match(argv[i])):
                takes_value = argv[i] in WRAPPER_VALUE_FLAGS
                i += 2 if takes_value else 1
            if base == "timeout" and i < len(argv) and DURATION.match(argv[i]):
                i += 1  # timeout DURATION cmd
            continue
        break
    return argv[i:]


def commands(src: str, _depth: int = 0) -> list[list[str]]:
    """Return argv lists for every simple command `src` would run (wrappers stripped)."""
    if _depth > MAX_DEPTH or not src.strip():
        return []
    text = _normalise(src)
    try:
        tokens = _tokens(text)
    except ValueError:
        tokens = _fallback_tokens(text)

    found: list[list[str]] = []
    for simple in _split_simple_commands(tokens):
        argv = _strip_wrappers(simple)
        if not argv:
            continue
        found.append(argv)
        head = os.path.basename(argv[0])
        if head in SHELLS and "-c" in argv[1:]:
            idx = argv.index("-c", 1)
            if idx + 1 < len(argv):
                found.extend(commands(argv[idx + 1], _depth + 1))
        elif head == "eval" and len(argv) > 1:
            found.extend(commands(" ".join(argv[1:]), _depth + 1))
    return found


def program(argv: list[str]) -> str:
    """The program name of an argv, without its path (`/usr/bin/gh` -> `gh`)."""
    return os.path.basename(argv[0]) if argv else ""
