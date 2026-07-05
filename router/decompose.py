"""Turn a plan (markdown or prose) into a flat list of atomic ``Task``s.

Strategy, in priority order:

1. **Markdown list items** — numbered (``1.``, ``1)``) or bulleted
   (``-``, ``*``, ``+``). This is the common case: a plan is a to-do list.
   Nested items are captured with their depth; a checkbox (``- [ ]`` /
   ``- [x]``) is stripped and its done-state recorded.
2. **Prose fallback** — if a paragraph has no list markers, it is split into
   sentences and each imperative-looking sentence becomes a task. This lets
   the tool accept a free-text brief, not only a tidy list.

Headings (``#``), fenced code blocks, blockquotes, and blank lines are skipped
so they never masquerade as tasks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Task:
    """One atomic unit of work extracted from a plan."""

    text: str
    #: 1-based position in the plan, in document order.
    index: int
    #: Nesting depth for list items (0 = top level). 0 for prose sentences.
    depth: int = 0
    #: True/False if the item was a checkbox; None if it was not a checkbox.
    done: Optional[bool] = None
    #: How this task was found — "list" or "prose". Useful for debugging.
    source: str = "list"
    #: Section heading this task fell under, if any.
    section: Optional[str] = None
    #: Optional metadata bag filled in by later stages (scores, tier, ...).
    meta: dict = field(default_factory=dict)


# --- Regexes ---------------------------------------------------------------
_ORDERED = re.compile(r"^(?P<indent>\s*)\d+[.)]\s+(?P<body>.+?)\s*$")
_BULLET = re.compile(r"^(?P<indent>\s*)[-*+]\s+(?P<body>.+?)\s*$")
_CHECKBOX = re.compile(r"^\[(?P<mark>[ xX])\]\s+(?P<body>.+?)\s*$")
_HEADING = re.compile(r"^\s*#{1,6}\s+(?P<title>.+?)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_BLOCKQUOTE = re.compile(r"^\s*>")
# Sentence splitter for the prose fallback: break on . ! ? followed by space.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Depth per indentation unit. Markdown commonly uses 2 or 4 spaces / a tab.
_INDENT_UNIT = 2


def _depth_from_indent(indent: str) -> int:
    # Treat a tab as one indent unit; otherwise count spaces in units.
    spaces = indent.replace("\t", " " * _INDENT_UNIT)
    return len(spaces) // _INDENT_UNIT


def _strip_checkbox(body: str):
    """Return (clean_body, done) where done is True/False/None."""
    m = _CHECKBOX.match(body)
    if not m:
        return body, None
    done = m.group("mark").lower() == "x"
    return m.group("body"), done


# Leading discourse markers to strip before looking for an imperative verb, so
# "Then summarize ...", "After that, write ...", "Finally, reformat ..." are
# recognised as tasks.
_CONNECTIVES = {
    "then", "next", "after", "that", "afterwards", "afterward", "first",
    "second", "third", "finally", "also", "now", "subsequently", "later",
    "please", "lastly", "additionally", "furthermore", "so", "and",
}

# Base-form verbs that mark an actionable task. Deliberately excludes weak/
# ambiguous verbs like "do"/"be" so a non-task sentence that merely contains
# "...needs to do" is not misread as a task.
_IMPERATIVE_VERBS = {
    "build", "create", "add", "write", "implement", "design", "set",
    "setup", "configure", "deploy", "test", "fix", "refactor", "parse",
    "extract", "format", "reformat", "summarize", "classify", "generate",
    "make", "update", "remove", "delete", "integrate", "wire", "define",
    "scaffold", "draft", "review", "analyze", "optimize", "migrate",
    "document", "rename", "compose", "split", "validate", "orchestrate",
    "plan", "research", "investigate", "audit", "rewrite", "publish",
}

_OBLIGATION = ("need to", "needs to", "should", "must", "have to", "has to",
               "we will", "i will", "we'll", "i'll")


def _words(text: str):
    """Lower-cased alpha-only word tokens."""
    return re.findall(r"[a-z]+", text.lower())


def _looks_imperative(sentence: str) -> bool:
    """Heuristic: does this prose sentence read like a task to do?

    A sentence is a task if, after stripping leading discourse markers, it
    starts with an imperative verb, OR it contains an obligation phrase
    ("need to", "should", "must") *and* an actual imperative verb somewhere.
    Structured lists are always preferred; this is only the prose fallback.
    """
    tokens = _words(sentence)
    if not tokens:
        return False

    # Strip leading connectives ("then", "after that", "finally", ...).
    i = 0
    while i < len(tokens) and tokens[i] in _CONNECTIVES:
        i += 1
    rest = tokens[i:]
    if not rest:
        return False

    # Case 1: begins with an imperative verb.
    if rest[0] in _IMPERATIVE_VERBS:
        return True

    # Case 2: obligation phrase + a real imperative verb present anywhere.
    lower = sentence.lower()
    if any(p in lower for p in _OBLIGATION) and any(t in _IMPERATIVE_VERBS for t in tokens):
        return True

    return False


def _split_prose(paragraph: str, start_index: int, section: Optional[str]) -> List[Task]:
    tasks: List[Task] = []
    for sentence in _SENTENCE_SPLIT.split(paragraph.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        if _looks_imperative(sentence):
            tasks.append(
                Task(
                    text=sentence.rstrip("."),
                    index=start_index + len(tasks),
                    depth=0,
                    source="prose",
                    section=section,
                )
            )
    return tasks


def decompose(plan_text: str) -> List[Task]:
    """Parse ``plan_text`` into an ordered list of atomic tasks.

    Prefers markdown list items; falls back to imperative prose sentences for
    any paragraph that has no list markers. Returns an empty list if nothing
    task-like is found.
    """
    lines = plan_text.splitlines()
    tasks: List[Task] = []
    current_section: Optional[str] = None
    in_fence = False
    prose_buffer: List[str] = []

    def flush_prose():
        nonlocal prose_buffer
        if prose_buffer:
            paragraph = " ".join(prose_buffer).strip()
            if paragraph:
                tasks.extend(_split_prose(paragraph, len(tasks) + 1, current_section))
            prose_buffer = []

    for raw in lines:
        # Toggle fenced code blocks — never treat their contents as tasks.
        if _FENCE.match(raw):
            flush_prose()
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        if not raw.strip():
            flush_prose()
            continue

        if _BLOCKQUOTE.match(raw):
            flush_prose()
            continue

        heading = _HEADING.match(raw)
        if heading:
            flush_prose()
            current_section = heading.group("title").strip()
            continue

        ordered = _ORDERED.match(raw)
        bullet = _BULLET.match(raw)
        match = ordered or bullet
        if match:
            flush_prose()
            body = match.group("body").strip()
            body, done = _strip_checkbox(body)
            body = body.strip()
            if not body:
                continue
            tasks.append(
                Task(
                    text=body,
                    index=len(tasks) + 1,
                    depth=_depth_from_indent(match.group("indent")),
                    done=done,
                    source="list",
                    section=current_section,
                )
            )
            continue

        # Anything else is prose — buffer it until the paragraph ends.
        prose_buffer.append(raw.strip())

    flush_prose()

    # Re-number sequentially in document order (prose flushes can interleave).
    for i, task in enumerate(tasks, start=1):
        task.index = i
    return tasks
