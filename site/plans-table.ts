import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Plugin } from 'vite'

/**
 * The pricing page's plan table, rendered from config/plans.json at BUILD.
 *
 * WHY IT IS A BUILD STEP AND NOT A FETCH. The page is static HTML served from
 * S3 behind CloudFront, and it has to say what a plan costs with JavaScript
 * off. So this runs in Node while vite builds, writes real <tr> elements into
 * the emitted file, and ships nothing to the browser - there is no request for
 * plans.json at run time and no code in the bundle that knows the file exists.
 *
 * WHY IT EXISTS AT ALL (18.5 / 11.3). The table was hand-written, and the
 * numbers in it were a second copy of the plan table. Stage 1 made
 * config/plans.json the one place a plan is described and filled the database
 * from it; this is the other half - what is marketed and what is offered now
 * come from the same eleven lines.
 *
 * WHAT THIS FILE HOLDS AND THE JSON DOES NOT: the row labels, the link text,
 * and the two money formats. That is presentation. "Seats" and "Monthly credit
 * toward metered use" are English, not data, and putting them in the JSON
 * would make a copy-edit a change to the thing the migration reads.
 *
 * NOT TYPE-CHECKED BY tsc -b, because site/tsconfig.json includes "src" only
 * and this sits beside vite.config.ts, which is not checked either. It runs
 * through esbuild when vite loads the config, and it is exercised on every
 * build - a mistake here fails the build rather than reaching the page.
 */

const HERE = dirname(fileURLToPath(import.meta.url))
export const PLANS_FILE = resolve(HERE, '..', 'config', 'plans.json')

/** Where the table goes. A comment, so the page is still valid HTML and still
 *  opens in a browser on its own while somebody edits the prose around it. */
const MARKER = '<!-- @plans-table -->'

/** And the trial length, wherever the prose states it. A token rather than a
 *  second marker comment, because it appears mid-sentence and inside a
 *  <meta> attribute - "{{TRIAL_DAYS}} days, full use, no card." */
const TRIAL_TOKEN = /\{\{TRIAL_DAYS\}\}/g

/** A plan's numbers are numbers; Enterprise carries the page's own words, and
 *  a null price is the one thing that must never be a number. */
type Cell = number | string | null

type Plan = {
  plan_key: string
  name: string
  seat_count: Cell
  monthly_price_cents: Cell
  monthly_credit_cents: Cell
  share_allowance: Cell
  field_sets_per_type: Cell
  sections_per_template: Cell
  daily_classification_cents: Cell
  how_it_starts: string
}

const REQUIRED = [
  'plan_key', 'name', 'seat_count', 'monthly_price_cents',
  'monthly_credit_cents', 'share_allowance', 'field_sets_per_type',
  'sections_per_template', 'daily_classification_cents', 'how_it_starts',
] as const

class PlansError extends Error {
  constructor(said: string) {
    super(`config/plans.json: ${said}`)
    this.name = 'PlansError'
  }
}

/**
 * Read it, or stop the build.
 *
 * EVERY FAILURE HERE IS FATAL, deliberately. A pricing page that renders with
 * a row missing, or with a price of "undefined", is worse than a build that
 * did not run: the first is published and read by somebody deciding whether to
 * buy, and the second is noticed in thirty seconds.
 */
export function readPlans(file = PLANS_FILE):
    { plans: Plan[]; topup: number; trialDays: number } {
  let text: string
  try {
    text = readFileSync(file, 'utf-8')
  } catch {
    throw new PlansError(`not found at ${file}. The marketing site renders `
      + 'its plan table from it and cannot be built without it.')
  }

  let doc: any
  try {
    doc = JSON.parse(text)
  } catch (err) {
    throw new PlansError(`is not valid JSON - ${(err as Error).message}`)
  }

  if (!Array.isArray(doc?.plans) || doc.plans.length === 0) {
    throw new PlansError('has no "plans" array, or it is empty.')
  }

  // The trial length. Not inside a plan: it is the same fourteen days on every
  // plan, and signup.TRIAL_DAYS - which is what actually writes
  // tenant.trial_ends_at - knows nothing about plans either.
  if (typeof doc.trial_days !== 'number' || doc.trial_days <= 0) {
    throw new PlansError('has no positive numeric trial_days.')
  }

  for (const plan of doc.plans) {
    for (const field of REQUIRED) {
      if (!(field in plan)) {
        throw new PlansError(
          `plan "${plan?.plan_key ?? '(unnamed)'}" has no ${field}.`)
      }
    }
    if (typeof plan.how_it_starts !== 'string'
        || !/^(https:\/\/|mailto:)/.test(plan.how_it_starts)) {
      throw new PlansError(
        `plan "${plan.plan_key}" has a how_it_starts that is neither an `
        + 'https link nor a mailto.')
    }
  }

  // Not inside a plan: the increment is one number the page prints once per
  // column. See topup_increment_note in the file.
  if (typeof doc.topup_increment_cents !== 'number') {
    throw new PlansError('has no numeric topup_increment_cents.')
  }

  return { plans: doc.plans as Plan[], topup: doc.topup_increment_cents,
           trialDays: doc.trial_days as number }
}

// --- the two money formats the page already uses ---------------------------
//
// They differ, and the difference is kept rather than tidied: the credit rows
// read $5.00 and the top-up row reads $5. Making them agree would be a change
// to the page nobody asked for, in a commit about where the numbers come from.

/** $5.00, $15.00 - the credit and allowance rows. */
const money2 = (cents: number) => `$${(cents / 100).toFixed(2)}`

/** $5, $25 - the top-up row and the price in the header. */
const money0 = (cents: number) => `$${cents / 100}`

/** HTML-escape. The values are ours, but a file is a file and an unescaped
 *  ampersand in a plan name would produce invalid markup on a published
 *  page. */
function escape(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** A cell that is a number in the file and a phrase for Enterprise.
 *  `whenNull` is what a null means for that row - the page says "unlimited"
 *  for an unlimited share allowance and "negotiated" for an unpriced plan. */
function cell(value: Cell, asNumber: (n: number) => string,
              whenNull: string): string {
  if (value === null) return whenNull
  if (typeof value === 'number') return asNumber(value)
  return escape(String(value))
}

const plain = (n: number) => String(n)

/**
 * The header cell. A null price renders as the page's own word for it.
 *
 * NULL IS THE RECORD, "negotiated" IS THE RENDERING. A negotiated price must
 * not be a release (CLAUDE.md, Money), so Enterprise carries no number - and
 * this is the one place that turns its absence into English.
 */
function header(plan: Plan): string {
  const price = plan.monthly_price_cents === null
    ? 'negotiated'
    : `${money0(plan.monthly_price_cents as number)} / month`
  return `      <th><span class="plan-name">${escape(plan.name)}</span>`
    + `<span class="plan-price">${price}</span></th>`
}

/** How it starts. The address comes from the file; the words come from what
 *  kind of address it is, because "Start a trial" and "Talk to us about
 *  Enterprise" are the page's language rather than the plan's data. */
function startCell(plan: Plan): string {
  const words = plan.how_it_starts.startsWith('mailto:')
    ? 'Talk to us about Enterprise'
    : 'Start a trial'
  return `<td class="num"><a href="${escape(plan.how_it_starts)}">${words}</a></td>`
}

function row(label: string, cells: string[]): string {
  return `      <tr><th scope="row">${label}</th>`
    + cells.map((c) => `<td class="num">${c}</td>`).join('') + '</tr>'
}

export function renderPlansTable(file = PLANS_FILE): string {
  const { plans, topup } = readPlans(file)

  const across = (make: (p: Plan) => string) => plans.map(make)

  const lines = [
    // NO LEADING INDENT ON THE FIRST LINE. The marker it replaces already
    // sits two spaces in, and vite substitutes in place - so indenting this
    // one as well put the table four spaces deep and moved a line that was
    // meant to be untouched. Every line after it carries its own indent,
    // because the substitution only affects where the first one starts.
    '<div class="tbl-scroll"><table>',
    '    <caption>Seats are a fixed plan attribute. Adding a seat is a plan change, not a proration.</caption>',
    '    <thead><tr><th></th>',
    ...plans.map((p, i) =>
      header(p) + (i === plans.length - 1 ? '</tr></thead>' : '')),
    '    <tbody>',
    row('Seats', across((p) => cell(p.seat_count, plain, ''))),
    row('Monthly credit toward metered use',
        across((p) => cell(p.monthly_credit_cents, money2, ''))),
    // Null is unlimited here, as migration 018 says - not zero, and not
    // missing.
    row('Shared memoranda per month',
        across((p) => cell(p.share_allowance, plain, 'unlimited'))),
    row('Field sets per document type',
        across((p) => cell(p.field_sets_per_type, plain, ''))),
    row('Sections per template',
        across((p) => cell(p.sections_per_template, plain, ''))),
    row('Daily classification allowance',
        across((p) => cell(p.daily_classification_cents, money2, ''))),
    // One number, every column. The historical note is kept because it is
    // what explains why this row looks per-plan and is not.
    row('Top-up increment', plans.map(() => money0(topup)))
      + '<!-- before 16 Sep 2026: $10 / $25 / $5 × seats -->',
    '      <!-- The addresses come from config/plans.json, which is also what the plan table is filled from (18.5). The Enterprise one is written a second time in ui/src/upgrade.tsx: a static page that fetched it from JavaScript would have nothing to say with JavaScript off, and the application is not built from this file. -->',
    '      <tr><th scope="row">How it starts</th>'
      + across(startCell).join('') + '</tr>',
    '    </tbody>',
    '  </table></div>',
  ]
  return lines.join('\n')
}

/**
 * The vite plugin. One replacement, in the page that asks for it.
 *
 * Runs on `vite build` and on `vite dev` alike, so what a person sees while
 * editing the page is what gets published.
 */
export function plansTable(): Plugin {
  return {
    name: 'arqedia-plans-table',
    transformIndexHtml: {
      order: 'pre',
      handler(html: string) {
        // THE TRIAL LENGTH IS REPLACED ON EVERY PAGE; the table only where a
        // page asks for one. index.html states the length and has no table.
        const { trialDays } = readPlans()
        const said = html.replace(TRIAL_TOKEN, String(trialDays))
        if (!said.includes(MARKER)) return said
        return said.replace(MARKER, renderPlansTable())
      },
    },
  }
}
