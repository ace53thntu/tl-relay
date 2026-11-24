# tl-relay

tl-relay is a set of skills, agents and two hooks for a tech lead. They carry a feature from design inputs to a pull request and stop for a human at each gate.

- `tl-design` takes a design set from source documents to filed tickets, through four gated stages: ingest, review, design and breakdown.
- `tl-implement` builds one breakdown row of a signed design set into one pull request.
- `write-plan`, `run-plan` and the other skills support both.

Claude Code gets the full set through the plugin. Cursor and Codex get the skills through `npx skills`.

## Install

### Claude Code plugin

```text
/plugin marketplace add ace53thntu/tl-relay
/plugin install tl-relay@tl-relay
```

The plugin ships the skills, the agents as `tl-relay:<name>`, the Workflow scripts, the SessionStart hook that loads `using-tl-relay` and the lesson hook. Plugin installs show each skill as `tl-relay:<name>`.

### Any agent through `npx`

```sh
npx skills add ace53thntu/tl-relay
npx skills add ace53thntu/tl-relay --skill brainstorm
npx skills add ace53thntu/tl-relay -a cursor
npx skills add ace53thntu/tl-relay -a codex
```

Install the plugin or the `npx` copies, not both. Both load each skill twice.

### Single-skill installs

`--skill <name>` suits the leaf skills: `brainstorm`, `debug-issue`, `test-first`, `verify-done`, `review-change`, `technical-writing` and `write-plan`. Some hand off to a follow-on skill, for example `brainstorm` to `write-plan` to `run-plan`, and `debug-issue` to `test-first` and `verify-done`. `run-plan`, `write-plan` and `review-change` read `route-subagents` for model choice.

Two bundles install together. `tl-design`, `tl-implement`, `ingest-sources`, `write-design`, `write-hla`, `write-lld` and `write-task-breakdown` check their sibling skills first and stop with the install command for any that is missing. The Build bundle carries `tl-design` for its Ask rule and retro step; running `tl-design` itself needs the Design bundle.

| Bundle | Skills |
|---|---|
| Design | `tl-design`, `ingest-sources`, `write-design`, `write-hla`, `write-lld`, `write-contract`, `write-task-breakdown`, `technical-writing`, `lens-qa-conformance`, `lens-qa-engineer`, `lens-security-engineer`, `lens-shared`, `lens-software-engineer`, `lens-solution-architect` |
| Build | `tl-implement`, `tl-design`, `write-plan`, `run-plan`, `review-change`, `verify-done`, `test-first`, `debug-issue`, `lens-qa-conformance`, `lens-shared` |

```sh
npx skills add ace53thntu/tl-relay --skill tl-implement --skill tl-design --skill write-plan --skill run-plan \
  --skill review-change --skill verify-done --skill test-first --skill debug-issue \
  --skill lens-qa-conformance --skill lens-shared
```

## Requirements

- Claude Code, Cursor or Codex.
- `git` and `gh`. `tl-implement` pushes branches and opens pull requests.
- `jq` for the hooks. Without it they print nothing.
- Optional: `TL_RELAY_LESSONS`, the absolute path of a folder of `<skill>.md` lesson files. The lesson hook injects the file for each skill that loads.
- `vale` for the writing gate of `tl-design`.
- `python3` 3.9 or later, for the skill scripts.

## Skills

| Skill | Use |
|---|---|
| `using-tl-relay` | Loads at session start and routes each task to a skill |
| `brainstorm` | Settles what to build before any new work |
| `write-plan`, `run-plan` | Writes an implementation plan, then runs its tasks through subagents |
| `test-first` | Writes the failing test before the code |
| `debug-issue` | Finds the root cause before a fix |
| `route-subagents` | Assigns each subagent role its model and effort |
| `explore-codebase` | Finds and reads existing code through the code index before grep |
| `review-change`, `verify-done` | Reviews a change, and checks the evidence before a claim of done |
| `tl-design` | Takes a feature from source documents to filed tickets |
| `tl-implement` | Builds one breakdown row of a signed design set into one pull request |
| `ingest-sources` | Snapshots and converts design inputs |
| `write-hla`, `write-design`, `write-lld`, `write-contract`, `write-task-breakdown` | Write the pages of a design set |
| `technical-writing` | Sets the writing rules and runs the Vale gate |
| `lens-*` | Review a design from one role: QA, security, software engineering, architecture |

### `ingest-sources` setup

PDF conversion needs one Python package. Install it once from the skill directory:

```sh
python3 -m venv <skill dir>/.venv && <skill dir>/.venv/bin/python -m pip install -r <skill dir>/requirements.txt
```

`<skill dir>` is the folder of the installed `ingest-sources` skill. Without the package the skill stops and names it.

## What each agent supports

| Capability | Claude Code (plugin) | Claude Code (`npx`) | Cursor, Codex (`npx`) |
|---|---|---|---|
| Skills | yes | yes | yes |
| Agents (`design-writer`, persona reviewers) | yes, as `tl-relay:<name>` | no | no |
| Workflow scripts | yes | yes, when the tool exists | no |
| Bootstrap hook | yes | no | no |

- Each agent file wraps one bound skill: a `lens-*` skill, or a `write-*` skill for `design-writer`. Every install carries the bound skills.
- Without the agents, a dispatch goes to a general subagent on the agent's model. Its prompt names the bound skill and the role line. With no subagent tool, the main session plays the role itself.
- A skill that starts a Workflow script runs its phases in sequence in the session when the Workflow tool is absent.

## Configuration

Every skill runs on built-in defaults. `.tl-relay/config.yaml` at the workspace root overrides them. [`config.example.yaml`](config.example.yaml) documents every key.

| Key | Default | Read by |
|---|---|---|
| `knowledge_dir` | `_knowledge` | `tl-design`, `write-*`, `ingest-sources`, `brainstorm`, `write-plan` |
| `state_dir` | `.tl-relay` | `tl-design`, `tl-implement` |
| `operator_language` | `en` | `tl-design`, `tl-implement` |
| `publish.command` | unset: `tl-design` step 12 reports a skip | `tl-design` |
| `publish.confirm_flag` | unset | `tl-design` |
| `tracker.comment` | unset: the `tl-implement` ticket comment reports a skip | `tl-implement` |
| `tracker.confirm_flag` | unset | `tl-implement` |
| `vale.vocab` | unset: Vale runs with the shipped vocabulary only | `technical-writing` |

- `publish.command` takes the placeholders `{dir}` and `{target}`. `tracker.comment` takes `{target}` and `{body_file}`.
- Commit `config.yaml`. Git-ignore `.tl-relay/sdd/` and `<state_dir>/designs/`. `run-plan` writes its own self-ignoring `.gitignore` inside `.tl-relay/sdd/`. `tl-design` and `tl-implement` add `<state_dir>/designs/` to the workspace `.gitignore`.
- A project `CLAUDE.md` overrides the role table in `route-subagents`, because user instructions outrank skills.

## Constraints

- A skill needs no config file and no home directory.
- Plugin name `tl-relay`, MIT licence, semver. The first release is `0.1.0`.

## Maintainers

The operator's tooling lives in [`maintainer/`](maintainer/README.md). Claude Code never loads it, though the plugin cache copies the folder.
