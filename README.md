# tl-relay

tl-relay is a set of agent skills for a tech lead. It takes a feature from its source documents through a reviewed design to one pull request per task. The agent drafts, reviews and builds. You sign each gate before the work moves on.

- `tl-design` turns a PRD, story register or prototype into a design set and its task breakdown.
- `tl-implement` builds one breakdown row of a signed design set into one pull request.
- The process skills (`brainstorm`, `write-plan`, `run-plan`, `test-first`, `review-change` and others) work on their own in any project.

Claude Code gets skills, agents and hooks through the plugin. Cursor, Codex and other agents get the skills through `npx skills`.

## Install

Pick one channel per agent. A plugin install plus an `npx` install loads every skill twice.

### Claude Code plugin

Run in Claude Code:

```text
/plugin marketplace add ace53thntu/tl-relay
/plugin install tl-relay@tl-relay
```

The plugin installs the following:

- every skill, named `tl-relay:<skill>`
- the agents, named `tl-relay:<agent>`
- the Workflow scripts
- a SessionStart hook that loads `using-tl-relay`
- a lesson hook

To update, run `claude plugin marketplace update tl-relay` and `claude plugin update tl-relay@tl-relay`, then restart Claude Code.

### `npx skills add`

`npx skills` installs the skills for Claude Code, Cursor, Codex and the other agents that the [skills command-line tool](https://github.com/vercel-labs/skills) supports. It does not install agents or hooks.

Inside a project, `npx skills add` installs the skills into that project. Add `-g` to install them for your user account instead.

```sh
npx skills add ace53thntu/tl-relay              # all skills, for the agents the CLI detects
npx skills add ace53thntu/tl-relay -g           # all skills, for your user account
npx skills add ace53thntu/tl-relay -a cursor    # Cursor only
npx skills add ace53thntu/tl-relay -a codex     # Codex only
npx skills add ace53thntu/tl-relay --list       # list the skills without installing
```

To install one skill, add `--skill <name>` and add `--skill using-tl-relay`. The skills read their path rules from `using-tl-relay`. That suits the skills that stand alone: `brainstorm`, `debug-issue`, `test-first`, `verify-done`, `review-change`, `technical-writing`, `explore-codebase` and `write-plan`. A few of them hand off to the next skill in a chain, so install the chain together: `brainstorm`, `write-plan`, `run-plan`, `route-subagents` and `review-change`, or `debug-issue`, `test-first` and `verify-done`.

### Bundles

The design and build workflows each need a set of skills. Before it runs, each workflow skill checks for its siblings. If one is missing, the skill stops and prints the install command.

| Bundle | Skills |
|---|---|
| Design | `using-tl-relay`, `tl-design`, `ingest-sources`, `write-design`, `write-hla`, `write-lld`, `write-contract`, `write-task-breakdown`, `technical-writing`, `lens-qa-conformance`, `lens-qa-engineer`, `lens-security-engineer`, `lens-shared`, `lens-software-engineer`, `lens-solution-architect` |
| Build | `using-tl-relay`, `tl-implement`, `tl-design`, `write-plan`, `run-plan`, `route-subagents`, `review-change`, `verify-done`, `test-first`, `debug-issue`, `lens-qa-conformance`, `lens-shared` |

The Build bundle carries `tl-design` for its Ask rule and its retro step. To run `tl-design` itself, install the Design bundle.

Design bundle:

```sh
npx skills add ace53thntu/tl-relay --skill using-tl-relay --skill tl-design --skill ingest-sources --skill write-design \
  --skill write-hla --skill write-lld --skill write-contract --skill write-task-breakdown --skill technical-writing \
  --skill lens-qa-conformance --skill lens-qa-engineer --skill lens-security-engineer --skill lens-shared \
  --skill lens-software-engineer --skill lens-solution-architect
```

Build bundle:

```sh
npx skills add ace53thntu/tl-relay --skill using-tl-relay --skill tl-implement --skill tl-design --skill write-plan --skill run-plan \
  --skill route-subagents --skill review-change --skill verify-done --skill test-first --skill debug-issue \
  --skill lens-qa-conformance --skill lens-shared
```

### Requirements

- Claude Code, Cursor or Codex.
- `git`, and `gh` for `tl-implement`, which pushes branches and opens pull requests.
- `python3` 3.9 or later for the skill scripts.
- `jq` for the plugin hooks. Without `jq` the hooks print nothing.
- `vale` for the writing gate in `technical-writing` and `tl-design`.
- Node.js with `npx` for `write-contract`. It runs `@redocly/cli` and downloads it on first use.

`ingest-sources` needs one Python package for PDF conversion. Install it, where `<skill dir>` is the folder of the installed `ingest-sources` skill:

```sh
python3 -m venv <skill dir>/.venv && <skill dir>/.venv/bin/python -m pip install -r <skill dir>/requirements.txt
```

Without the package, `ingest-sources` stops and prints this command with the real `<skill dir>`. A plugin update installs a new version folder, so run the command again after each update.

## Skills

| Group | Skill | Use |
|---|---|---|
| Session | `using-tl-relay` | Loads at session start and routes each task to a skill |
| Process | `brainstorm` | Settles what to build, and why, before any new work |
| Process | `write-plan` | Writes an implementation plan from approved requirements |
| Process | `run-plan` | Runs a plan's tasks through fresh subagents, with a review after each task |
| Process | `route-subagents` | Assigns each subagent role its model and effort |
| Process | `explore-codebase` | Finds and reads existing code through the code index before grep |
| Process | `test-first` | Writes the failing test before the code |
| Process | `debug-issue` | Finds the root cause before any fix |
| Process | `review-change` | Reviews a finished task or feature against its requirements |
| Process | `verify-done` | Runs the check behind a claim of done, fixed or passing |
| Workflow | `tl-design` | Takes a feature from source documents to a signed design set and its tickets |
| Workflow | `tl-implement` | Builds one breakdown row of a signed design set into one pull request |
| Workflow | `ingest-sources` | Snapshots design inputs, converts them to Markdown and records what changed between revisions |
| Design pages | `write-hla` | Writes a High-Level Architecture document |
| Design pages | `write-design` | Writes or changes a page of a design set |
| Design pages | `write-lld` | Writes a Low-Level Design |
| Design pages | `write-contract` | Writes an OpenAPI 3.1 contract and checks it against the design |
| Design pages | `write-task-breakdown` | Generates and checks the task breakdown of a signed design |
| Design pages | `technical-writing` | Sets the writing rules and runs the Vale gate |
| Lenses | `lens-solution-architect` | Reviews boundaries, contracts, data ownership and NFRs |
| Lenses | `lens-software-engineer` | Reviews whether an engineer could build from the pages |
| Lenses | `lens-security-engineer` | Reviews authentication, sensitive data, secrets and abuse cases |
| Lenses | `lens-qa-engineer` | Checks that each use case and route has a testable rule |
| Lenses | `lens-qa-conformance` | Maps each design rule of a breakdown row to code and a test in the diff |
| Lenses | `lens-shared` | Holds the finding schema the lenses share. Nobody invokes it directly |

## Agent support

| Capability | Claude Code, plugin | Claude Code, `npx` | Cursor, Codex, `npx` |
|---|---|---|---|
| Skills | yes | yes | yes |
| Agents (`design-writer` and the persona reviewers) | yes, as `tl-relay:<agent>` | no | no |
| Workflow scripts | yes | yes, when the Workflow tool exists | no |
| SessionStart hook | yes | no | no |

- Each agent file wraps one skill: a `lens-*` skill, or a `write-*` skill for `design-writer`. Every install carries those skills.
- Without the agents, a skill dispatches a general subagent on the agent's model, with a prompt that names the skill and the role. With no subagent tool, the main session plays the role itself.
- Without the Workflow tool, a skill runs the phases of its Workflow script in sequence in the session.
- `ingest-sources` first dispatches one subagent per slice when the session has a subagent tool.

## Configuration

Every skill runs with no config. The lookup and the paths follow [`skills/using-tl-relay/config.md`](skills/using-tl-relay/config.md). To override a default, add `.tl-relay/config.yaml` at the workspace root, or `~/.tl-relay/config.yaml` for every workspace. The workspace file wins key by key:

```yaml
state_dir: ~/work/tl-relay-state
operator_language: en
publish:
  command: "my-docs-cli push {dir} --parent {target}"
  confirm_flag: "--yes"
tracker:
  comment: "my-tracker comment {target} --body-file {body_file}"
  confirm_flag: "--yes"
vale:
  vocab: docs/vale/accept.txt
```

| Key | Default | Effect | Read by |
|---|---|---|---|
| `knowledge_dir` | unset | A shared hub that skills read, and that receives ADRs, glossary terms and index entries | `technical-writing`, `write-hla`, `write-lld`, `tl-design` |
| `state_dir` | `~/.tl-relay` | Root of `<runtime>`, which holds specs, plans, design sets and plan runs. Worktrees fall back to `<state_dir>/worktrees` | every skill that writes |
| `worktree_dir` | unset | Worktree root after `$WORKTREE_ROOT` | `run-plan`, `tl-implement` |
| `operator_language` | `en` | Language of the questions the workflows ask you | `tl-design`, `tl-implement` |
| `publish.command` | unset: the publish step reports a skip | Publishes the staged design pages. `{dir}` is the staged tree and `{target}` is the target you name | `tl-design` |
| `publish.confirm_flag` | unset | The flag the skill adds once you approve the dry run | `tl-design` |
| `tracker.comment` | unset: the ticket comment reports a skip | Posts the ticket comment. `{target}` is the ticket key and `{body_file}` is the comment file | `tl-implement` |
| `tracker.confirm_flag` | unset | The flag the skill adds once you approve the dry run | `tl-implement` |
| `vale.vocab` | unset: Vale uses the shipped vocabulary | Extra accepted words, one per line | `technical-writing` |

- A relative path resolves against the workspace root.
- Commit `.tl-relay/config.yaml`. `run-plan` writes a `.gitignore` in each plan-runs dir. With a `state_dir` inside a git tree, `tl-design` and `tl-implement` ignore `designs/*/publish/` and `designs/*/runs/`.
- A project `CLAUDE.md` or `AGENTS.md` outranks the skills. A model rule in it overrides `route-subagents`.
- [`config.example.yaml`](config.example.yaml) documents every key.

## Lessons

Set `TL_RELAY_LESSONS` to the absolute path of a folder of `<skill>.md` files. Name each file after the skill, without the `tl-relay:` prefix. A lesson replaces a default of that skill.

In Claude Code, set the variable in the `env` block of `settings.json`. Otherwise, export it in the shell that starts the agent.

- With the plugin, the lesson hook injects the matching file when a skill loads.
- With `npx skills`, a step in `using-tl-relay` reads `$TL_RELAY_LESSONS/<skill>.md` before the skill runs.

## Licence

MIT. See [`LICENSE`](LICENSE). Releases follow semver.

## Maintainers

Maintainer tooling lives in [`maintainer/`](maintainer/README.md). No install channel loads it as a skill.
