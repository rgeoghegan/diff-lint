#!/usr/bin/env python
import subprocess
import argparse
import re


def args():
    parser = argparse.ArgumentParser(
        description="Mix pep8/pyflakes commands with git diff."
    )
    parser.add_argument("file", help="Filename to process")
    parser.add_argument(
        "-r", "--ref", default="HEAD", help="Git ref to compare against."
    )
    return parser.parse_args()


def diff_output(filename, ref):
    diff = subprocess.check_output(
        ["git", "diff", "--color", filename]
    ).decode('utf8')
    return diff.split('\n')


PEP8_PARSER = re.compile(":(\d+):")


def parse_output(output):
    errors = {}
    for line in output.decode('utf8').split('\n'):
        if not line:
            continue
        match = PEP8_PARSER.search(line)
        assert match, "Line %r does not match" % line

        line_no = int(match.group(1))
        errors.setdefault(line_no, []).append(line)

    return errors


def pep8_output(filename):
    proc = subprocess.Popen(["pep8", filename], stdout=subprocess.PIPE)
    (stdout, _) = proc.communicate()
    return parse_output(stdout)


def pyflakes_output(filename):
    proc = subprocess.Popen(["pyflakes", filename], stdout=subprocess.PIPE)
    (stdout, _) = proc.communicate()
    return parse_output(stdout)


COLORS = {
    'cyan': 36,
    'green': 32,
    'red': 31,
    'yellow': 33
}


def color_block(text, color):
    return '\x1b[%dm%s\x1b[m' % (color, text)


def two_pane(text, msg, color):
    padding = 5 * text.count('\x1b[3')
    padding += 3 * text.count('\x1b[m')
    padding -= 6 * text.count('\t')
    return (
        text[:70].ljust(80 + padding)
        + " "
        + color_block(msg, COLORS[color])
    )


def warning_line(text, warning):
    return two_pane(text, warning, "yellow")


def error_line(text, error):
    return two_pane(text, error, "red")


class DiffStateMachine:
    HEADER_PARSER = re.compile("^.{5}@@ -\d+,\d+ \+(\d+),\d+ @@.{3}$")

    def __init__(self, diff_lines, pep8, pyflakes):
        self.state = self.diff_top
        self.diff_lines = diff_lines
        self.diff_line = 0
        self.code_line = 0
        self.pep8 = pep8
        self.pyflakes = pyflakes

    def __iter__(self):
        while self.diff_line < len(self.diff_lines):
            yield self.state()

    def line(self):
        return self.diff_lines[self.diff_line]

    def diff_top(self):
        line = self.line()
        if self.diff_line == 3:
            self.state = self.header
        self.diff_line += 1
        return line

    def header(self):
        line = self.line()
        parsed = self.HEADER_PARSER.match(line)
        assert parsed

        self.code_line = int(parsed.group(1))
        self.state = self.code_lines
        self.diff_line += 1

        return line

    def code_lines(self):
        line = self.line()

        if line[:6] == '\x1b[31m-':
            self.diff_line += 1
            return line

        if self.pyflakes.get(self.code_line, []):
            self.state = self.continue_msgs
            return error_line(line, self.pyflakes[self.code_line].pop(0))
        if self.pep8.get(self.code_line, []):
            self.state = self.continue_msgs
            return warning_line(line, self.pep8[self.code_line].pop(0))

        self.diff_line += 1
        self.code_line += 1
        return line

    def continue_msgs(self):
        msg = None
        if self.pyflakes.get(self.code_line, []):
            msg = error_line('', self.pyflakes[self.code_line].pop(0))
        elif self.pep8.get(self.code_line, []):
            msg = warning_line('', self.pep8[self.code_line].pop(0))

        if msg is None:
            self.diff_line += 1
            self.code_line += 1
            self.state = self.code_lines
            return self.code_lines()

        return msg


def match_lines(filename, ref):
    pep8 = pep8_output(filename)
    pyflakes = pyflakes_output(filename)
    diff_lines = diff_output(filename, ref)

    matcher = DiffStateMachine(diff_lines, pep8, pyflakes)
    for line in matcher:
        print(line)

if __name__ == "__main__":
    options = args()
    match_lines(options.file, options.ref)
