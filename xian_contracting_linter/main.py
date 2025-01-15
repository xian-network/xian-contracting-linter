import asyncio
import ast
import re
from io import StringIO
from functools import lru_cache

from pyflakes.api import check
from pyflakes.reporter import Reporter

from xian_contracting_linter.linter import Linter

__all__ = ["lint_code"]


class Settings:
    """Simple settings class"""

    def __init__(self):
        self.MAX_CODE_SIZE = 1_000_000  # 1MB
        self.CACHE_SIZE = 100
        self.DEFAULT_WHITELIST_PATTERNS = frozenset(
            {
                "export",
                "construct",
                "Hash",
                "Variable",
                "ctx",
                "now",
                "random",
                "ForeignHash",
                "ForeignVariable",
                "block_num",
                "block_hash",
                "importlib",
                "hashlib",
                "datetime",
                "crypto",
                "decimal",
                "Any",
                "LogEvent",
            }
        )


settings = Settings()


class LintingException(Exception):
    """Custom exception for linting errors"""

    pass


# Compile regex patterns once
PYFLAKES_PATTERN = re.compile(r"<string>:(\d+):(\d+):\s*(.+)")
CONTRACTING_PATTERN = re.compile(r"Line (\d+):\s*(.+)")


def standardize_error_message(message):
    """Standardize error message by removing extra location information."""
    location_pattern = r"\s*\(<unknown>,\s*line\s*\d+\)$"
    message = re.sub(location_pattern, "", message)
    return message


def is_duplicate_error(error1, error2):
    """Check if two errors are duplicates by comparing standardized messages and positions."""
    # msg1 = standardize_error_message(error1["message"])
    # msg2 = standardize_error_message(error2["message"])

    if error1["message"] != error2["message"]:
        return False

    # if bool(error1.position) != bool(error2.position):
    if bool(error1["line"]) != bool(error2["line"]):
        return False

    # if error1.position and error2.position:
    if error1["line"] and error2["line"]:
        return error1["line"] == error2["line"] and error1["col"] == error2["col"]

    return True


def deduplicate_errors(errors):
    """Remove duplicate errors while preserving order."""
    unique_errors = []
    for error in errors:
        error["message"] = standardize_error_message(error["message"])
        if not any(is_duplicate_error(error, existing) for existing in unique_errors):
            unique_errors.append(error)
    return unique_errors


def parse_pyflakes_line(line, whitelist_patterns):
    """Parse a Pyflakes error line into standardized format"""
    match = PYFLAKES_PATTERN.match(line)
    if not match:
        return None

    line_num, col, message = match.groups()

    if any(pattern in message for pattern in whitelist_patterns):
        return None

    return {"message": message, "line": int(line_num) - 1, "col": int(col) - 1}


def parse_contracting_line(violation):
    """Parse a Contracting linter error into standardized format"""
    match = CONTRACTING_PATTERN.match(violation)
    if match:
        line_num = int(match.group(1))
        message = match.group(2)
        if line_num == 0:
            return {"message": message}

        return {"message": message, "line": line_num - 1, "col": 0}
    return {"message": violation}


async def run_pyflakes(code, whitelist_patterns):
    """Runs Pyflakes and returns standardized errors"""
    try:
        loop = asyncio.get_event_loop()
        stdout = StringIO()
        stderr = StringIO()
        reporter = Reporter(stdout, stderr)

        await loop.run_in_executor(None, check, code, "<string>", reporter)

        combined_output = stdout.getvalue() + stderr.getvalue()
        errors = []

        for line in combined_output.splitlines():
            line = line.strip()
            if not line:
                continue

            error = parse_pyflakes_line(line, whitelist_patterns)
            if error:
                errors.append(error)

        return errors
    except Exception as e:
        raise LintingException(str(e)) from e


async def run_contracting_linter(code):
    """Runs Contracting linter and returns standardized errors"""
    try:
        loop = asyncio.get_event_loop()
        tree = await loop.run_in_executor(None, ast.parse, code)
        linter = Linter()
        violations = await loop.run_in_executor(None, linter.check, tree)

        if not violations:
            return []

        return [parse_contracting_line(v.strip()) for v in violations if v.strip()]
    except Exception as e:
        if isinstance(e, SyntaxError) and e.lineno is not None:
            return [
                {
                    "message": str(e),
                    "line": e.lineno - 1,
                    "col": e.offset - 1 if e.offset else 0,
                }
            ]
        raise LintingException(str(e)) from e


@lru_cache(maxsize=settings.CACHE_SIZE)
def get_whitelist_patterns():
    """Convert whitelist patterns string to frozenset for caching"""
    return settings.DEFAULT_WHITELIST_PATTERNS


async def lint_code(code):
    """Run all linters in parallel"""
    try:
        whitelist_patterns = get_whitelist_patterns()

        pyflakes_task = run_pyflakes(code, whitelist_patterns)
        contracting_task = run_contracting_linter(code)

        results = await asyncio.gather(pyflakes_task, contracting_task)
        all_errors = results[0] + results[1]
        
        return deduplicate_errors(all_errors)
    except LintingException as e:
        error_msg = str(e)
        return [{"message": error_msg}]
