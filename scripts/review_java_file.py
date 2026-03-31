#!/usr/bin/env python3
"""Summarize Java files for spring-refactor with lightweight risk checks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence

METHOD_PATTERN = re.compile(
    r"(?m)^[ \t]*(?:public|private|protected)\s+"
    r"(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?"
    r"(?:<[^>]+>\s+)?[\w<>\[\], ?]+\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*"
    r"\((?P<params>[^)]*)\)\s*"
    r"(?:throws\s+[^{]+)?\{"
)

CALL_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "new", "throw", "synchronized"}

STAGE_KEYWORDS = {
    "validation": ("validate", "check", "require", "assert", "isblank", "isnull"),
    "parameter_construction": ("build", "create", "format", "collect", "convert", "map", "pair"),
    "business_processing": ("save", "update", "insert", "delete", "select", "find", "receive", "execute", "sync"),
    "post_processing": ("log", "notify", "async", "deleteobject", "expire", "unlock", "close", "shutdown"),
}

SIDE_EFFECT_PATTERNS = {
    "locking": (r"\btryLock\s*\(", r"\bunlock\s*\("),
    "redis": (r"\bredisCache\.", r"\bredissonClient\."),
    "database": (r"\bMapper\.", r"\bselect[A-Z]\w*\(", r"\binsert[A-Z]\w*\(", r"\bupdate[A-Z]\w*\(", r"\bdelete[A-Z]\w*\("),
    "service_calls": (r"\b[a-zA-Z0-9_]+Service\.",),
    "context": (r"AuthContextHolder\.setContext", r"AuthContextHolder\.getContext"),
    "logging": (r"\blog\.",),
    "resource_cleanup": (r"\bclose\s*\(", r"\bshutdown\s*\(", r"\bunlock\s*\(", r"setContext\s*\(\s*oldContext\s*\)"),
}

GENERIC_METHOD_NAMES = {
    "handle",
    "process",
    "processdata",
    "execute",
    "run",
    "deal",
    "common",
    "helper",
    "util",
    "dohandle",
}

GENERIC_LOCAL_NAMES = {
    "data",
    "obj",
    "object",
    "result",
    "res",
    "tmp",
    "temp",
    "list1",
    "map1",
    "info",
}


@dataclass
class MethodSummary:
    name: str
    signature: str
    start_line: int
    end_line: int
    length: int
    parameter_count: int
    comment_lines: int
    method_calls: List[str] = field(default_factory=list)
    stages: Dict[str, List[str]] = field(default_factory=dict)
    side_effects: Dict[str, List[str]] = field(default_factory=dict)
    risks: List[str] = field(default_factory=list)


@dataclass
class FileSummary:
    file: str
    total_lines: int
    method_count: int
    methods: List[MethodSummary]


def line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def find_matching_brace(text: str, open_index: int) -> int:
    depth = 0
    for idx in range(open_index, len(text)):
        char = text[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return idx
    raise ValueError("Unbalanced braces while parsing Java method")


def parse_methods(text: str) -> List[dict]:
    methods: List[dict] = []
    for match in METHOD_PATTERN.finditer(text):
        open_index = text.find("{", match.end() - 1)
        close_index = find_matching_brace(text, open_index)
        methods.append(
            {
                "name": match.group("name"),
                "params": match.group("params"),
                "signature": text[match.start():open_index].strip(),
                "start_line": line_number(text, match.start()),
                "end_line": line_number(text, close_index),
                "body": text[open_index:close_index + 1],
            }
        )
    return methods


def collect_method_calls(body: str) -> List[str]:
    calls: List[str] = []
    for match in CALL_PATTERN.finditer(body):
        name = match.group(1)
        if name not in KEYWORDS:
            calls.append(name)
    ordered: List[str] = []
    seen = set()
    for name in calls:
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered


def collect_stage_signals(calls: Sequence[str]) -> Dict[str, List[str]]:
    stages: Dict[str, List[str]] = {stage: [] for stage in STAGE_KEYWORDS}
    for call in calls:
        lowered = call.lower()
        for stage, keywords in STAGE_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                stages[stage].append(call)
    return {stage: values for stage, values in stages.items() if values}


def collect_side_effects(body: str) -> Dict[str, List[str]]:
    lines = body.splitlines()
    effects: Dict[str, List[str]] = {}
    for category, patterns in SIDE_EFFECT_PATTERNS.items():
        matches = []
        for idx, line in enumerate(lines, start=1):
            if any(re.search(pattern, line) for pattern in patterns):
                matches.append(f"line+{idx}: {line.strip()}")
        if matches:
            effects[category] = matches
    return effects


def has_stage_comments(body: str) -> bool:
    return bool(re.search(r"//\s*[1-4]\.", body) or re.search(r"//.*(validate|build|execute|post|cleanup)", body, re.IGNORECASE))


def collect_local_variable_names(body: str) -> List[str]:
    names: List[str] = []
    pattern = re.compile(r"(?m)^\s*(?:final\s+)?[\w<>\[\], ?]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*=")
    for match in pattern.finditer(body):
        name = match.group(1)
        if name not in KEYWORDS:
            names.append(name)
    return names


def detect_risks(method: dict) -> List[str]:
    body = method["body"]
    risks: List[str] = []
    method_calls = collect_method_calls(body)
    stages = collect_stage_signals(method_calls)
    side_effect_categories = collect_side_effects(body)
    local_names = collect_local_variable_names(body)
    normalized_method_name = method["name"].lower()

    if method["end_line"] - method["start_line"] + 1 > 40 and not has_stage_comments(body):
        risks.append("large method without stage comments")

    if len(stages) >= 3:
        risks.append("mixed responsibilities across multiple workflow stages")

    if len(stages) >= 3 and method["end_line"] - method["start_line"] + 1 > 5:
        risks.append("method likely violates single responsibility across multiple workflow stages")

    if normalized_method_name in GENERIC_METHOD_NAMES or (
        any(token in normalized_method_name for token in ("handle", "process", "helper", "util"))
        and not any(token in normalized_method_name for token in ("validate", "build", "execute", "after", "sync"))
    ):
        risks.append("method name is too generic to express a clear responsibility")

    if any(name.lower() in GENERIC_LOCAL_NAMES for name in local_names):
        risks.append("local variable names are too generic to express business meaning")

    if "tryLock(" in body and "unlock(" in body:
        guarded_cleanup = re.search(
            r"if\s*\((?:[^)]*(?:acquired|locked|tryLock|isHeldByCurrentThread)[^)]*)\)\s*\{[^{}]*unlock\s*\(",
            body,
            re.DOTALL,
        )
        if not guarded_cleanup:
            risks.append("lock may be released unconditionally after tryLock")

    if "AuthContextHolder.setContext(" in body and "finally" not in body:
        risks.append("context switch without visible finally restore")
    elif re.search(r"AuthContextHolder\.setContext\(", body) and "oldContext" in body and "finally" not in body:
        risks.append("context restore path is not explicit")

    if re.search(r"new(?:Single|Fixed|Cached|Scheduled)ThreadPool", body) and "shutdown" not in body:
        risks.append("executor created without visible shutdown")

    if "locking" in side_effect_categories and "resource_cleanup" in side_effect_categories and "mixed responsibilities across multiple workflow stages" not in risks:
        if len(side_effect_categories) >= 4:
            risks.append("stateful workflow mixes locking, side effects, and cleanup")

    return risks


def summarize_method(method: dict) -> MethodSummary:
    body = method["body"]
    calls = collect_method_calls(body)
    return MethodSummary(
        name=method["name"],
        signature=method["signature"],
        start_line=method["start_line"],
        end_line=method["end_line"],
        length=method["end_line"] - method["start_line"] + 1,
        parameter_count=0 if not method["params"].strip() else len([p for p in method["params"].split(",") if p.strip()]),
        comment_lines=sum(1 for line in body.splitlines() if line.strip().startswith("//")),
        method_calls=calls,
        stages=collect_stage_signals(calls),
        side_effects=collect_side_effects(body),
        risks=detect_risks(method),
    )


def summarize_file(path: Path, method_name: str | None = None) -> FileSummary:
    text = path.read_text(encoding="utf-8")
    methods = parse_methods(text)
    if method_name:
        methods = [method for method in methods if method["name"] == method_name]
        if not methods:
            raise SystemExit(f"Method not found: {method_name}")
    summaries = [summarize_method(method) for method in methods]
    summaries.sort(key=lambda item: (item.start_line, item.name))
    return FileSummary(
        file=str(path),
        total_lines=len(text.splitlines()),
        method_count=len(summaries),
        methods=summaries,
    )


def format_text(summary: FileSummary, method_name: str | None) -> str:
    lines = [
        f"FILE: {summary.file}",
        f"TOTAL_LINES: {summary.total_lines}",
        f"METHOD_COUNT: {summary.method_count}",
    ]
    if not method_name:
        lines.append("TOP_METHODS_BY_LENGTH:")
        for method in sorted(summary.methods, key=lambda item: item.length, reverse=True)[:10]:
            risk = "; ".join(method.risks) if method.risks else "none"
            lines.append(
                f"- {method.name} lines {method.start_line}-{method.end_line} "
                f"(len={method.length}, params={method.parameter_count}, risks={risk})"
            )
        return "\n".join(lines)

    for method in summary.methods:
        lines.extend(
            [
                "",
                f"METHOD: {method.name}",
                f"SIGNATURE: {method.signature}",
                f"LINES: {method.start_line}-{method.end_line} (len={method.length})",
                f"PARAMETERS: {method.parameter_count}",
                f"COMMENT_LINES: {method.comment_lines}",
                "STAGES:",
            ]
        )
        if method.stages:
            for stage, values in method.stages.items():
                lines.append(f"- {stage}: {', '.join(values)}")
        else:
            lines.append("- none detected")

        lines.append("SIDE_EFFECTS:")
        if method.side_effects:
            for category, values in method.side_effects.items():
                lines.append(f"- {category}:")
                for value in values[:6]:
                    lines.append(f"  {value}")
        else:
            lines.append("- none detected")

        lines.append("RISKS:")
        if method.risks:
            for risk in method.risks:
                lines.append(f"- {risk}")
        else:
            lines.append("- none detected")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize Java files for spring-refactor")
    parser.add_argument("file", help="Path to a Java file")
    parser.add_argument("--method", help="Method name to summarize in detail")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    path = Path(args.file).expanduser().resolve()
    if not path.is_file():
        parser.error(f"file not found: {path}")
    if path.suffix != ".java":
        parser.error("input must be a .java file")

    summary = summarize_file(path, args.method)
    if args.json:
        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    else:
        print(format_text(summary, args.method))
    return 0


if __name__ == "__main__":
    sys.exit(main())
