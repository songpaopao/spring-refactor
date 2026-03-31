# spring-refactor

`spring-refactor` is a Codex skill for safely refactoring Java/Spring backend code.

It focuses on:

- large methods
- unclear responsibilities
- staged entry-method flow
- mandatory comments
- post-refactor review
- resource lifecycle safety such as lock release and conditional cleanup

## Structure

- `SKILL.md`: main skill definition
- `agents/openai.yaml`: UI metadata and default prompt
- `references/checklist.md`: refactor and review checklist

## Install

Copy this repository into your Codex skills directory as `spring-refactor`:

```bash
cp -R spring-refactor "${CODEX_HOME:-$HOME/.codex}/skills/spring-refactor"
```

## Use

```text
Use $spring-refactor to refactor this Java/Spring backend file while preserving external behavior.
```
