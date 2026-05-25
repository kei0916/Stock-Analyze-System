"""Verify refactoring tracker and source hygiene invariants."""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src" / "stock_analyze_system"
MASTER_TRACKER = REPO_ROOT / "docs" / "superpowers" / "refactoring-2026-04-18" / "master.md"

HISTORY_LABEL_RE = re.compile(
    r"Bug\s*#\d+|Bug#\d+|バグ\s*#\d+|バグ#\d+|既知バグ\s*#?\d+|新発見\s*\d+|新\d+修正"
)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md)\)")


@dataclass(frozen=True)
class VerificationViolation:
    path: str
    message: str
    line: int | None = None

    def format(self) -> str:
        location = f"{self.path}:{self.line}" if self.line is not None else self.path
        return f"{location}: {self.message}"


def _repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _is_git_tracked(path: Path) -> bool:
    if not path.exists():
        return False
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", _repo_relative(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def find_history_label_violations(
    source_root: Path = SOURCE_ROOT,
) -> list[VerificationViolation]:
    """Return source locations that still contain bug-history labels."""
    violations: list[VerificationViolation] = []
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if HISTORY_LABEL_RE.search(line):
                violations.append(
                    VerificationViolation(
                        path=_repo_relative(path),
                        line=line_no,
                        message="history label remains in source",
                    )
                )
    return violations


def find_master_markdown_link_violations(
    master_path: Path = MASTER_TRACKER,
) -> list[VerificationViolation]:
    """Return markdown links in the refactoring master tracker that are missing or untracked."""
    violations: list[VerificationViolation] = []
    for line_no, line in enumerate(master_path.read_text(encoding="utf-8").splitlines(), start=1):
        for match in MARKDOWN_LINK_RE.finditer(line):
            target = match.group(1)
            if "://" in target or target.startswith("#"):
                continue
            target_path = (master_path.parent / target).resolve()
            if not target_path.exists():
                violations.append(
                    VerificationViolation(
                        path=_repo_relative(master_path),
                        line=line_no,
                        message=f"linked markdown file does not exist: {target}",
                    )
                )
            elif not _is_git_tracked(target_path):
                violations.append(
                    VerificationViolation(
                        path=_repo_relative(master_path),
                        line=line_no,
                        message=f"linked markdown file is not tracked by git: {target}",
                    )
                )
    return violations


def find_ruff_violations() -> list[VerificationViolation]:
    """Run ruff over src/tests/scripts and surface failures as verification violations."""
    result = subprocess.run(
        ["uv", "run", "ruff", "check", "src", "tests", "scripts"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return []
    detail = (result.stdout + result.stderr).strip() or "(no output)"
    return [
        VerificationViolation(
            path="src+tests+scripts",
            message=f"ruff check failed:\n{detail}",
        ),
    ]


def main() -> int:
    violations = [
        *find_history_label_violations(),
        *find_master_markdown_link_violations(),
        *find_ruff_violations(),
    ]
    if violations:
        for violation in violations:
            print(violation.format(), file=sys.stderr)
        return 1
    print("refactoring-phase-verification-ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
