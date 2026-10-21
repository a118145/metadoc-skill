# metadoc-skill

AI tools now write code faster than people can read it. A **metadoc** is a companion file,
`<stem>.metadoc` next to `<stem>.py` / `<stem>.cpp` / ..., with short full-text explanations of
the file's algorithms, classes and functions.
[Metadoc Reader](https://github.com/a118145/metadoc-reader) shows a source file and its metadoc
side by side, keeps each explanation level with the code it describes, and flags explanations whose
code has changed.

This repository contains an **agent skill** that teaches an AI coding agent to write and maintain
those metadoc files correctly: which sections to write, how to name and locate them, how to compute
the span hashes the reader needs for alignment, and how to write explanations worth reading.

The format itself is defined by the
[metadoc spec, version 0](https://github.com/a118145/metadoc-reader/blob/main/docs/metadoc-spec.md)
in the metadoc-reader repository. This skill targets that version and links to it rather than
copying it.

## Contents

```text
skills/metadoc/
├── SKILL.md                    # the skill: workflow and the rules needed at writing time
├── scripts/metadoc_tool.py     # span hashes and metadoc checks (Python 3, no dependencies)
└── examples/
    ├── token_bucket.py         # worked example: a small source file ...
    └── token_bucket.metadoc    # ... and its metadoc
tests/                          # unit tests for the helper script
```

## Install

The skill is the folder `skills/metadoc/`. Install it by copying that one folder.

### Claude Code

For all your projects (personal skill):

```sh
git clone https://github.com/a118145/metadoc-skill.git
mkdir -p ~/.claude/skills
cp -r metadoc-skill/skills/metadoc ~/.claude/skills/
```

For one project (shared with everyone who works on it), copy the folder into the project instead:

```sh
mkdir -p .claude/skills
cp -r /path/to/metadoc-skill/skills/metadoc .claude/skills/
```

Claude Code picks the skill up automatically in new sessions.

### Other agents

`skills/metadoc/` follows the [Agent Skills](https://agentskills.io) format (a `SKILL.md` with YAML
frontmatter plus bundled files), so it also works with other agents that support Agent Skills.
Copy the folder to wherever your agent loads skills from. The agent needs to be able to run
`python3`.

## Use

Ask your agent, for example:

- "Write a metadoc for `src/solver.py`."
- "Document `lu_solver.cpp` for Metadoc Reader."
- "I changed `kalman.py`; refresh its metadoc."

The agent reads the source, writes the `.metadoc` next to it, computes every hash with the bundled
script, and checks the result.

You can run the helper script yourself, too:

```sh
# anchor attributes for line ranges of a source file
python3 skills/metadoc/scripts/metadoc_tool.py hash skills/metadoc/examples/token_bucket.py 27-30 32-39
# lines="27-30" hash="4afc378e8ed3"
# lines="32-39" hash="238c663b3b0e"

# check metadocs against their sources (exit status 1 if anything is stale, moved or invalid)
python3 skills/metadoc/scripts/metadoc_tool.py check skills/metadoc/examples/token_bucket.metadoc
# skills/metadoc/examples/token_bucket.metadoc: OK
```

## Development

Run the tests (Python 3.8 or newer, standard library only) from the repository root:

```sh
python3 -m unittest
```

The tests check the helper script against the spec's test vectors. `tests/fixtures/kalman.py` and
`kalman.metadoc` are copied unchanged from metadoc-reader's `examples/python/`, because the spec's
test vector refers to them. CI (`.github/workflows/ci.yml`) runs the same command on every pull
request and on pushes to `main`.

## License

[MIT](LICENSE)
