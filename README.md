# spring-refactor

`spring-refactor` is a Codex skill for safely refactoring Java and Spring backend code.

It is designed for large methods, mixed responsibilities, stateful service flows, and cleanup-sensitive code. The skill helps keep external contracts stable while restructuring entry methods into clear stages with mandatory comments, post-refactor review, and explicit resource lifecycle checks.

## Highlights

- Split oversized methods into clear staged flows
- Clarify service responsibilities without changing external behavior by default
- Enforce comments for stage boundaries and non-obvious business intent
- Add post-refactor review as a required step
- Verify safe cleanup of locks, executors, streams, clients, and context state
- Detect unsafe unconditional cleanup such as `unlock()` after failed `tryLock()`

## Repository Layout

- `scripts/review_java_file.py`: summarize a Java file or method into a compact review artifact
- `scripts/review_git_diff.py`: summarize the current Java diff into a compact review artifact
- `SKILL.md`: main skill definition
- `agents/openai.yaml`: UI metadata and default prompt
- `references/checklist.md`: refactor and review checklist

## Installation

Copy this repository into your Codex skills directory as `spring-refactor`:

```bash
cp -R spring-refactor "${CODEX_HOME:-$HOME/.codex}/skills/spring-refactor"
```

## Usage

```text
Use $spring-refactor to refactor this Java/Spring backend file while preserving external behavior.
```

Before feeding a large file into the skill, generate a compact summary artifact:

```bash
python3 scripts/review_java_file.py /path/to/TaskServiceImpl.java --method receivePoints
```

Before reviewing a large set of changes, summarize the Java diff first:

```bash
python3 scripts/review_git_diff.py --repo /path/to/repo
```

## Design Principles

- Preserve external request and response contracts unless a change is declared first
- Keep entry methods readable as staged process orchestration
- Prefer small, local, reversible refactors over broad rewrites
- Require comments for major stages, ordering constraints, and side effects
- Treat review and resource cleanup verification as part of the refactor itself
