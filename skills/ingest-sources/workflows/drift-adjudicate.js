export const meta = {
  name: 'drift-adjudicate',
  description: 'Adjudicate a new story register revision against its baseline, one Opus reader per slice',
  whenToUse: 'ingest-sources, after pair.py and slices.py have run for a revision of a stories source',
  phases: [{ title: 'Adjudicate', detail: 'each reader writes a slice table and a findings file' }],
}

const COUNTS = {
  type: 'object',
  properties: {
    slice: { type: 'string' },
    rows_checked: { type: 'integer' },
    pairs_confirmed: { type: 'integer' },
    pairs_repaired: { type: 'integer' },
    pairs_broken: { type: 'integer' },
    withdrawn: { type: 'integer' },
    questions: { type: 'integer' },
    files_written: { type: 'array', items: { type: 'string' } },
  },
  required: ['slice', 'rows_checked', 'pairs_confirmed', 'pairs_repaired', 'pairs_broken', 'withdrawn', 'questions', 'files_written'],
}

function prompt(a, s) {
  return [
    `You are reader ${s.name}. You adjudicate one slice of a new story register revision against its baseline.`,
    `Read ${a.ws}/old.jsonl (the baseline criteria), ${a.ws}/new.jsonl (the new revision), and ${a.ws}/pairs.tsv (a heuristic pairing that is often wrong).`,
    `The converted sources are ${a.oldSource} and ${a.newSource}.`,
    `Your new criteria are ${s.new_ids.join(', ')}.`,
    `Baseline criteria with no pair that you must rule on: ${s.rule_on.length ? s.rule_on.join(', ') : 'none'}.`,
    '',
    'Step 1. For each of your new criteria, read its paired baseline criterion. Confirm the pair, repair it to a different baseline criterion, or break it. A pair survives only when both rows describe the same behaviour of the same actor on the same screen. Wording may differ freely.',
    'Report changed rather than reworded whenever the meaning of the rule moves: a new value, a new actor, a permission that widens or narrows, a guard that appears or disappears.',
    'A repair may not claim a baseline criterion that pairs.tsv pairs with a new criterion outside your slice. Raise that as a question instead.',
    'Step 2. For each baseline criterion you must rule on, search the whole new revision for a row with the same behaviour under different wording. There are two outcomes. It is withdrawn when no row carries it. Otherwise name the new row that does; if that row is outside your slice, raise a question instead of writing the pair.',
    'A criterion you cannot decide is raised as a question and left out of the slice table.',
    `Step 3. Write ${a.ws}/slice-${s.name}.md holding one markdown table and nothing else. The header is | New criterion | Old criterion | Continuity | and the delimiter is | --- | --- | --- |. Continuity is one of identical, reworded, changed, new, withdrawn. Wrap each id in backticks and write — where a verdict leaves a side empty.`,
    `Step 4. Write ${a.ws}/findings-${s.name}.md with these sections in this order and nothing else: Material changes; Withdrawn criteria and what is designed against them; Contradictions inside the new revision; Stale references in the new text to baseline identifiers; Questions you could not settle. One line per item. Cite every claim by criterion id. Make no recommendations.`,
    `Step 5. Read both files back. Return only after ${a.ws}/slice-${s.name}.md and ${a.ws}/findings-${s.name}.md both exist, and list their absolute paths in files_written.`,
    'Edit no other file and run no git command. Return the counts.',
  ].join('\n')
}

const a = args
phase('Adjudicate')
const results = await parallel(a.slices.map(s => () =>
  agent(prompt(a, s), { label: `reader ${s.name}`, phase: 'Adjudicate', schema: COUNTS, model: 'opus' })))
const returned = results.filter(Boolean)
log(`${returned.length} of ${a.slices.length} readers returned`)
const incomplete = returned.filter(r => !r.files_written.some(f => f.endsWith(`findings-${r.slice}.md`))).map(r => r.slice)
if (incomplete.length) log(`no findings file from: ${incomplete.join(', ')}`)
return { returned, missing: a.slices.map(s => s.name).filter(n => !returned.some(r => r.slice === n)), incomplete }
