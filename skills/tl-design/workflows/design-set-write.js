export const meta = {
  name: 'design-set-write',
  description: 'Write, review and fix module contracts and LLDs for a design set, one Opus agent per module',
  whenToUse: 'Called only by tl-design through scriptPath, with a phase of write, review, fix or rereview',
  phases: [{ title: 'Write' }, { title: 'Review' }, { title: 'Fix' }, { title: 'Rereview' }],
}

const CATEGORIES = ['LOST', 'MISCITED', 'CONTRADICTS', 'CROSS-MODULE', 'SKILL', 'LENGTH']
const FINDING = {
  type: 'object',
  properties: {
    id: { type: 'string' },
    category: { type: 'string', enum: CATEGORIES },
    module: { type: 'string' },
    file: { type: 'string' },
    summary: { type: 'string' },
  },
  required: ['id', 'category', 'module', 'file', 'summary'],
}
const WRITTEN = {
  type: 'object',
  properties: {
    module: { type: 'string' },
    check_contract_exit: { type: 'integer' },
    doc_budget_exit: { type: 'integer' },
    addressed: { type: 'array', items: { type: 'string' } },
    files_written: { type: 'array', items: { type: 'string' } },
    questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['module', 'check_contract_exit', 'doc_budget_exit', 'addressed', 'files_written'],
}
const REVIEWED = {
  type: 'object',
  properties: { findings: { type: 'array', items: FINDING } },
  required: ['findings'],
}
const REREVIEWED = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          verdict: { type: 'string', enum: ['ADDRESSED', 'NOT ADDRESSED'] },
          note: { type: 'string' },
        },
        required: ['id', 'verdict', 'note'],
      },
    },
    new_findings: { type: 'array', items: FINDING },
  },
  required: ['verdicts', 'new_findings'],
}

const a = args
const h = a.handle
const root = `${a.knowledge}/designs/${h}`
const files = m => ({
  contract: `${root}/contracts/${m}.openapi.yaml`,
  lld: `${root}/lld/${m}.md`,
  api: `${root}/lld/${m}-api.md`,
  routes: `${root}/lld/${m}/api/4-*.md`,
  overview: `${root}/overview.md`,
})
const check = m => {
  const f = files(m)
  return `python3 ${a.skills}/write-contract/scripts/check_contract.py --contract ${f.contract} --lld ${f.api} --api ${f.api} --module ${m} --common ${f.api}`
}
// render_lld.py creates the route-page directory on every run, and every budget run follows a render.
const budget = m => {
  const f = files(m)
  const base = a.baseline ? ` --baseline ${a.baseline}` : ''
  return `python3 ${a.skills}/tl-design/scripts/doc_budget.py ${f.lld} ${f.api} ${f.lld.replace(/\.md$/, '')}${base}`
}
const meetBudget = `Meet the budget by moving a fact to the page the skill names for it, merging, or linking. Never delete a design fact. An implementation-plan item taken off a page moves to ${root}/implementation-notes.md, and is never deleted. An invariant or race outcome is a design fact and never moves to implementation-notes.md. When a page cannot meet its budget without dropping one, return a question naming the page and the fact.`
const shared = [
  `${root}/overview.md`,
  `${root}/contracts/common.openapi.yaml`,
  `${root}/schema-changes.md`,
  `${root}/dependencies.md`,
  `${root}/use-cases/index.md`,
  `${root}/specs/`,
].join(', ')
const rules = [
  `Read the ledger at ${a.ledger} before anything else and follow every ruling in it.`,
  'Run no git command.',
  'Write no open point into any page. Return each question the sources cannot answer in the questions field. The controller adds it to the set\'s open points pages in root, as the tl-design skill says. An Open entry goes to both open-points.md and the local open-points-full.md, and a Proposed or Accepted entry to the full list only. Both files are local: link neither one from any page.',
]

function writePrompt(m) {
  const f = files(m)
  return [
    `You write the ${m} module's contract and LLD for the ${h} design set.`,
    ...rules,
    'Invoke the write-contract skill, then the write-design skill, and follow both.',
    `Read ${f.overview}, the use case pages under ${root}/use-cases, ${f.api}, and these shared pages: ${shared}.`,
    `Write ${f.contract}. Run render_lld.py with --contract ${f.contract} --lld ${f.api} --module ${m} --common ${f.api}. It writes the route pages at ${f.routes}. Then write the section 4 route table, the \`**Rules:**\` list on each route page and the other LLD sections.`,
    'Section 1 holds the scope, the Out of scope list and the scenarios. In a set with several modules, the Scenarios block sits on a child page, as write-design sets. A module with routes keeps section 4 on its API page, as write-design sets. An LLD has no traceability page and no code changes page; the code changes belong to the implementation plan. A route page is titled `API 4.N: <METHOD path> - <summary>`, and any other section 4 element page `<Kind> 4.N: <name> - <summary>`, such as `Workflow 4.1: pickupBookingThWorkflow - Run one booking attempt`. Neither title carries the module name. Each element names its reason in the slot write-design sets: a UC-n, NFR-n or HLA 4.N, a module rule, or a criterion id of the register. A dependency is one sentence that links dependencies.md and names the DEP-n id. Section 5 holds no pseudo-code; the implementation plan does.',
    'Return each table, column, index, check constraint, route, interface, metric and event that names no reason as a question. Delete it only when the LLD has never passed G-design.',
    `Run ${check(m)} and fix what it reports until it exits 0.`,
    `Run ${budget(m)} after the last edit. ${meetBudget}`,
    `Edit only ${f.contract} and ${f.lld}, the pages in the directory beside it named after it, ${f.api}, and ${root}/implementation-notes.md.`,
    'Return the last check_contract and doc_budget exit codes, an empty addressed list, and the absolute paths you wrote. Include the implementation-notes.md path in the paths when you moved an item.',
  ].join('\n')
}

function reviewPrompt() {
  const sets = a.modules.map(m => Object.values(files(m)).join(', ')).join('\n')
  return [
    `You review the whole ${h} contract and LLD set. You edit no file.`,
    ...rules,
    'Invoke the write-contract and write-design skills and read them, so you know the rules the writers followed.',
    `The shared pages are ${shared}.`,
    `The module files are:\n${sets}`,
    `Run these once per module, and file each page they report as one LENGTH finding:\n${a.modules.map(budget).join('\n')}`,
    'Review the Scenarios, API and Execution logic child pages of an LLD as part of that LLD. Moving those blocks onto child pages breaks no write-design rule. A traceability page or a code changes page under an LLD is a finding. So is a section 4 child page whose title carries the module name or misses the `API 4.N:` or `<Kind> 4.N:` format.',
    'File each finding once, under one category.',
    'LOST: a fact the Overview or its child pages state that the LLD or contract dropped.',
    'MISCITED: a criterion, decision or page cited for something it does not say.',
    'CONTRADICTS: two statements in the set that cannot both hold.',
    'CROSS-MODULE: a shape or rule one module states that another module states differently.',
    'SKILL: a rule of write-contract or write-design that a page breaks. This includes an element that names no reason and a reason whose id exists in no source.',
    'LENGTH: a page that doc_budget.py reports, one finding per page, listing its rules and sections.',
    `Set module to the directory name exactly as listed here: ${a.modules.join(', ')}.`,
    'Give each finding an id of the form <module>-<n>, the file, and one sentence.',
  ].join('\n')
}

function fixPrompt(m, list) {
  const f = files(m)
  return [
    `You fix the ${m} module's contract and LLD for the ${h} design set.`,
    ...rules,
    'Invoke the write-contract skill, then the write-design skill, and follow both.',
    `Fix these findings:\n${list.map(x => `${x.id} [${x.category}] ${x.file}: ${x.summary}`).join('\n')}`,
    `Run ${check(m)} after the last edit and fix what it reports until it exits 0.`,
    `Run ${budget(m)} after the last edit. ${meetBudget}`,
    `Edit only ${f.contract} and ${f.lld}, the pages in the directory beside it named after it, ${f.api}, and ${root}/implementation-notes.md.`,
    'Return the check_contract and doc_budget exit codes, the ids you addressed, and the absolute paths you wrote. Include the implementation-notes.md path in the paths when you moved an item.',
  ].join('\n')
}

function rereviewPrompt() {
  return [
    `You re-review a fix round on the ${h} contract and LLD set. You edit no file.`,
    ...rules,
    `Read the fix diff with: diff -ru ${a.scratch} ${root}. ${a.scratch} holds the copy of the set made before the fix. This read-only diff is the one command you may run beyond the checks below.`,
    `Give a verdict on each finding:\n${a.findings.map(x => `${x.id} [${x.category}] ${x.file}: ${x.summary}`).join('\n')}`,
    'Report new findings only for breakage the fix diff itself introduced.',
    `Run these once per module, and file each page they report with a violation no finding above names as one new LENGTH finding:\n${a.modules.map(budget).join('\n')}`,
  ].join('\n')
}

const need = a.phase === 'rereview' ? ['knowledge', 'handle', 'scratch'] : ['knowledge', 'handle']
const absent = need.filter(k => !a[k])
if (absent.length) throw new Error(`missing args: ${absent.join(', ')}`)
if (a.phase === 'write' || a.phase === 'fix') {
  const title = a.phase === 'write' ? 'Write' : 'Fix'
  phase(title)
  const unknown = a.phase === 'fix' ? a.findings.filter(x => !a.modules.includes(x.module)) : []
  if (unknown.length) throw new Error(`findings name modules not in args.modules: ${unknown.map(x => x.id).join(', ')}`)
  const todo = a.phase === 'write' ? a.modules : a.modules.filter(m => a.findings.some(x => x.module === m))
  const out = await parallel(todo.map(m => () => agent(
    a.phase === 'write' ? writePrompt(m) : fixPrompt(m, a.findings.filter(x => x.module === m)),
    { label: `${a.phase} ${m}`, phase: title, schema: WRITTEN, model: 'opus' })))
  const got = out.filter(Boolean)
  const missing = todo.filter(m => !got.some(r => r.module === m))
  const failing = got.filter(r => r.check_contract_exit !== 0 || r.doc_budget_exit !== 0).map(r => r.module)
  log(`${got.length} of ${todo.length} returned; failing: ${failing.join(', ') || 'none'}`)
  return { phase: a.phase, returned: got, missing, failing }
}
if (a.phase === 'review') {
  phase('Review')
  const r = await agent(reviewPrompt(), { label: 'review set', phase: 'Review', schema: REVIEWED, model: 'opus' })
  return { phase: 'review', findings: r ? r.findings : null }
}
if (a.phase === 'rereview') {
  phase('Rereview')
  const r = await agent(rereviewPrompt(), { label: 'rereview set', phase: 'Rereview', schema: REREVIEWED, model: 'opus' })
  return { phase: 'rereview', result: r }
}
throw new Error(`unknown phase ${a.phase}`)
