---
name: unslop
description: Use when writing or editing prose for humans (docs, specs, PR descriptions, comments, messages, reports) and it reads as AI-generated. Symptoms include em dashes everywhere, inflated vocabulary, bolded proper nouns, rule-of-three lists, negative parallelism, and sycophantic openers.
---

# Unslop

AI prose has a fingerprint: inflated words, mechanical structure, hedging and forced symmetry. Removing those patterns is half the job. The result must sound like a person with an opinion wrote it.

The work has three steps: scan, rewrite with the meaning kept, then add voice.

## When to use

- You edit your own draft, or AI-generated text, before a human reads it.
- A doc, spec, PR or message "feels AI", and nobody can say why.
- Not for code, machine-read output such as JSON or logs, or text a person already wrote in their own voice. Leave code blocks and inline code byte for byte.

## Scan

Read [patterns.md](patterns.md) whole. It lists the words, structures and formatting habits to remove. Check every heading and every bullet, not only the paragraphs. A sentence-case heading capitalizes its first word and proper names only, so `Retry Policy Details` becomes `Retry policy details`.

## Rewrite

Replace each hit with the plain statement. Keep every fact, name and number. Add no claim the source lacks.

Delete a contrast with something nobody claimed. "It is more than a linter" still carries the "not just X" tell. Say what the thing does.

## Add voice

Removing the patterns gives sterile text, not human text. Then:

- **Have an opinion.** React to the fact instead of listing it neutrally.
- **Vary rhythm.** A short sentence. Then a longer one, because the thought needs the room.
- **Be concrete.** `agents churning away at 3am` beats `this is a concern`. Give numbers, names and mechanisms.
- **Show the working.** Say what a thing does, not how it feels.
- **Use "I"** when you mean it.
- **Let some mess in.** Perfect balance is itself a tell.
- **One idea per sentence** when a sentence gets dense.

A design document or other reference page skips this step. `technical-writing` sets its register.

## The test

Read the text aloud. A press release or a chatbot voice fails. A sharp colleague explaining the thing over coffee passes.

## Common mistakes

- **Over-correcting into terse robot.** Keep the adjectives that carry meaning.
- **Replacing words blindly.** `leverage` in a finance doc is correct, and so is `robust` for a real robustness property. Judge in context.
- **Sanding a real person's quirks.** If a person wrote it in their own voice, leave that voice alone.
