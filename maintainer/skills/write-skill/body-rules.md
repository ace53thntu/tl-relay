# Body rules

## Contents

- Frontmatter
- Body
- Discipline skills
- Voice

## Frontmatter

- `name` holds letters, digits and hyphens. A new name prefers the verb-noun pattern, such as `write-plan`.
- `description` is third person and stays under 500 characters.
- The description states trigger conditions and symptoms. It never summarises the procedure.
- Name the underlying problem, not a library symptom, unless the skill is tool-specific.
- Seed the description and the body with words an agent searches for: error text, symptoms, synonyms, command names.

## Body

- Keep a skill body below 500 words, and far below for a skill that loads every session.
- Draft only what the observed failures need. Add nothing for imagined cases.
- Move bulky reference material or a reusable script into a companion file. Link it straight from SKILL.md. Never chain references two levels deep.
- Give a companion file over 100 lines a contents list at its top.
- Point at another skill by name with an explicit required marker. Never force-load it by an `@` path.
- Call a shipped script as an argument to its interpreter. Packaging can strip the exec bit from a bare path.
- Give one complete, runnable example from a real case. Never port it to several languages.
- Draw a flowchart only for a non-obvious decision or a loop an agent may quit early. Label nodes with meaning. Put no code in a node.
- Use one term per concept. Never rotate synonyms.
- Never write the skill as the story of one past session.
- Leave out instructions that expire on a date. Move a superseded method to a collapsed legacy note.
- Assume the reader is capable. Cut every sentence that does not earn its tokens.

## Discipline skills

These rules apply to the skill being written. In a discipline skill:

- State early that breaking the wording breaks the intent.
- Keep an excuse-and-rebuttal table built from the logged excuses.
- Keep a list of warning signs for self-checks.

## Voice

Write every sentence, heading and the description in words of your own. Copy no source. Follow `technical-writing` (required): sentences of at most 20 words, active voice, a named actor.
