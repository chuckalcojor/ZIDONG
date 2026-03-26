# Skill: context-files-bootstrap

## Purpose

Create and maintain a multi-tool context setup using `AGENTS.md` as canonical source and synced adapter files for other tools.

## When to use

Use this skill when the user asks to:

- Create `AGENTS.md` from scratch
- Translate existing context files to a unified format
- Add `CLAUDE.md`, `GEMINI.md`, `COPILOT.md`, `CURSOR.md`, `CODEX.md`, `AGENT.md` adapters
- Keep all context files synchronized after process changes

## Output files

Mandatory:

- `AGENTS.md` (canonical)

Optional adapters (create only requested ones):

- `CLAUDE.md`
- `GEMINI.md`
- `COPILOT.md`
- `CURSOR.md`
- `CODEX.md`
- `AGENT.md`

## Workflow

1. Inspect existing docs (`README.md`, CI workflows, lint/test scripts, architecture docs).
2. Draft `AGENTS.md` with executable commands and explicit conventions.
3. Create adapter files as thin wrappers that point to `AGENTS.md`.
4. Verify consistency across files.
5. Return a short changelog with touched paths and any assumptions.

## AGENTS.md minimum sections

- Project overview
- Setup commands
- Development/test/lint/typecheck/build commands
- Code style and architecture rules
- Security and secret handling
- Contribution flow (commit/PR)

## Quality rules

- Prefer precise commands over generic text.
- Avoid duplicated policy text across adapters.
- Keep adapters short and stable.
- If something is unknown, mark as `TODO:` instead of inventing details.

## Adapter template

Use this exact structure for adapters:

```markdown
# <TOOL_FILE_NAME>

This repository uses `AGENTS.md` as the canonical agent context.

Read and apply first: `./AGENTS.md`

If this file conflicts with `AGENTS.md`, `AGENTS.md` wins.
If user instructions in chat conflict, user instructions win.
```

## Maintenance mode

When updating an existing project:

1. Update `AGENTS.md` first.
2. Refresh adapter files only if precedence text is missing or stale.
3. Do not add tool-specific behavior unless explicitly requested.

## Deliverable style

- Keep final response concise.
- Include list of created/updated files.
- Include 1-2 practical next steps.
