"""Tests for skills/metadoc/scripts/metadoc_tool.py. Run with: python3 -m unittest"""

import hashlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "skills", "metadoc", "scripts", "metadoc_tool.py")
EXAMPLES = os.path.join(ROOT, "skills", "metadoc", "examples")
# kalman.py / kalman.metadoc are copied unchanged from examples/python/ of
# https://github.com/a118145/metadoc-reader, the repository that defines the spec's test vectors.
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
KALMAN = os.path.join(FIXTURES, "kalman.py")

_spec = importlib.util.spec_from_file_location("metadoc_tool", SCRIPT)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

# The canonical Python one-liner from spec section 6.1, verbatim.
SPEC_ONE_LINER = (
    'import hashlib,sys;p,s,e=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]);'
    'L=open(p,encoding="utf-8-sig",newline="").read().split("\\n")[s-1:e];'
    'print(hashlib.sha256("".join(l.rstrip(" \\t\\r")+"\\n" for l in L).encode()).hexdigest()[:12])'
)


def run_cli(*args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        status = tool.main(list(args))
    return status, stdout.getvalue(), stderr.getvalue()


class SpanHashTest(unittest.TestCase):
    def test_spec_vector_kalman_update(self):
        self.assertEqual(tool.span_hash(tool.read_lines(KALMAN), 41, 54), "a474c953856a")

    def test_spec_vector_trailing_whitespace_and_crlf(self):
        lines = tool.split_lines("ab  \r\ncd\t\n")
        self.assertEqual(tool.span_hash(lines, 1, 2), "5141648ccbe9")
        self.assertEqual(hashlib.sha256(b"ab\ncd\n").hexdigest()[:12], "5141648ccbe9")

    def test_spec_vector_from_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "vector.txt")
            with open(path, "wb") as handle:
                handle.write(b"ab  \r\ncd\t\n")
            self.assertEqual(run_cli("hash", path, "1-2")[1], 'lines="1-2" hash="5141648ccbe9"\n')

    def test_matches_spec_one_liner(self):
        lines = tool.read_lines(KALMAN)
        for start, end in [(1, 1), (9, 16), (19, 58), (41, 54), (77, 79), (1, len(lines))]:
            with self.subTest(lines=f"{start}-{end}"):
                expected = subprocess.run(
                    [sys.executable, "-c", SPEC_ONE_LINER, KALMAN, str(start), str(end)],
                    check=True, capture_output=True, text=True,
                ).stdout.strip()
                self.assertEqual(tool.span_hash(lines, start, end), expected)

    def test_line_numbering(self):
        self.assertEqual(tool.split_lines("a\nb\n"), ["a", "b"])
        self.assertEqual(tool.split_lines("a\r\nb"), ["a\r", "b"])
        self.assertEqual(tool.split_lines("a\n\n"), ["a", ""])
        self.assertEqual(tool.split_lines(""), [])
        self.assertEqual(tool.split_lines("\ufeffx\ny"), ["x", "y"])

    def test_insensitive_to_line_endings_bom_and_trailing_whitespace(self):
        unix = tool.span_hash(tool.split_lines("def f():\n    return 1\n"), 1, 2)
        self.assertEqual(tool.span_hash(tool.split_lines("def f():  \r\n    return 1"), 1, 2), unix)
        self.assertEqual(tool.span_hash(tool.split_lines("\ufeffdef f():\n    return 1\n"), 1, 2), unix)

    def test_sensitive_to_indentation_and_content(self):
        base = tool.span_hash(tool.split_lines("if x:\n    y()\n"), 1, 2)
        self.assertNotEqual(tool.span_hash(tool.split_lines("if x:\n  y()\n"), 1, 2), base)
        self.assertNotEqual(tool.span_hash(tool.split_lines("if x:\n    z()\n"), 1, 2), base)
        self.assertNotEqual(tool.span_hash(tool.split_lines("if x:\n    y()\u00a0\n"), 1, 2), base)

    def test_out_of_range(self):
        lines = tool.split_lines("a\nb\n")
        self.assertIsNone(tool.span_hash(lines, 0, 1))
        self.assertIsNone(tool.span_hash(lines, 2, 3))
        self.assertIsNone(tool.span_hash(lines, 2, 1))


class HashCommandTest(unittest.TestCase):
    def test_prints_anchor_attributes_per_range(self):
        status, out, _ = run_cli("hash", KALMAN, "41-54", "9-16", "77")
        self.assertEqual(status, 0)
        self.assertEqual(out.splitlines(), [
            'lines="41-54" hash="a474c953856a"',
            'lines="9-16" hash="80af0221e425"',
            'lines="77-77" hash="%s"' % tool.span_hash(tool.read_lines(KALMAN), 77, 77),
        ])

    def test_rejects_bad_ranges(self):
        for bad in ["0-3", "9-2", "x", "78-80"]:
            with self.subTest(range=bad):
                status, _, err = run_cli("hash", KALMAN, bad)
                self.assertEqual(status, 2)
                self.assertIn("error:", err)

    def test_runs_as_a_script(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "hash", KALMAN, "41-54"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, 'lines="41-54" hash="a474c953856a"\n')


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory)
        for name in ["kalman.py", "kalman.metadoc"]:
            shutil.copy(os.path.join(FIXTURES, name), self.directory)
        self.metadoc = os.path.join(self.directory, "kalman.metadoc")
        self.source = os.path.join(self.directory, "kalman.py")

    def read(self, path):
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read()

    def write(self, path, text):
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def test_worked_example_is_clean(self):
        status, out, _ = run_cli("check", os.path.join(EXAMPLES, "token_bucket.metadoc"))
        self.assertEqual(status, 0, out)
        self.assertTrue(out.endswith(": OK\n"))

    def test_reader_example_is_clean(self):
        self.assertEqual(tool.check_metadoc(self.metadoc), [])

    def test_line_endings_and_trailing_whitespace_keep_it_clean(self):
        text = self.read(self.source)
        self.write(self.source, "\ufeff" + text.replace("\n", "  \r\n"))
        self.assertEqual(tool.check_metadoc(self.metadoc), [])

    def test_changed_code_is_stale(self):
        text = self.read(self.source)
        self.write(self.source, text.replace("innovation_variance = a + self.r", "innovation_variance = a + 2 * self.r"))
        problems = tool.check_metadoc(self.metadoc)
        self.assertEqual(len(problems), 2, problems)  # KalmanFilter (19-58) and KalmanFilter.update (41-54)
        self.assertTrue(all("stale" in problem for problem in problems), problems)
        self.assertIn("KalmanFilter.update lines 41-54", "\n".join(problems))
        status, _, err = run_cli("check", self.metadoc)
        self.assertEqual(status, 1)
        self.assertIn("2 problem(s)", err)

    def test_moved_code_suggests_new_lines(self):
        text = self.read(self.source)
        self.write(self.source, text.replace("import random\n", "import math\nimport random\n\n"))
        problems = tool.check_metadoc(self.metadoc)
        self.assertEqual(len(problems), 8, problems)
        self.assertIn('lines="43-56" (hash unchanged)', "\n".join(problems))

    def test_out_of_bounds(self):
        text = self.read(self.source)
        self.write(self.source, text.split('if __name__ == "__main__":')[0])
        problems = tool.check_metadoc(self.metadoc)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("lines 77-79: out of bounds, the source has 76 lines", problems[0])

    def test_structure_problems(self):
        self.write(self.metadoc, "\n".join([
            '<!-- metadoc:file version="1" source="kalman.py" -->',
            "# kalman.py",
            '<!-- metadoc:section symbol="simulate" lines="61-74" hash="5ad48aca0751" -->',
            "## `simulate`",
            '<!-- metadoc:section symbol="GaussianState" lines="9-16" hash="80AF0221E425" -->',
            "## `GaussianState`",
            '<!-- metadoc:section symbol="bad name" lines="16-9" hash="xyz" -->',
            '<!-- metadoc:section lines="20" -->',
            "<!-- metadoc:note text=\"x\" -->",
            "```markdown",
            '<!-- metadoc:section lines="1-2" hash="000000000000" -->',
            "```",
            "",
        ]))
        problems = "\n".join(tool.check_metadoc(self.metadoc))
        for expected in [
            'kalman.metadoc:1: header version is \'1\', expected "0"',
            "kalman.metadoc:5: hash should be written in lowercase",
            "kalman.metadoc:5: out of source order",
            'kalman.metadoc:7: invalid symbol "bad name"',
            'kalman.metadoc:7: invalid lines "16-9"',
            'kalman.metadoc:7: invalid hash "xyz"',
            "kalman.metadoc:8: missing hash attribute",
            'kalman.metadoc:9: unknown anchor kind "metadoc:note"',
        ]:
            self.assertIn(expected, problems)
        self.assertNotIn("kalman.metadoc:11:", problems)  # anchors inside code fences are ignored

    def test_header_and_pairing(self):
        body = self.read(self.metadoc).split("\n", 1)[1]
        self.write(self.metadoc, body)
        problems = tool.check_metadoc(self.metadoc)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("missing header", problems[0])

        self.write(self.metadoc, '<!-- metadoc:file version="0" source="kalman.py " -->\n' + body)
        self.assertIn("source file not found", "\n".join(tool.check_metadoc(self.metadoc)))

        renamed = os.path.join(self.directory, "filter.metadoc")
        self.write(renamed, '<!-- metadoc:file version="0" source="kalman.py" -->\n')
        self.assertIn("file name should be kalman.metadoc", "\n".join(tool.check_metadoc(renamed)))

        missing = os.path.join(self.directory, "gone.metadoc")
        self.write(missing, '<!-- metadoc:file version="0" source="gone.py" -->\n')
        self.assertIn("source file not found", "\n".join(tool.check_metadoc(missing)))


if __name__ == "__main__":
    unittest.main()
