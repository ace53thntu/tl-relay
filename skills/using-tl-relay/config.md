# Workspace config

Every skill resolves its paths from this page. Each skill runs with no config file.

## Lookup

- The start directory is the session's working directory. Inside a linked git worktree, it is the main worktree: the parent of `git rev-parse --path-format=absolute --git-common-dir`.
- Walk up from the start directory to the nearest `.tl-relay/config.yaml`. The walk stops before `~`. A bare `.tl-relay/` directory is no marker.
- `~/.tl-relay/config.yaml` is the fallback. The workspace file wins key by key over it, and a key in neither file takes its default.

## Workspace

- The workspace root is the directory that holds the `.tl-relay/` of the found workspace config. Without one, it is the git top level of the start directory, else the start directory.
- `<workspace>` is the root's basename. Two workspace roots with the same basename share one `<runtime>`; set `state_dir` in one of them.

## Paths

- `<runtime>` is `<state_dir>/<workspace>`. `state_dir` defaults to `~/.tl-relay`.
- A relative value resolves against the workspace root, and a leading `~/` means the home directory. Skills pass absolute paths to scripts and subagents.

| Output under `<runtime>` | Written by |
|---|---|
| `specs/YYYY-MM-DD-<slug>.md` | `brainstorm` |
| `plans/YYYY-MM-DD-<slug>.md` | `write-plan` |
| `plans/lld/` | `write-lld` |
| `designs/<handle>/` | `tl-design`, `write-*`, `ingest-sources` |
| `hlds/<slug>.md` | `write-hla` |
| `audits/` | `technical-writing` |
| `plan-runs/<plan>/` | `run-plan` |

- `<design root>` is the directory that holds `designs/`: `<runtime>`, or the parent of `designs/` in a `CLAUDE.md` override.
- The `CLAUDE.md` section "Skill output targets" outranks each default, design sets included.
- `designs/<handle>/runs/` and `designs/<handle>/publish/` never follow the override and stay under `<runtime>`.

## Worktrees

- The root is the `CLAUDE.md` section "Worktree location", else `$WORKTREE_ROOT`, else `worktree_dir`, else `<state_dir>/worktrees`.
- Layout: `<root>/<repo>/<branch>`.

## Unset knowledge_dir

- `knowledge_dir` has no default. When set, it resolves against the workspace root, and it never resolves against a worktree.
- When it is unset, skip each of these steps and say so in one line:
  - reading hub pages (wiki, glossary, ADRs);
  - writing ADRs and glossary terms;
  - adding hub `index.md` entries;
  - reading `_templates/`;
  - running the hub `lint.sh`.
