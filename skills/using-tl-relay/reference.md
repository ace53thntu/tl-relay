# using-tl-relay reference

Read this when two or more skills apply, or when instructions conflict.

## Order between skills

When several skills apply, sort them by kind. With several requests in one message, every request's process skills run before any implementation skill.

| Kind | Runs | Examples |
|------|------|----------|
| Process | First; it sets the approach | `brainstorm`, `debug-issue`, any other process skill |
| Implementation | After; it carries the approach out | `frontend-design`, the domain skills |

| Request | First | Then |
|---------|-------|------|
| "Build X" | `brainstorm` | Implementation skills |
| "Fix this bug" | `debug-issue` | Domain skills |

## Precedence of instructions

1. Your user's instructions rank highest: your instruction files (user and project `CLAUDE.md`, `AGENTS.md`) when present, and direct requests.
2. Skills rank next.
3. Default behavior ranks last.
4. A skill's workflow and instructions stand until your human partner explicitly tells you to set them aside. Nothing else lifts them.
