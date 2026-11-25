# tl-relay maintainer notes

This folder holds the operator's tooling. Claude Code never loads it, though the plugin cache copies the folder. The plugin and `npx skills` expose the root `skills/`, `agents/` and `hooks/` only.

`maintainer/sdlc.py` has two commands. `install` registers the guardrail hooks and writes `env.sh`. `check-neutral` scans committed files for the home's neutrality patterns.

## Repository layout

| Path | Holds |
|---|---|
| `maintainer/sdlc.py` | The command line: `install` and `check-neutral` |
| `maintainer/runtime/` | The modules behind those two commands, and their tests |
| `maintainer/hooks/` | Guardrail hooks, `git-pre-push`, the settings fragments that register them, and their tests |
| `maintainer/skills/` | The operator-only skills `write-skill` and `retro` |
| `maintainer/tl-relay.yaml` | Repository config. It holds only `apiVersion` and `kind` |
| `maintainer/tl-relay.example.yaml` | The template for the local config |
| `maintainer/ci/stub-claude` | The stub `claude` that CI puts first on `PATH` |
| `skills/`, `agents/`, `hooks/` | The public plugin content. Root `hooks/` holds the bootstrap hook and the lesson hook |
| `.claude-plugin/` | `plugin.json` and `marketplace.json` |
| `config.example.yaml` | The template for a workspace's `.tl-relay/config.yaml` |
| `.github/workflows/test.yml` | CI: every suite below plus the Vale gate, on push and pull request |

## Requirements

- macOS or Linux, with `/usr/bin/python3` 3.9 or later. The runtime uses only the standard library.
- Claude Code (`claude`).
- `git` and `gh`. `tl-implement` pushes branches and opens pull requests.
- `jq` for the hooks.
- `vale` for the writing gate of `tl-design`.

## Install

1. Clone the repository outside the workspace it works on.
2. Create the home, which holds the local config. `install` does not create it. Any absolute path works. Without `--home`, the tooling falls back to `~/.tl-relay`.

   ```sh
   mkdir -p <home>
   ```

3. Copy `maintainer/tl-relay.example.yaml` to `<home>/tl-relay.yaml` and set `project.root` to the workspace root.
4. Preview the hook changes:

   ```sh
   /usr/bin/python3 maintainer/sdlc.py install --dry-run --git-hook --home <home>
   ```

5. Install the hooks:

   ```sh
   /usr/bin/python3 maintainer/sdlc.py install --git-hook --home <home>
   ```

6. Link every skill and agent into `~/.claude`. Run it from the checkout root. The loop skips a name that already exists there and prints it:

   ```sh
   mkdir -p ~/.claude/skills ~/.claude/agents
   for skill in "$PWD"/skills/*/SKILL.md "$PWD"/maintainer/skills/*/SKILL.md; do
     dir=$(dirname "$skill")
     link=~/.claude/skills/$(basename "$dir")
     if [ -e "$link" ] || [ -L "$link" ]; then echo "skip $link"; else ln -s "$dir" "$link"; fi
   done
   for agent in "$PWD"/agents/*.md; do
     link=~/.claude/agents/$(basename "$agent")
     if [ -e "$link" ] || [ -L "$link" ]; then echo "skip $link"; else ln -s "$agent" "$link"; fi
   done
   ```

   Link into `~/.claude` even when you use another Claude config directory. The `technical-writing` skill runs its Vale wrapper from `<skill dir>/vale/run.sh`.

`--git-hook` also writes `<git-common-dir>/hooks/pre-push`, which runs `maintainer/skills/write-skill/scripts/final_run.py check` from the main checkout before every push. A plain `install` never writes it and prints one line when it is missing or names another home. `install --git-hook` exits 1 and changes nothing on a `pre-push` it did not write, when `core.hooksPath` is set, and when the main checkout lacks `final_run.py` or `maintainer/sdlc.py`. A plain `install` also prints one line for those cases and for a hook that is not executable.

`install` writes `<home>/env.sh` and the rendered hook fragments under `<home>/hooks/`. It merges the hooks into the `settings.json` of each directory in `install.claude_config_dirs`, and into `<project.root>/.claude/settings.json`. A second run with the same `--home` changes nothing. A bare rerun in a shell without `TL_RELAY_HOME` or `AI_SDLC_HOME` looks in the default home (see Fallbacks) and exits 1. Without a local config, `install` exits 1.

`install` also writes `TL_RELAY_HOME` into the `env` block of each user `settings.json`, and keeps the other `env` keys. `install` never adds `TL_RELAY_HOME` to `<project.root>/.claude/settings.json`. When that file names a different home, `install` exits 1, and `install --home` removes the key. When `settings.local.json` names a different home, `install` exits 1 and asks you to delete the key.

- Open Claude Code sessions pick up the new home after a restart.
- Without `--home`, `install` uses `TL_RELAY_HOME` from the shell, else `AI_SDLC_HOME`, else the default home (see Fallbacks). It exits 1 when a user `settings.json` already names a different home. Pass `--home` to replace it.
- `maintainer/sdlc.py` run outside Claude Code needs `export TL_RELAY_HOME=<home>` in your shell profile.
- When the home sits on a volume that is not mounted, `require-guardrails.sh` denies every other tool in every Claude Code session. Read, Edit, Write, Glob and Grep stay allowed. Mount the volume to fix it.
- When the tl-relay checkout sits on the unmounted volume, the hook script is missing and `/bin/sh` exits 127. Claude Code treats that exit code as non-blocking, so the guardrails are off.
- Inside Claude Code, the `settings.json` value beats a shell `export`. One Claude config directory therefore holds one home, and the last `install --home` wins in user settings. Each `<project.root>/.claude/settings.json` keeps the old home in its hook commands until `install` runs again for that `project.root`.

## Configuration

Config has two layers.

| Layer | File | Holds |
|---|---|---|
| Repository | `maintainer/tl-relay.yaml` | `apiVersion` and `kind` only |
| Local | `<home>/tl-relay.yaml` | Workspace root (`project.root`), Claude config directories (`install`), neutrality patterns, and the `operator_language` that `retro` reads |

`<home>` is `$TL_RELAY_HOME`, else `$AI_SDLC_HOME`, else the default home (see Fallbacks). `sdlc.py`, `install`, `retro` and the guardrail hooks find the home this way. Choose it with `install --home`, which writes `TL_RELAY_HOME` into each user `settings.json`.

The public skills read `.tl-relay/config.yaml` in the workspace, never the local config. The publish command and the ticket comment template live there. The local config keeps only what the maintainer tooling reads. `maintainer/tl-relay.example.yaml` shows the template.

## Fallbacks

Installs from before the rename keep working through these fallbacks. The new name always wins.

- `TL_RELAY_HOME` wins. `sdlc.py`, `install`, `retro` and the guardrail hooks read `AI_SDLC_HOME` when `TL_RELAY_HOME` is unset or empty.
- The default home is `~/.tl-relay`, or `~/.ai-sdlc` when only that one exists.
- `<home>/tl-relay.yaml` wins. The tooling reads `<home>/ai-sdlc.yaml` when it is the only file. `apiVersion: ai-sdlc/v2` still loads.
- The guardrail hooks read `AI_SDLC_HOME` and the five `AI_SDLC_<v>` names from the environment or `env.sh` when the new names are missing.
- `install` replaces a same-home `AI_SDLC_HOME` key with `TL_RELAY_HOME` in each user `settings.json`. It refuses a key that names another home unless you pass `--home`. The project `settings.json` keeps a same-home `AI_SDLC_HOME`. `install` never edits `settings.local.json`.
- `install` and the write-skill gate accept the old pre-push hook marker.

Not migrated:

- `install` never renames `<home>/ai-sdlc.yaml` and never moves `~/.ai-sdlc`.
- A pre-push hook installed before the rename blocks the pushes the write-skill gate checks until you rerun `sdlc.py install --git-hook`. `install` prints a notice. The gate checks skill changes, annotated tags, and tag or notes pushes with commits not on `origin/main`.
- The write-skill scripts (`final_run.py`) read `TL_RELAY_HOME` only. The `gates.md` commands set it inline.
- `TL_RELAY_TRIGGER_*` and every other internal variable read no old name.
- The write-skill scripts do not read records under `<git common dir>/ai-sdlc/`. They score branches again that an earlier run scored.

## Commands

Run each command as `/usr/bin/python3 maintainer/sdlc.py <command>`. `maintainer/sdlc.py <command> --help` lists the arguments.

| Command | Action |
|---|---|
| `install [--dry-run] [--home <dir>] [--git-hook]` | Register the hooks |
| `check-neutral [--repo <path>] [--range <rev-range> \| --tag-object <tag>]` | Fail when a committed file matches a local neutrality pattern |

## Maintainer skills

| Skill | Use |
|---|---|
| [`write-skill`](skills/write-skill/SKILL.md) | Authors or revises a skill, with baseline runs and trigger prompts as proof |
| [`retro`](skills/retro/SKILL.md) | Reads the day's interactive sessions and writes lessons and feedback memories that cut routine questions |

The public skills are listed in the [root README](../README.md).

## Retro schedule

`retro` runs headless at 22:00 from a launchd agent. Save the plist below as `~/Library/LaunchAgents/<label>.plist`. Then run `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<label>.plist`.

Replace each placeholder with an absolute path or a name. launchd expands neither `~` nor `$HOME`.

| Placeholder | Value |
|---|---|
| `<label>` | The job name, such as `com.<you>.tl-relay-retro` |
| `<claude>` | The output of `command -v claude` |
| `<home>` | The maintainer home, the value of `TL_RELAY_HOME` |
| `<config>` | The Claude config folder, the value of `CLAUDE_CONFIG_DIR` |
| `<user>` | The output of `id -un`. Without `USER`, `claude` cannot read its login and prints `Not logged in`. |
| `<node-bin>` | The folder of `command -v node`. Hooks run `node`, and launchd does not load your shell profile. |
| `<workdir>` | `<home>`. When `<home>` sits on an external volume, use your home folder instead. |
| `<log>` | `<home>/launchd.log`. When `<home>` sits on an external volume, use `<your home folder>/Library/Logs/tl-relay-retro.log`. |

On an external volume, launchd exited with code 78 before it opened `<home>/launchd.log` or entered `<home>`. Keep both on the internal disk.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string><label></string>
  <key>ProgramArguments</key>
  <array>
    <string><claude></string>
    <string>-p</string>
    <string>/retro</string>
    <string>--model</string>
    <string>opus</string>
    <string>--allowedTools</string>
    <string>Read Glob Grep Bash Write Edit</string>
  </array>
  <key>WorkingDirectory</key><string><workdir></string>
  <key>StandardOutPath</key><string><log></string>
  <key>StandardErrorPath</key><string><log></string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>TL_RELAY_HOME</key><string><home></string>
    <key>CLAUDE_CONFIG_DIR</key><string><config></string>
    <key>USER</key><string><user></string>
    <key>LOGNAME</key><string><user></string>
    <key>PATH</key><string><node-bin>:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>22</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
</dict>
</plist>
```

launchd runs a missed job at the next wake when the Mac sleeps through 22:00. Run `launchctl kickstart gui/$(id -u)/<label>` once to test it, then check `<home>/retro/reports/` and `<log>`. To listen while you work, run `/retro listen` in a session.

`retro` detects corrections and recommended options from English words. To add words in another language, write `<home>/retro/patterns.json`. Each key takes a list of literal words that `retro` adds to the English ones:

```json
{
  "recommended": ["<word>"],
  "correction_prefix": ["<word>"],
  "correction_rule": ["<phrase>"]
}
```

`correction_prefix` words count only at the start of a message. `digest.py run` exits 2 on an unknown key or a value that is not a list of strings.

## Tests

Run each command from the checkout root, one suite at a time. CI runs the same list from `.github/workflows/test.yml`:

```sh
/usr/bin/python3 skills/tests/run_tests.py --all
/usr/bin/python3 -m unittest discover -s maintainer/runtime/tests -p 'test_*.py'
sh maintainer/hooks/tests/run.sh
for s in ingest-sources tl-design write-contract write-task-breakdown; do
  /usr/bin/python3 -m unittest discover -s skills/$s/scripts -p 'test_*.py'
done
/usr/bin/python3 -m unittest discover -s maintainer/skills/retro/scripts -p 'test_*.py'
sh skills/technical-writing/vale/test.sh
```

Copy `maintainer/ci/stub-claude` to a folder first on `PATH` as `claude`, and set `CLAUDE_STUB_LOG` to an empty file. No suite may call the real `claude`, so the log stays empty. `run_tests.py` runs the units in parallel. Without `--all` it skips `test_final_run` and `test_triggers` when the diff from `origin/main` touches none of their inputs.

## Trigger suite

`skills/tests/run-triggers.sh` runs each prompt in `skills/tests/prompts/` against a real `claude` and checks which skill loads. It stays a local run and is not part of CI. `TL_RELAY_TRIGGER_AGENT`, `TL_RELAY_TRIGGER_PROMPTS` and `TL_RELAY_TRIGGER_TIMEOUT` override the agent, the prompt folder and the per-prompt timeout.

## Pre-push gate

`install --git-hook` writes the `pre-push` hook. It runs `maintainer/skills/write-skill/scripts/final_run.py check` from the main checkout before every push. The write-skill records live at `<git common dir>/tl-relay/final-run.jsonl`.

## Neutrality

The repository holds the core only: no organisation names and no runtime data. The names to keep out live in `neutrality.patterns` of the local config, so the list itself never lands in the repository. Run `maintainer/sdlc.py check-neutral` before each push. It exits 0 when no committed file matches.
