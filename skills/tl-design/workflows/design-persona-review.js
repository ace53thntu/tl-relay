export const meta = {
  name: 'design-persona-review',
  description: 'Fan out persona reviewers over design pages, then merge their findings with one Opus agent',
  whenToUse: 'Called only by tl-design through scriptPath at design steps 5 and 9',
  phases: [{ title: 'Review' }, { title: 'Merge' }],
}

const SEVERITY = ['blocking', 'minor']
const KEY_CLASS = ['contract', 'data_model', 'architecture', 'security_release', 'timeline', 'none']
const PERSONAS = ['sa', 'se', 'qa', 'security', 'temporal']
const ERROR_CLASS = ['missing_detail', 'voice_structure', 'length_focus', 'key_decision_unasked', 'other']
const AGENTS = {
  sa: 'solution-architect',
  se: 'software-engineer',
  qa: 'qa-engineer',
  security: 'security-engineer',
  temporal: 'temporal-reviewer',
}
const MODELS = { sa: 'opus', se: 'sonnet', qa: 'sonnet', security: 'opus', temporal: 'opus' }
const LENS = {
  sa: 'lens-solution-architect',
  se: 'lens-software-engineer',
  qa: 'lens-qa-engineer',
  security: 'lens-security-engineer',
  temporal: 'temporal-workflow-design-critic',
}
const ROLES = {
  sa: "You review the named pages as the solution architect, using the bound lens. You return findings only.\n\nNever rewrite pages.",
  se: "You review the named pages as the engineer who builds from them, using the bound lens. Each guess you make becomes a finding.\n\nNever propose architecture.",
  qa: "You review the named pages as the QA engineer, using the bound lens. You derive one test case per use case and per route. An untestable rule becomes a finding.\n\nNever edit the design.",
  security: "You review the named pages as the security engineer, using the bound lens. You return findings only.\n\nNever review code.",
  temporal: "You review the Overview, the workflow and schedule element pages, and the routes that start a run. You check each against the code with the bound critic skill. Return an object `{\"findings\": [...]}`. Each finding has the fields `persona` (always `temporal`), `page` (page path), `anchor` (heading anchor, or the empty string when you cannot name one), `severity` (`blocking` or `minor`), `key_class` (`contract`, `data_model`, `architecture`, `security_release`, `timeline` or `none`), `guess` (what you had to assume) and `question` (what the page must answer). Read the pages the prompt names and the code in the repos those pages name, nothing else. Never read `decisions.md`, `sources/` or `open-points*.md`. Follow the tagging rules: a question about what the code at the baseline already does is `key_class` `none`, and at stage `hla` a question that asks for LLD detail is `minor`. Mark a question only an outside owner can answer `minor` and name the owner in `question`.\n\nNever edit pages.",
}

const FINDING = {
  type: 'object',
  properties: {
    persona: { type: 'string', enum: PERSONAS },
    page: { type: 'string' },
    anchor: { type: 'string' },
    severity: { type: 'string', enum: SEVERITY },
    key_class: { type: 'string', enum: KEY_CLASS },
    guess: { type: 'string' },
    question: { type: 'string' },
  },
  required: ['persona', 'page', 'anchor', 'severity', 'key_class', 'guess', 'question'],
}
const REVIEWED = {
  type: 'object',
  properties: { findings: { type: 'array', items: FINDING } },
  required: ['findings'],
}
const MERGED_FINDING = {
  type: 'object',
  properties: {
    personas: { type: 'array', items: { type: 'string', enum: PERSONAS } },
    page: { type: 'string' },
    anchor: { type: 'string' },
    severity: { type: 'string', enum: SEVERITY },
    key_class: { type: 'string', enum: KEY_CLASS },
    error_class: { type: 'string', enum: ERROR_CLASS },
    guess: { type: 'string' },
    question: { type: 'string' },
  },
  required: ['personas', 'page', 'anchor', 'severity', 'key_class', 'error_class', 'guess', 'question'],
}
const MERGED = {
  type: 'object',
  properties: { findings: { type: 'array', items: MERGED_FINDING } },
  required: ['findings'],
}

const a = args !== null && typeof args === 'object' ? args : {}
const need = ['handle', 'knowledge', 'stage', 'round', 'pages', 'ledger']
const absent = need.filter(k => a[k] === undefined || a[k] === null || a[k] === '')
if (absent.length) throw new Error(`missing args: ${absent.join(', ')}`)
if (a.stage !== 'hla' && a.stage !== 'design') throw new Error(`unknown stage ${a.stage}`)
if (!Array.isArray(a.pages) || !a.pages.length) throw new Error('args.pages must be a non-empty array')
const relative = a.pages.find(p => typeof p !== 'string' || !p.startsWith('/'))
if (relative !== undefined) throw new Error(`args.pages entry is not an absolute path: ${relative}`)

const mode = a.agents === undefined || a.agents === null ? 'bare' : a.agents
if (!['plugin', 'bare', 'none'].includes(mode)) throw new Error(`unknown agents mode ${mode}`)

const out = `${a.knowledge}/designs/${a.handle}/rounds/${a.stage}-r${a.round}/findings.json`
const ids = a.temporal ? PERSONAS : PERSONAS.filter(p => p !== 'temporal')

const reviewPrompt = id => [
  ...(mode === 'none' ? [`Load the skill ${LENS[id]} and follow it.`, ROLES[id]] : []),
  `You review the ${a.handle} design set at stage ${a.stage}, round ${a.round}, as persona "${id}".`,
  id === 'temporal'
    ? `Follow your lens. Review these pages against the code. Read the pages and the code of the repos they name under the workspace that holds ${a.knowledge}, and edit no file:`
    : 'Follow your lens. Read only these pages, and edit no file:',
  a.pages.join('\n'),
  'Return an object {findings: [...]}, one entry per finding.',
  `Set persona to "${id}" on each. Set anchor to the heading anchor on the page, or the empty string when you cannot name one. A question only an outside owner can answer is minor, and the question names that owner.`,
].join('\n')

const mergePrompt = reviewed => [
  `You merge the persona findings for the ${a.handle} design set at stage ${a.stage}, round ${a.round}.`,
  `Pages reviewed:\n${a.pages.join('\n')}`,
  `Findings by persona, as JSON:\n${JSON.stringify(reviewed)}`,
  `Read the Agent decisions section of the ledger at ${a.ledger}.`,
  'Produce the merged list:',
  '1. A finding whose question names an outside owner (PO, another team) passes through as its own minor finding. Never merge it with another finding, never upgrade it, even with an empty anchor. Rules 2, 3 and 4 do not apply to it.',
  '2. For every other finding: one with an empty anchor, or an anchor that matches no heading on its page, becomes its own finding with error_class missing_detail. Never merge or drop it. A rule 2 finding with a key_class other than none is always blocking. Any other rule 2 finding is blocking unless the reviewer marked it minor.',
  '3. Other findings with equal non-empty page and anchor merge into one. Set personas to every persona that reported it, keep the higher severity, and pick the error_class that fits from missing_detail, voice_structure, length_focus or other. Rule 4 may change it afterwards. Also keep the first key_class other than none that a reviewer set.',
  '4. Apply this rule only to findings that rules 1 and 2 do not cover. Take a finding whose key_class is not none. If the Agent decisions section has no row for its page and anchor, set its error_class to key_decision_unasked. Also set its severity to blocking. Add no separate finding.',
  'Every other finding stays as reported, with personas holding its single persona and an error_class from missing_detail, voice_structure, length_focus or other. Rule 4 may change it afterwards.',
  'Only rule 4 sets key_decision_unasked.',
  `Write the merged list as a JSON array with the Write tool to ${out}, then return it as findings.`,
].join('\n')

phase('Review')
const results = await parallel(ids.map(id => () => agent(reviewPrompt(id), {
  label: `review ${id}`,
  phase: 'Review',
  schema: REVIEWED,
  ...(mode === 'none' ? { model: MODELS[id] } : { agentType: (mode === 'plugin' ? 'tl-relay:' : '') + AGENTS[id] }),
})))
const missing = ids.filter((id, i) => !results[i])
const reviewed = results.filter(Boolean).flatMap(r => r.findings)
log(`${ids.length - missing.length} of ${ids.length} personas returned; missing: ${missing.join(', ') || 'none'}`)

phase('Merge')
const merged = await agent(mergePrompt(reviewed), { label: 'merge findings', phase: 'Merge', schema: MERGED, model: 'opus' })
if (!merged) return { stage: a.stage, round: a.round, findings: null, missing: [...missing, 'merge'], out: null }
return { stage: a.stage, round: a.round, findings: merged.findings, missing, out }
