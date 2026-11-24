# Builder check: subagent prompt

Once the written design exists, hand the block below to a fresh general-purpose subagent with both placeholders filled.

Placeholders:

- `[DOMAIN, e.g. software engineer, event planner, bakery consultant]`: the practitioner who would build this.
- `[DOCUMENT_PATH]`: the design doc.

```
Input
The file at [DOCUMENT_PATH] is a design document. Start by reading it in full.

Role
Read it as a talented [DOMAIN, e.g. software engineer, event planner, bakery consultant] who must plan the build from it.
The document is all you have: its author is out of reach.

Report
Return only the questions that block a good plan. Do not write the plan itself.
A question qualifies when you would otherwise be guessing, and a wrong guess costs something.
Pair each question with how its answer would change your plan.
Rank them by importance, highest first.

Leave out
- points the document says outright are the builder's call
- anything you could reasonably decide on your own
- nitpicks about wording

Empty report
If no question qualifies, reply with exactly: nothing important left
```

The dispatcher sorts the reply into piles, not the subagent. See the builder check in [SKILL.md](SKILL.md).
