# Trigger prompts and description tuning

## Contents

- Writing the prompts
- Held-out prompts
- Tuning and scoring

## Writing the prompts

A separate blind author writes the prompts before anyone writes the description. The author never sees the description.

Give the author:

- the skill's purpose and class
- the names and topics of the neighbouring skills
- the file format below

Each prompt is a `.txt` file at `<repo>/skills/tests/prompts/<name>-<case>.txt`. This includes near-miss negatives that this skill owns. `tune` and the score tiers select prompts by the `<name>-` prefix. Line 1 reads `expect: <skill>`. Line 2 holds the prompt. The set holds:

- one explicit prompt that names the skill or its job
- one implicit prompt that names neither, in the wording of a plain request
- one or more neighbour negatives. Each `expect:` line names the neighbour that should win.

Make each prompt substantive, because a one-step request may bypass every skill. Vary register and phrasing. Make negatives near misses with shared keywords or an adjacent domain.

A prompt shares no run of 3 or more words with the description. Lowercase both texts, then split each into `[a-z0-9]+` words.
A shared run counts only when it holds a word outside `ai`, `sdlc`, `skills` and the tokens of `<name>`. Never copy a prompt's wording into the description.

## Held-out prompts

The blind author also writes at least one held-out prompt. Held-out prompts score the description and never tune it.

- Store them in a separate directory outside `skills/tests/prompts/`, because `run-triggers.sh` runs every `.txt` file in its prompts directory.
- Keep the held-out directory and the run ledger outside the repository checkout. The author never commits either.
- Start each file with an LF-terminated `expect: <skill>` line, followed by a non-empty prompt. Use the `.txt` extension.
- Never expect `using-tl-relay` in a held-out prompt.
- A held-out set stays valid through tuning until its first `score` run. After that run, `score` exits 2 for the set on any other skill `name` or `description`, and the change needs a fresh set from a fresh author.
- A held-out set that failed is burned, and so is the set of an abandoned attempt with an unresolved FAIL. A new attempt needs a fresh set from a fresh author.
- The tuner, who edits the description, reads no file in that directory.

## Tuning and scoring

1. Reuse `<home>` if this run validated it. Otherwise, resolve it with the command at the top of [gates.md](gates.md). Then run `AI_SDLC_HOME='<home>' /usr/bin/python3 <repo>/maintainer/skills/write-skill/scripts/final_run.py --repo <repo> tune <name> --runs 5`. The command scores the tuning prompts against the working tree.
2. Tune the description until each tuning prompt picks its expected skill. A FAIL during tuning stops nothing.
3. Know what `tune` does not do. It writes no record. It refuses `--heldout`, `TL_RELAY_TRIGGER_PROMPTS` and a skill with no prompt files.
4. When the description is ready, stop tuning. The held-out set and the neighbour prompts get scored only in "Final run" in [gates.md](gates.md).
5. If the final run fails, the operator chooses drop or a new tuning pass. A new pass meets the exit 1 rule in [gates.md](gates.md) and restarts at step 1 with a fresh held-out set.
