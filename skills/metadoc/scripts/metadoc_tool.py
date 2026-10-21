#!/usr/bin/env python3
"""Span hashes and freshness checks for .metadoc files (metadoc format spec v0).

The format is defined by docs/metadoc-spec.md in https://github.com/a118145/metadoc-reader.
This script implements only what a producer needs at writing time:

  hash   FILE RANGE...      print the anchor attributes lines="S-E" hash="..." of each range
  check  METADOC...         report sections whose hash or line range no longer fits the source

RANGE is "START-END" or "LINE" (1-based, inclusive). Python 3.8+, standard library only.
Exit status: 0 = success / all clean, 1 = problems found, 2 = usage or I/O error.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

SPEC_VERSION = "0"
HASH_LENGTH = 12

HASH_PATTERN = re.compile(r"^[0-9a-f]{12}$")
LINES_PATTERN = re.compile(r"^(\d+)(?:-(\d+))?$")
SYMBOL_PATTERN = re.compile(r'^[^\s"]+$')
# Same anchor and fence syntax as the reference reader (spec sections 4 and 5).
ANCHOR_LINE = re.compile(r"^\s*<!--\s*metadoc:([A-Za-z0-9_-]*)(.*?)-->\s*$")
ATTRIBUTE = re.compile(r'\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*"([^"]*)"')
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")


class UsageError(Exception):
    """A bad argument or unreadable file; reported with exit status 2."""


# --- Span hash (spec section 6) ---------------------------------------------------------------


def split_lines(text: str) -> List[str]:
    """Numbers lines as spec section 5.2 does: drop a BOM, split at LF, no extra final line."""
    if text.startswith("﻿"):
        text = text[1:]
    if text == "":
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def hash_lines(lines: Sequence[str]) -> str:
    """Hash of already split lines: strip trailing space/tab/CR, LF-terminate, SHA-256, 12 hex."""
    joined = "".join(line.rstrip(" \t\r") + "\n" for line in lines)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:HASH_LENGTH]


def span_hash(lines: Sequence[str], start: int, end: int) -> Optional[str]:
    """Hash of the 1-based inclusive range start-end, or None if it does not lie in the file."""
    if start < 1 or end < start or end > len(lines):
        return None
    return hash_lines(lines[start - 1 : end])


def read_lines(path: str) -> List[str]:
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as error:
        raise UsageError(f"{path}: cannot read: {error.strerror}") from error
    try:
        return split_lines(data.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise UsageError(f"{path}: not valid UTF-8 ({error.reason} at byte {error.start})") from error


def parse_range(value: str) -> Optional[Tuple[int, int]]:
    """Parses "START-END" or "LINE"; None if malformed or START > END or START < 1."""
    match = LINES_PATTERN.match(value.strip())
    if not match:
        return None
    start = int(match.group(1))
    end = start if match.group(2) is None else int(match.group(2))
    if start < 1 or end < start:
        return None
    return start, end


# --- Metadoc parsing (spec sections 3-5) ------------------------------------------------------


class Section(NamedTuple):
    anchor_line: int
    attributes: Dict[str, str]
    problems: List[str]


class Metadoc(NamedTuple):
    header: Optional[Dict[str, str]]
    sections: List[Section]
    problems: List[Tuple[int, str]]


def parse_anchor(line: str) -> Optional[Tuple[str, Dict[str, str], List[str]]]:
    """Parses a line that is only a <!-- metadoc:KIND ... --> comment, else returns None."""
    match = ANCHOR_LINE.match(line)
    if not match:
        return None
    attributes: Dict[str, str] = {}
    problems: List[str] = []
    rest = match.group(2)
    position = 0
    while position < len(rest):
        attribute = ATTRIBUTE.match(rest, position)
        if not attribute:
            if rest[position:].strip():
                problems.append(f'unparsable anchor text "{rest[position:].strip()}"')
            break
        name, value = attribute.group(1), attribute.group(2)
        if name in attributes:
            problems.append(f'duplicate attribute "{name}"')
        else:
            attributes[name] = value
        position = attribute.end()
    return match.group(1), attributes, problems


def parse_metadoc(text: str) -> Metadoc:
    header: Optional[Dict[str, str]] = None
    sections: List[Section] = []
    problems: List[Tuple[int, str]] = []
    seen_content = False
    fence: Optional[Tuple[str, int]] = None

    for number, raw in enumerate(split_lines(text), start=1):
        line = raw[:-1] if raw.endswith("\r") else raw
        if fence:
            if re.match(r"^ {0,3}%s{%d,}\s*$" % (re.escape(fence[0]), fence[1]), line):
                fence = None
            continue
        opening = FENCE_OPEN.match(line)
        if opening:
            fence = (opening.group(1)[0], len(opening.group(1)))
            seen_content = True
            continue
        anchor = parse_anchor(line)
        if anchor is None:
            if line.strip():
                seen_content = True
            continue
        kind, attributes, anchor_problems = anchor
        if kind == "file":
            if header is None and not seen_content and not sections:
                header = attributes
                problems.extend((number, f"header: {problem}") for problem in anchor_problems)
            else:
                problems.append((number, "misplaced metadoc:file header (must be the first non-blank line)"))
            seen_content = True
        elif kind == "section":
            sections.append(Section(number, attributes, anchor_problems))
            seen_content = True
        else:
            problems.append((number, f'unknown anchor kind "metadoc:{kind}"'))
    return Metadoc(header, sections, problems)


# --- Checking ---------------------------------------------------------------------------------


def nearest_match(lines: Sequence[str], length: int, wanted: str, hint: int) -> Optional[int]:
    """Start line of the length-line window hashing to wanted that lies closest to hint."""
    best: Optional[int] = None
    for start in range(1, len(lines) - length + 2):
        if span_hash(lines, start, start + length - 1) == wanted:
            if best is None or abs(start - hint) < abs(best - hint):
                best = start
    return best


def check_metadoc(metadoc_path: str, source_path: Optional[str] = None) -> List[str]:
    """Returns one "path:line: message" string per problem; an empty list means clean."""
    try:
        with open(metadoc_path, "rb") as handle:
            text = handle.read().decode("utf-8")
    except OSError as error:
        raise UsageError(f"{metadoc_path}: cannot read: {error.strerror}") from error
    except UnicodeDecodeError as error:
        raise UsageError(f"{metadoc_path}: not valid UTF-8 ({error.reason} at byte {error.start})") from error

    doc = parse_metadoc(text)
    problems: List[Tuple[int, str]] = list(doc.problems)
    directory = os.path.dirname(metadoc_path)

    if doc.header is None:
        problems.append((1, 'missing header <!-- metadoc:file version="0" source="..." --> on the first non-blank line'))
    else:
        version = doc.header.get("version")
        if version != SPEC_VERSION:
            problems.append((1, f'header version is {version!r}, expected "{SPEC_VERSION}"'))
        source = doc.header.get("source", "").strip()
        if not source:
            problems.append((1, "header has no source attribute"))
        elif source_path is None:
            source_path = os.path.join(directory, *source.split("/"))
            problems.extend((1, message) for message in pairing_problems(metadoc_path, source_path))

    lines: Optional[List[str]] = None
    if source_path is None:
        problems.append((1, "no source file to check against (add a source attribute or pass --source)"))
    elif not os.path.isfile(source_path):
        problems.append((1, f"source file not found: {source_path}"))
    else:
        lines = read_lines(source_path)

    previous_start: Optional[int] = None
    for section in doc.sections:
        problems.extend((section.anchor_line, problem) for problem in section.problems)
        problems.extend((section.anchor_line, problem) for problem in check_section(section, lines))
        span = parse_range(section.attributes.get("lines", ""))
        if span is None:
            continue
        if previous_start is not None and span[0] < previous_start:
            problems.append((section.anchor_line, f"out of source order: starts at line {span[0]}, before the previous section (line {previous_start})"))
        elif previous_start is not None and span[0] == previous_start:
            problems.append((section.anchor_line, f"starts on the same line as the previous section ({span[0]})"))
        previous_start = span[0]

    return [f"{metadoc_path}:{line}: {message}" for line, message in sorted(problems, key=lambda item: item[0])]


def pairing_problems(metadoc_path: str, source_path: str) -> List[str]:
    """Problems that would stop a reader from finding this metadoc for its source (spec section 2)."""
    source_name = os.path.basename(source_path)
    stem = source_name.rsplit(".", 1)[0] if "." in source_name else source_name
    accepted = {source_name + ".metadoc", stem + ".metadoc"}
    problems = []
    if os.path.basename(metadoc_path) not in accepted:
        problems.append(f"file name should be {stem}.metadoc or {source_name}.metadoc for source {source_name}")
    if os.path.abspath(os.path.dirname(source_path)) != os.path.abspath(os.path.dirname(metadoc_path) or "."):
        problems.append("source must be in the same directory as the metadoc")
    return problems


def check_section(section: Section, lines: Optional[List[str]]) -> List[str]:
    attributes = section.attributes
    problems = []
    symbol = attributes.get("symbol")
    if symbol is not None and not SYMBOL_PATTERN.match(symbol):
        problems.append(f'invalid symbol "{symbol}" (no whitespace or quotes allowed)')

    span: Optional[Tuple[int, int]] = None
    if "lines" not in attributes:
        problems.append("missing lines attribute")
    else:
        span = parse_range(attributes["lines"])
        if span is None:
            problems.append(f'invalid lines "{attributes["lines"]}" (expected "START-END", 1-based, START <= END)')

    wanted: Optional[str] = None
    if "hash" not in attributes:
        problems.append("missing hash attribute")
    elif HASH_PATTERN.match(attributes["hash"].lower()):
        wanted = attributes["hash"].lower()
        if wanted != attributes["hash"]:
            problems.append("hash should be written in lowercase")
    else:
        problems.append(f'invalid hash "{attributes["hash"]}" (expected 12 hex characters)')

    if span is None or lines is None:
        return problems
    start, end = span
    label = f'section {symbol or "(no symbol)"} lines {start}-{end}'
    if end > len(lines):
        problems.append(f"{label}: out of bounds, the source has {len(lines)} lines")
    if wanted is None:
        return problems
    actual = span_hash(lines, start, end)
    if actual == wanted:
        return problems
    moved = nearest_match(lines, end - start + 1, wanted, start)
    if moved is not None:
        problems.append(f'{label}: code moved, update to lines="{moved}-{moved + end - start}" (hash unchanged)')
    elif actual is not None:
        problems.append(f"{label}: stale, hash is {actual} but the section says {wanted}; re-read the code, update lines, hash and text")
    return problems


# --- Command line -----------------------------------------------------------------------------


def command_hash(args: argparse.Namespace) -> int:
    lines = read_lines(args.file)
    for value in args.ranges:
        span = parse_range(value)
        if span is None:
            raise UsageError(f'invalid range "{value}" (expected START-END or LINE, 1-based, START <= END)')
        digest = span_hash(lines, *span)
        if digest is None:
            raise UsageError(f"range {value} is outside {args.file}, which has {len(lines)} lines")
        print(f'lines="{span[0]}-{span[1]}" hash="{digest}"')
    return 0


def command_check(args: argparse.Namespace) -> int:
    if args.source is not None and len(args.metadocs) != 1:
        raise UsageError("--source can only be used with a single metadoc")
    found = 0
    for path in args.metadocs:
        problems = check_metadoc(path, args.source)
        for problem in problems:
            print(problem)
        if not problems:
            print(f"{path}: OK")
        found += len(problems)
    if found:
        print(f"{found} problem(s) found", file=sys.stderr)
    return 1 if found else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    hash_parser = commands.add_parser("hash", help="print lines/hash anchor attributes for line ranges of a source file")
    hash_parser.add_argument("file", help="source file")
    hash_parser.add_argument("ranges", nargs="+", metavar="RANGE", help='"START-END" or "LINE", 1-based inclusive')
    hash_parser.set_defaults(handler=command_hash)

    check_parser = commands.add_parser("check", help="verify .metadoc files against their source files")
    check_parser.add_argument("metadocs", nargs="+", metavar="METADOC", help=".metadoc file(s)")
    check_parser.add_argument("--source", help="source file to check against instead of the header's source")
    check_parser.set_defaults(handler=command_check)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except UsageError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
