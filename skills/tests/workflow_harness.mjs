import { readFileSync } from 'node:fs'

const [script, argsJson] = process.argv.slice(2)
const source = readFileSync(script, 'utf8').replace(/^export const meta/m, 'const meta')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const run = new AsyncFunction('args', 'agent', 'parallel', 'phase', 'log', source)

const agent = async (prompt, opts) => {
  console.log(JSON.stringify({ prompt, opts }))
  return { findings: [] }
}
const parallel = thunks => Promise.all(thunks.map(t => t()))

await run(JSON.parse(argsJson), agent, parallel, () => {}, () => {})
