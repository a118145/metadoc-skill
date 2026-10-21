---
name: metadoc
description: Write, generate, update or refresh .metadoc files, the prose companion files that Metadoc Reader shows side by side with source code. Use when asked to create a metadoc for a source file, document a source file for Metadoc Reader, or bring an existing .metadoc up to date after the code changed. Covers choosing sections, symbol names, line ranges, span hashes (computed with the bundled script, never by hand) and writing concise explanations.
---

# Writing metadoc files

A metadoc (`<stem>.metadoc`) explains a source file in prose. Metadoc Reader shows it next to the
code and aligns each section with the span of code it describes. The alignment depends on three
machine-readable attributes per section, so they must be exact.

**Spec:** this skill targets **metadoc format version 0**. The normative definition is
[`docs/metadoc-spec.md`](https://github.com/a118145/metadoc-reader/blob/main/docs/metadoc-spec.md)
in the metadoc-reader repository; section numbers below (§) refer to it. If anything here seems to
disagree with the spec, the spec wins. Read it when a case is not covered here.

**Helper script:** `scripts/metadoc_tool.py` in this skill's folder (Python 3, no dependencies).
**Always use it** to compute hashes and to check the result. Never compute, guess or copy a hash
by hand. Below, `TOOL` means `python3 <this skill's folder>/scripts/metadoc_tool.py`.

```sh
TOOL hash  path/to/source.py 41-54 9-16     # prints  lines="41-54" hash="a474c953856a"  per range
TOOL check path/to/source.metadoc           # exit 0 = clean, 1 = problems (one per line)
```

A complete, clean example pair is in `examples/` (`token_bucket.py` + `token_bucket.metadoc`).

## File layout (minimum rules)

- File: `<stem>.metadoc` in the **same directory** as the source, where the stem is the file name
  up to its last dot (`kalman.py` → `kalman.metadoc`). If another file with the same stem already
  has `<stem>.metadoc` (e.g. `lu_solver.cpp` and `lu_solver.hpp`), use the full name:
  `lu_solver.hpp.metadoc`.
- First non-blank line, exactly: `<!-- metadoc:file version="0" source="<source file name>" -->`.
- Then optional overview Markdown (the file as a whole), then the sections.
- Each section is an anchor line followed by Markdown:

  ```markdown
  <!-- metadoc:section symbol="KalmanFilter.update" lines="41-54" hash="a474c953856a" -->
  ### `update` — measurement update

  Fuses one position measurement into the belief ...
  ```

  The anchor must be alone on its line. Attribute values are in double quotes and may not contain
  `"`. Write the hash in lowercase.
- Sections appear in **source order** (ascending start line). They may nest: a class section first,
  then sections for its methods. Two sections should not start on the same line. Code may be left
  undescribed.
- Start every section with a heading: `##` for top-level symbols, `###` for members.
- Do not use raw HTML or HTML comments in the descriptions; the reader shows them as literal text.
  Each section's Markdown is rendered on its own, so link reference definitions are not shared
  between sections.

## Workflow: new metadoc

1. **Read the whole source file** and understand it before writing anything. Get exact line numbers
   from a numbered view (your file-read tool, `cat -n`, `grep -n`); never count lines by hand.
2. **Choose sections.** Give a section to each class/struct, each function or method that contains
   real logic, and each non-obvious block (a constants table, a `main` guard). Skip trivial members
   (plain getters, one-line delegations) or mention them in the enclosing class's section. Aim for
   sections a reader would want next to the code, not one per line of code.
3. **Name each symbol** (§5.1, below).
4. **Determine each span** (§5.2, below).
5. **Hash all spans in one call:** `TOOL hash <source> <start>-<end> ...`, then paste each printed
   `lines="…" hash="…"` pair into its anchor.
6. **Write the descriptions** (guidance below).
7. **Run `TOOL check <metadoc>`** and fix every reported problem until it prints `OK`.

### Symbol names (§5.1)

`symbol` is the qualified name **within the file**: every enclosing scope, joined with `.`.

| Construct | `symbol` |
|---|---|
| Python top-level function `simulate` | `simulate` |
| Python method `update` of class `KalmanFilter` | `KalmanFilter.update` |
| Python nested class `Config` in class `Model` | `Model.Config` |
| C++ `void LuSolver::solve()` defined out of line inside `namespace linalg` | `linalg.LuSolver.solve` |
| C++ constructor of `LuSolver` in `namespace linalg` | `linalg.LuSolver.LuSolver` |
| C++ free function `norm` in nested namespaces `a::b` | `a.b.norm` |
| TypeScript method `render` of class `View` | `View.render` |

- Use the scope path as written in the source: namespaces, classes/structs, enclosing functions.
  Convert `::` to `.`.
- Leave out parameter lists, return types, template arguments and generic parameters
  (`Matrix<T>::at` → `Matrix.at`).
- Overloads share one name; the line hint tells them apart.
- Anonymous scopes (C++ anonymous namespaces, lambdas) cannot be named: omit `symbol`.
- Omit `symbol` for spans that are not a symbol (imports, a constants block, a `main` guard).
- No whitespace or `"` in the value.

### Line ranges (§5.2)

`lines="<start>-<end>"`: 1-based, inclusive, as the file is **now**. A single line may be written
`lines="<n>"`.

- **Start** at the symbol's first line **including** decorators, annotations/attributes and
  template headers (`@dataclass`, `@property`, `[[nodiscard]]`, `template <typename T>`).
- **Exclude** comments and blank lines that precede the symbol (doc comments above a C++ function,
  a `# comment` above a Python method). A Python docstring is inside the body and therefore included.
- **End** at the symbol's last line: the closing brace (`}` or `};`), or the last line of the
  indented body. Do not include trailing blank lines.
- A non-symbol span covers exactly the lines described.
- Line numbering counts LF-separated lines; a final newline does not add a line.

Example (`examples/token_bucket.py`): the comment on line 26 is not part of `_refill`, so its span
is `27-30`; the `@dataclass` on line 10 is part of `TokenBucket`, so its span is `10-44`.

### Hash (§6)

The hash is the first 12 hex characters of a SHA-256 over the span's lines with trailing spaces,
tabs and CRs stripped and every line LF-terminated. Line-ending style, trailing whitespace and the
final newline do not affect it; any other edit in the span, including re-indentation, does.
**Always get it from `TOOL hash`.** It reproduces spec §6.1 exactly; a hand-made or remembered hash
makes the reader flag the section as stale.

## Writing the descriptions

The reader already shows the code. A section earns its place by telling what the code alone does
not tell quickly:

- **What and why, not how line by line.** State the purpose, the algorithm or idea behind it, and
  why it is done this way. Do not narrate statements ("then it loops over the list and appends...").
- **Name the algorithm and its model** when there is one (e.g. "Doolittle LU with partial pivoting",
  "constant-velocity Kalman filter, `x[k+1] = F x[k] + w`"). Give the key formula in Markdown or
  inline code if it clarifies the code.
- **Contracts and consequences:** inputs and their units, return value, side effects, invariants,
  error behaviour, edge cases, complexity when it matters.
- **Non-obvious decisions:** why a constant has its value, why a simpler approach was not used,
  what would break if it were changed.
- **Concise:** usually 2–8 lines per section; lists and short paragraphs over walls of text. A class
  section describes the role of the class and its state; leave method details to method sections.
- **Accurate:** describe what the code actually does, not what its names suggest. Do not invent
  behaviour, history or intent you cannot see in the code; say "presumably" if you must infer.
- The **overview** (before the first section) says what the file is for and how its parts fit
  together, in a few sentences.
- Write in the language the user asks for; default to English.

## Workflow: refreshing a metadoc after the source changed

1. Run `TOOL check <metadoc>`. It reports, per section:
   - **code moved** with a suggested `lines="…"`: the code is unchanged but at a new place. Update
     `lines` to the suggestion; hash and text stay.
   - **stale**: the code inside the span changed (or the span boundaries moved). Re-read the
     current code of that symbol (`git diff` helps), determine its new span (§5.2), re-hash it with
     `TOOL hash`, and **update the text** if behaviour, parameters or reasoning changed.
   - **out of bounds**: the file got shorter than the span. Treat it like stale; delete the section
     if the symbol no longer exists.
2. Sections whose span was not reported can still need attention: a class section covers its
   methods, so a changed method makes both stale; and code added or removed between two sections
   shifts every later span.
3. Add sections for new symbols that deserve one and delete sections for removed symbols. Keep
   source order.
4. Update the overview if the file's purpose or structure changed.
5. Run `TOOL check` again until it prints `OK`.

Do not "fix" a stale section by re-hashing without re-reading the code: the hash is the reader's
only signal that the text may no longer be true.

## Final checklist

- [ ] `<stem>.metadoc` (or `<name>.metadoc`) next to the source; header is the first non-blank line
      with `version="0"` and the source file name.
- [ ] Sections in source order, each with `symbol` (when nameable), `lines`, `hash`, and a heading.
- [ ] Every `lines`/`hash` pair came from `TOOL hash`; `TOOL check` prints `OK`.
- [ ] Descriptions explain purpose, algorithm and decisions concisely; no line-by-line paraphrase,
      no raw HTML.
