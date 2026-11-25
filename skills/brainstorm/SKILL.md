---
name: brainstorm
description: You MUST use this before any creative work - creating features, building components, adding functionality, modifying behavior, or planning anything new, in software or out of it (a talk, a business, a renovation).
---

# Brainstorming

Your picture of what the person wants is thinner than it feels. Before anything gets built, learn what they want and why they want it.

A known why is what lets you settle the unmentioned choices as they would. Asking also serves them: many people have not finished deciding, and answering is how they get there.

## Before the first reply

**Investigate before the first reply** whenever the project already exists or they gave you context.

Context means anything they handed over: an earlier conversation, files they named, a handoff, a plan or a spec.

- Sources: everything they referred to, plus the code or material wired to it.
- Stop point: you can explain today's behaviour of the parts involved, and how far the change reaches.
- Skip any question whose answer already sits in the project or in what they gave you.
- No question reopens a point they have already settled.

With that done, take stock of what you know about the what and the why. The table picks what the first message does.

| What you know | First move |
|---|---|
| The request settles everything that matters, such as "rename the Export button to Download" | No conversation needed. Make the change as the quick job it is, then report what you did. |
| Something non-trivial is still open | Start the conversation with the [first message](#first-message). |

### Sequence to implementation

Implementation waits for these four steps, in this order:

1. They choose one approach from a message that carries only approaches ([Approaches](#approaches)).
2. You draft the design doc in its short or full form ([Sizing](#sizing)).
3. They approve the doc.
4. You invoke `write-plan`.

Shortcut: nothing is open at the first message, and only one sensible way exists. Then steps 1 to 3 all happen inside that first message.

Two kinds of work fall outside implementation, so this sequence does not bind them. One is a [spike](#spikes) they agreed to. The other is doing the task once they opted out of questions.

## First message

The first message must move the work forward. Choose its body by how specific the request is, then its ending by whether they asked for this conversation.

**Request is specific.** They already said what they want, through a spec, a plan or a detailed request. Treat a spec as likely to have gaps, and check it with them before relying on it. Assemble the message from these parts, about 200 words in all:

| Part | Content |
|---|---|
| Restatement | What it is, who it serves, and the why as far as they gave it. Use your own words. This lets them check its shape. |
| Findings | The current behaviour of the parts involved, and what the change reaches into. |
| Blind spot, if any | Something they may not have weighed that would alter the ask or the build: a cheaper path, a conflict, a constraint. Say it plainly. |
| Correction line | One line asking them to correct anything you got wrong. |
| Close | Pick from the next table. |

Discussion of how to build it stays out. That waits for [Approaches](#approaches).

Check the rows below from the top; the first row that matches picks the close. A missing why therefore always wins.

| Situation | Close with |
|---|---|
| The why is missing: they never stated it, even if you could guess it | One open question about the why. Use their terms and offer no options. |
| The why is known, and a point still open would change the build | Ask about the point that moves the build most. Nameable choices get a concrete sketch each, a trade-off each, and your recommendation. |
| The why is known, nothing is open, and one sensible way exists | Propose the short design in three parts: the approach, a line ruling out the alternatives, and a few-line design. Ask for approval. |

A yes to that short design settles approach and design together. Record what they approved in a short design doc, then move to the plan.

**Request is not specific.** They have not said what they want yet.

- Ask one open question, in their terms, about the biggest unsettled thing.
- Say why you ask: what the answer changes in the build.
- Example: someone wants "an app for my running club". You could write: "If members mostly need this week's route, one shared page covers it. If they log their own runs, it needs accounts and storage. What do you picture people doing in it first?"

**They asked for brainstorming**, by name, by invoking this skill, or by asking to talk the design through. End the message there.

**They did not ask for it.** Add one light line offering to skip the questions and just start. For example: "Happy to skip the questions and just get going, if you'd prefer."

- They accept → this skill ends. First state, in one plain line, any significant choice of how it gets made, such as platform, language or medium. Then carry out the task via the usual workflow.

Nothing else goes into the first message.

## Conversation rules

### When to ask

- [ ] The answer changes the build, and neither request nor project holds it → ask.
- [ ] Anything short of that → decide. Tell them the decision with its reason, so they can correct it, and carry on.
- [ ] Torn between asking and proposing → a proposal with a reason they can correct often serves better.
- [ ] Write-ups, file locations, further digging and presentation format are yours every time → act, and mention that you did.
- [ ] They say "just guess" or "what do you think?" → put a concrete proposal on the table.

### How to ask

- [ ] One question at a time. The single exception is the builder check's "theirs" pile, which goes out in one message.
- [ ] Use plain language, pitched a notch above their level. Use their vocabulary. Use no process jargon.
- [ ] Never quote this skill to them.
- [ ] Be clear and brief, and lead with what matters. From your findings, give the most important and offer the rest.
- [ ] Fit each question to their project and to what they said.
- [ ] Root each question in a finding or in what they just answered. Aim it at a consequence or a missed case. For instance, after learning that orders close at noon on Friday: "A payment fails at 11:58 and the retry lands at 12:03. Does that order count?"
- [ ] Reason for a question not obvious? Name what its answer would change, or what you expect to learn.

### Open questions and named choices

- [ ] Why still unknown → open questions only, with no sample answers. Offered options swap your framing in for their intent; their own phrasing keeps it.
- [ ] Why known → for a decision with nameable choices, sketch every choice concretely, with trade-off and recommendation.
- [ ] [Approaches](#approaches) handle the build method only. On what they want, let them describe it before you propose anything.

### Who owns the how

How it gets made covers the medium, tools, materials and resources. For an app that means platform, language and libraries; for a painting, the medium.

- [ ] Listen for which decisions they want to keep. Their wording usually shows it.
- [ ] They raise the how, or ask about trade-offs: give options with your pick.
- [ ] They talk only about outcomes: they handed you the how. Make the calls and state each one in a line.
- [ ] Existing work: build on the tools and materials it already uses.
- [ ] The design labels each choice you made as yours. It never presents one as their agreement.

### Ground to cover

The conversation should reach each area below at some point. The table is a map, never a questionnaire to recite.

| Area | Covered once you know |
|---|---|
| Nature | What kind of thing it is, and what sets it apart |
| Timing and success | Why it matters now, and how they will judge success |
| Scope | Goals, non-goals and anti-goals. An anti-goal is a result that would count as failure despite working technically. |
| Prior art | Examples elsewhere that they loved or hated |
| Current state | What exists already, and what they have tried |
| Details | The specifics they care about |

### Looking and showing

- [ ] With some ground covered, dig further where it helps: the web, their files and data, the codebase or project. Report what you searched for and what turned up.
- [ ] Would seeing it help them more than reading it? Then add a text sketch, a few lines long, of the thing they would look at.

### Spikes

Agentic work still runs as waterfall, only at high speed. That makes a rough disposable build a low-cost answer to two questions: what do they actually want, and is it feasible?

- [ ] Offer a spike when it would help.
- [ ] They only want a spike → step aside and let them have it.
- [ ] A spike bypasses planning, the implementation process and review. It carries no tests or minimal ones, and nobody expects it to be bulletproof.
- [ ] Feed the spike's lessons back into the conversation.

## Approaches

Approaches come after you understand the what and the why, and before any write-up. Send them as a standalone message.

1. Generate several real alternatives.
2. Cut the weak ones: anything that conflicts with the why, or that the existing work excludes.
3. Make each of the two or three survivors concrete enough to picture. Tie each to the project's real behaviour and state its trade-off.
4. Name your recommendation with its reason, then ask them to choose. When the how is yours, announce that you are proceeding with your pick.
5. A single sensible way → state that here and give the reason each alternative fails. Send the design in the following message.

## Playback

> The conversation alternates to the end: questions, a playback, more questions. A playback is due when one part is clear enough to put into words. A part can be the purpose and audience, or the behaviour of one piece.
>
> Write that part back to them in roughly 200–300 words, then turn your questions to the next part. The final playback sweeps up everything left. Close each one by asking what it gets wrong or leaves out.
>
> Credit to them only what they actually said. Label everything you filled in as your proposal, with its reason.
>
> Before you send a playback:
> - Describes something they will look at (page, screen, schedule, printout) → add a text sketch beside it.

## Sizing

Once you understand the work and an approach is chosen, state its size in plain words. They may override it.

| Size | Design doc |
|---|---|
| A small change | A short doc: what you covered, written down. Each full-design point gets one or two lines. It goes straight to them, with no builder check. |
| A project | A full written design, followed by the [builder check](#builder-check). |

- The work grows partway through: stop, tell them, and move up a size.
- Several independent projects inside one request → point that out, settle the sequence with them, then take each through brainstorming separately.

## Design doc contents

Every design doc, short or full, has an **Approaches** part. It lists the two or three options considered, their trade-offs, the one picked and why. They choose in conversation; the doc only records that choice afterwards.

The bar for a full design: a skilled practitioner of the domain plans the build from it alone, with no trip back to the person. Keep it plain prose. It contains:

| Part | Holds |
|---|---|
| Intent | What they want, and why |
| Scope | Goals, non-goals, anti-goals |
| Constraints | Limits the build must respect |
| Approaches | The options weighed, as described above |
| Their decisions | Each part of the how they settled, written the way they settled it |
| Builder's latitude | What remains for the builder to decide |

Save it to `<runtime>/specs/YYYY-MM-DD-<slug>.md`, with `<runtime>` per [config.md](../using-tl-relay/config.md). The "Skill output targets" section of `CLAUDE.md` overrides it. A location they prefer overrides that path.

## Builder check

This check runs for the project size only.

1. Warn them when you announce the write-up: a reviewer reads it before they do. That review may produce one short round of questions from you.
2. Hand [builder-check-prompt.md](builder-check-prompt.md) to a fresh subagent. With no subagent tool, read the document yourself as that builder.
3. Keep the document back until the check returns.
4. Sort each returned question into a pile:

   | Pile | What you do |
   |---|---|
   | Answered already: something said earlier, or the project, settles it | Copy that answer into the doc. |
   | Minor: settling it either way leaves the build as it is | Decide it yourself. The document marks that decision as yours. |
   | Theirs: the build depends on the answer, and only the person can give it | Hold it for step 5. |

5. Ask the person every "theirs" question together, ranked with the weightiest at the top. Fold their replies into the document. Then deliver it, with your own decisions listed briefly so they can check each one while reading.

The check gives exactly one round of questions.

<HARD-GATE>
In this skill, building covers product code, scaffolding, dependency installs, project creation, and invoking any implementation skill. Reading and exploring do not count.

None of that starts before the person approves the design doc. A small change needs its short doc approved. A project needs its full doc approved.

Approval leads to exactly one place: invoke `write-plan`. No other skill comes next.

Exceptions:
- Opt-out. When they decline the questions, this skill ends, and the gate ends with it.
- Spike. An agreed spike may be built, marked throwaway throughout. Wanting to keep its output is a fresh request, and that request must pass this gate.
</HARD-GATE>

## Red flags

| If you think | Do instead |
|---|---|
| "I'll give them a menu of things they might want." | Ask them to describe it. A menu steers the answer, and you learn which of your guesses they tolerate, not what they want. |
| "I'll just pick reasonable defaults for the gaps." | Fill them, and announce each one. They can only reject a default they know about. |
| "My questions are answered; time for the doc." | Approaches come before the doc: in a separate message, or inside the first message's short design when nothing was open. Otherwise the doc records a choice nobody made. |
| "I should explain how this process works first." | Ask the question. The process shows itself, and an explanation costs them a read before anything moves. |
| "They said 'sounds good', so it's approved." | Their nod covers only what you showed them. A doc they have not seen written down carries no approval. |
| "This spike runs fine; I'll extend it into the real thing." | Treat keeping it as a new request and take it back through the gate. Skipping that ships throwaway code. |
