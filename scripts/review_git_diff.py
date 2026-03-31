#!/usr/bin/env python3
"""Summarize Java-focused git diffs for spring-refactor."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence


@dataclass
class DiffFileSummary:
    path: str
    added_lines: int
    removed_lines: int
    added_comments: int
    removed_comments: int
    risks: List[str] = field(default_factory=list)
    added_signals: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class DiffSummary:
    source: str
    file_count: int
    files: List[DiffFileSummary]


def parse_diff_blocks(diff_text: str) -> List[tuple[str, List[str]]]:
    blocks: List[tuple[str, List[str]]] = []
    current_path = None
    current_lines: List[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current_path is not None:
                blocks.append((current_path, current_lines))
            current_lines = [line]
            current_path = None
        else:
            current_lines.append(line)
            if line.startswith("+++ b/"):
                current_path = line[6:]
    if current_lines and current_path is not None:
        blocks.append((current_path, current_lines))
    return blocks


def collect_added_removed(block_lines: List[str]) -> tuple[List[str], List[str]]:
    added, removed = [], []
    for line in block_lines:
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    return added, removed


def detect_risks(path: str, added: List[str], removed: List[str]) -> tuple[List[str], Dict[str, List[str]]]:
    risks: List[str] = []
    signals: Dict[str, List[str]] = {}
    added_joined = "\n".join(added)

    def add_signal(name: str, values: List[str]) -> None:
        if values:
            signals[name] = values[:8]

    added_try_lock = [line.strip() for line in added if "tryLock(" in line]
    added_unlock = [line.strip() for line in added if "unlock(" in line]
    added_shutdown = [line.strip() for line in added if "shutdown(" in line or "close(" in line]
    added_context = [line.strip() for line in added if "AuthContextHolder.setContext(" in line]
    added_public = [line.strip() for line in added if line.strip().startswith(("public ", "protected "))]
    removed_public = [line.strip() for line in removed if line.strip().startswith(("public ", "protected "))]
    added_comments = [line.strip() for line in added if line.strip().startswith("//")]
    removed_comments = [line.strip() for line in removed if line.strip().startswith("//")]

    add_signal("try_lock", added_try_lock)
    add_signal("unlock", added_unlock)
    add_signal("cleanup", added_shutdown)
    add_signal("context", added_context)
    add_signal("public_signatures_added", added_public)
    add_signal("public_signatures_removed", removed_public)

    if added_try_lock and added_unlock:
        guarded = (
            "if (acquired" in added_joined
            or "if(acquired" in added_joined
            or "isHeldByCurrentThread" in added_joined
            or "releaseLockIfAcquired" in added_joined
        )
        if not guarded:
            risks.append("cleanup may be unconditional after tryLock in added code")

    if added_context:
        restored = any("setContext(oldContext" in line or "setContext(oldAuthContext" in line for line in added)
        if not restored and "finally" not in added_joined:
            risks.append("context switch added without visible restore path")

    if added_public and removed_public:
        risks.append("public or protected method signature changed")

    if len(removed_comments) - len(added_comments) >= 3 and len(added_comments) <= 1:
        risks.append("comment coverage may have regressed in touched code")

    if any("ExecutorService" in line or "newFixedThreadPool" in line or "newSingleThreadExecutor" in line for line in added):
        if not any("shutdown" in line for line in added):
            risks.append("executor usage added without visible shutdown path")

    return risks, signals


def summarize_diff_text(diff_text: str, source: str = "<diff>") -> DiffSummary:
    files: List[DiffFileSummary] = []
    for path, block_lines in parse_diff_blocks(diff_text):
        if not path.endswith(".java"):
            continue
        added, removed = collect_added_removed(block_lines)
        risks, signals = detect_risks(path, added, removed)
        files.append(
            DiffFileSummary(
                path=path,
                added_lines=len(added),
                removed_lines=len(removed),
                added_comments=sum(1 for line in added if line.strip().startswith("//")),
                removed_comments=sum(1 for line in removed if line.strip().startswith("//")),
                risks=risks,
                added_signals=signals,
            )
        )
    return DiffSummary(source=source, file_count=len(files), files=files)


def run_git_diff(repo: Path) -> str:
    cmd = ["git", "-C", str(repo), "diff", "--unified=0", "--", "*.java"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def format_text(summary: DiffSummary) -> str:
    lines = [
        f"SOURCE: {summary.source}",
        f"JAVA_FILES_TOUCHED: {summary.file_count}",
    ]
    for item in summary.files:
        lines.extend(
            [
                "",
                f"FILE: {item.path}",
                f"ADDED_LINES: {item.added_lines}",
                f"REMOVED_LINES: {item.removed_lines}",
                f"ADDED_COMMENTS: {item.added_comments}",
                f"REMOVED_COMMENTS: {item.removed_comments}",
                "RISKS:",
            ]
        )
        if item.risks:
            for risk in item.risks:
                lines.append(f"- {risk}")
        else:
            lines.append("- none detected")
        if item.added_signals:
            lines.append("SIGNALS:")
            for key, values in item.added_signals.items():
                lines.append(f"- {key}:")
                for value in values:
                    lines.append(f"  {value}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize Java-focused git diffs for spring-refactor")
    parser.add_argument("--repo", default=".", help="Repository path for git diff mode")
    parser.add_argument("--diff-file", help="Read diff text from a file instead of running git diff")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.diff_file:
        diff_path = Path(args.diff_file).expanduser().resolve()
        diff_text = diff_path.read_text(encoding="utf-8")
        source = str(diff_path)
    else:
        repo = Path(args.repo).expanduser().resolve()
        diff_text = run_git_diff(repo)
        source = f"git diff --unified=0 in {repo}"

    summary = summarize_diff_text(diff_text, source=source)
    if args.json:
        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    else:
        print(format_text(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
