# Gates

`final_run.py score` runs gate 2. The agent runs gates 1, 3 and 4 itself after the commit. Each path is absolute.

The agent resolves `<home>` once per run and reuses the validated value. The candidate is `$AI_SDLC_HOME` when it is non-empty. Otherwise, the agent asks the operator for the path.
The agent validates the candidate with this command. It puts the candidate inside the single quotes and writes each embedded `'` as `'\''`:

`h='<candidate>'; case "$h" in "~/"*) h="$HOME/${h#\~/}";; esac; case "$h" in /*) test -f "$h/ai-sdlc.yaml" && test ! -e "$h/sdlc.py" && test ! -L "$h/sdlc.py" && printf '%s\n' "$h";; *) false;; esac`

`<home>` is the printed value. Every later command single-quotes it the same way and does not need the ambient variable.
On a nonzero exit with the ambient value, the agent asks the operator for the home.
On a nonzero exit with the operator's answer, the agent reports it and asks once more. After a second bad answer, the agent stops and reports.
A run with no operator reports the missing or invalid home to its caller and stops.
The agent never guesses a home and never edits home config.

1. `/usr/bin/python3 <repo>/skills/tests/run_tests.py` must print OK. Its overlap test must pass.
2. Every committed prompt, neighbours included, must pick its expected skill. `final_run.py score` runs them.
3. `export AI_SDLC_HOME='<home>'; base=$(git -C <repo> merge-base refs/remotes/origin/main HEAD) && /usr/bin/python3 <repo>/maintainer/sdlc.py check-neutral --repo <repo> && /usr/bin/python3 <repo>/maintainer/sdlc.py check-neutral --repo <repo> --range="$base..HEAD"` must exit zero. The first scan covers HEAD, and the second covers every commit the pre-push hook scans: tree, paths, message, author and committer.
4. Run `/usr/bin/python3 <repo>/skills/tests/overlap.py report | grep ' <name>/'`. Each line for the skill's files must start with `PASS`.

## Final run

Tuning is not the final run. The script `final_run.py` scores the trigger prompts, and the agent never scores them by hand.
Every command below runs in a fresh shell, so it sets `AI_SDLC_HOME` inline. `score` exits 2 without it.

1. The agent commits the work.
2. The agent runs `AI_SDLC_HOME='<home>' /usr/bin/python3 <repo>/maintainer/skills/write-skill/scripts/final_run.py --repo <repo> score --heldout <dir>`.
3. On exit 0, gate 2 has passed. The agent then runs gates 1, 3 and 4 on the commit.
4. The agent pushes only when `score` exited 0 and gates 1, 3 and 4 passed.

The held-out directory sits outside the checkout. A blind author writes it before tuning, as [trigger-prompts.md](trigger-prompts.md) describes.
A held-out set stays valid through tuning until its first `score` run. After that run, `score` exits 2 for the set on any other skill `name` or `description`, and the change needs a fresh set from a fresh author. A resume on the same fingerprint stays allowed.

| Exit | Meaning | Action |
|---|---|---|
| 0 | PASS | Run gates 1, 3 and 4. Push only when all three pass. |
| 1 | FAIL | Stop. Report the FAIL lines to the operator or caller. |
| 2 | Precondition or usage error | Read the message and fix the precondition. A session hook refusal follows the session hook rule below. |
| 3 | ERROR | Fix the infrastructure cause and rerun the same command once. A rerun resumes from the recorded runs. On a second exit 3, stop and report the output and exit code to the operator. |
| 4 | Another `score` holds the lock | Wait for that `score`, then rerun. `tune` takes no lock. |

A branch that changes `hooks/session-start-skills.sh` always exits 2 from `score`. The agent still runs gates 1, 3 and 4 on that branch.
When all three pass, the agent stops and reports the branch to the operator. When one fails, the gate failure rule below applies.
The operator decides whether to push with `--no-verify` and measure after the merge. The agent never uses `--no-verify` on its own.

On exit 1, the agent pushes nothing and the operator chooses drop or a new tuning pass.
A new pass must change a skill `name`, `description`, `when_to_use` or `disable-model-invocation`. A body-only edit keeps the recorded FAIL.
A prompt correction qualifies only when the operator approves it and the ledger records the reason.
A new pass also needs a fresh held-out set from a fresh author, because a held-out set that failed is burned. An abandoned attempt with an unresolved FAIL burns its set too.
On drop, the commit stays on the branch. The agent reports the commit SHA to the operator and leaves history alone until the operator orders its removal. It does not push that branch.

If gate 1, 3 or 4 fails after the commit, the agent does not push. It reports the commit SHA to the operator or caller.
A fix is a new commit. A gate 3 hit in an earlier unpushed commit needs a rewrite of that commit. A new commit cannot clear it.
The agent rewrites only its own unpushed commits. It reports a hit in any other commit to the operator and stops.
Each fix needs a new `score` run.

The overlap test allows at most 10% matched lines per file and no 3 matches in a row.
A line whose form a language or format fixes, such as a shebang, may go into `skills/tests/fixtures/overlap-fixed-lines.txt`.
Each entry there carries a reason. At most 5 lines per file may match that list, repeats included.

The report exits zero on any result, so read its lines. Never grep for `0/`, because it also matches inside `10/110`.

## Push gate install

After merge, the agent installs the pre-push hook for the main checkout. The agent omits `--home`, so a home mismatch stops the install.

1. Reuse `<home>` if this run validated it. Otherwise, resolve it with the command at the top of this file.
2. Run `AI_SDLC_HOME='<home>' AI_SDLC_REPO='<main>' /usr/bin/python3 '<main>/maintainer/sdlc.py' install --git-hook`.
3. Run `hook="$(git -C '<main>' rev-parse --path-format=absolute --git-common-dir)/hooks/pre-push" && test -f "$hook" && test -x "$hook" && grep -qF -e '# tl-relay pre-push hook' -e '# ai-sdlc pre-push hook' "$hook" && /usr/bin/python3 -c 'import os,shlex,sys; m=[l for l in open(sys.argv[1]) if l.startswith("main=")]; sys.exit(not (m and os.path.samefile(shlex.split(m[0])[0][5:], sys.argv[2])))' "$hook" '<main>'`.

`install` can exit 0 after it skips the hook, so step 3 decides the result. On a nonzero exit from any step, the agent stops and reports.
