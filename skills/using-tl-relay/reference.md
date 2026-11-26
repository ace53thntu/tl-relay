# using-tl-relay reference

Read this when two or more skills apply.

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
