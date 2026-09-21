import './styles/site.css'
// One source, two surfaces - the same footing tokens.css uses. The engine
// lives in the application and the site reads it from there; a copy is how
// the hero and the configuration screen's stages would drift apart.
import { mountFlock } from '../../ui/src/flock'

/* The hero animation, the worked sample, and the starter-pack chooser.
   Nothing else on the page moves. */

// --- the hero --------------------------------------------------------------

const canvas = document.querySelector<HTMLCanvasElement>('canvas[data-flock]')
if (canvas) mountFlock(canvas)

// --- the worked sample -----------------------------------------------------
//
// A sentence in the memorandum, the facts that produced it, and the document
// each fact was read from. Three sentences, each with its own set of facts and
// its own sources — which is the whole point, and why one panel would not do.

interface Fact {
  label: string
  value: string
  source: string
  page: string
  before: ('s' | 'm' | 'l')[]
  passage: string
  after: ('s' | 'm' | 'l')[]
}

interface Claim {
  text: string
  section: string
  facts: Fact[]
}

const CLAIMS: Claim[] = [
  {
    text: 'The borrower reports senior facilities of USD 24.6m drawn against a committed line of USD 30.0m.',
    section: 'Senior facilities',
    facts: [
      {
        label: 'Total Debt', value: 'USD 24,600,000',
        source: 'Audited-Accounts-FY2025.pdf', page: 'p. 14',
        before: ['l', 'm'],
        passage: 'Senior facilities drawn at year end: USD 24,600,000.',
        after: ['l', 's', 'm'],
      },
      {
        label: 'Facility Limit', value: 'USD 30,000,000',
        source: 'Facility-Agreement-2024.pdf', page: 'p. 3, cl. 2.1',
        before: ['m', 'l'],
        passage: 'The Lenders make available a committed revolving facility in an aggregate amount of USD 30,000,000.',
        after: ['s', 'l'],
      },
      {
        label: 'Undrawn Headroom', value: 'USD 5,400,000',
        source: 'Audited-Accounts-FY2025.pdf', page: 'p. 14',
        before: ['l'],
        passage: 'Undrawn and available at year end: USD 5,400,000.',
        after: ['m', 's', 'l'],
      },
    ],
  },
  {
    text: 'Net leverage stands at 2.8× on trailing twelve-month EBITDA of USD 8.8m.',
    section: 'Leverage',
    facts: [
      {
        label: 'EBITDA (trailing twelve months)', value: 'USD 8,800,000',
        source: 'Management-Accounts-Q1.xlsx', page: 'Summary, B12:B24',
        before: ['m'],
        passage: 'EBITDA, trailing twelve months to 31 December 2025: USD 8,800,000.',
        after: ['l', 's'],
      },
      {
        label: 'Net Debt', value: 'USD 24,600,000',
        source: 'Audited-Accounts-FY2025.pdf', page: 'p. 31',
        before: ['l', 'l'],
        passage: 'Net debt, being total borrowings less cash and cash equivalents: USD 24,600,000.',
        after: ['s'],
      },
      {
        label: 'Net Leverage', value: '2.8×',
        source: 'Audited-Accounts-FY2025.pdf', page: 'p. 31',
        before: ['m', 's'],
        passage: 'Net debt to EBITDA at the reporting date: 2.8 times.',
        after: ['l', 'm'],
      },
    ],
  },
  {
    text: 'No financial maintenance covenant ratio is stated in the facility agreement provided.',
    section: 'Covenants',
    facts: [
      {
        label: 'Covenant Ratio', value: 'Not disclosed',
        source: 'Facility-Agreement-2024.pdf', page: 'p. 41, cl. 18',
        before: ['l', 'm'],
        passage: 'The Borrower shall comply with the financial covenants set out in Schedule 4, which was not provided.',
        after: ['s', 'l'],
      },
      {
        label: 'Lender Name', value: 'Northbank Commercial plc',
        source: 'Facility-Agreement-2024.pdf', page: 'p. 1',
        before: ['m'],
        passage: 'NORTHBANK COMMERCIAL PLC, as Agent and Original Lender.',
        after: ['l', 'l', 's'],
      },
      {
        label: 'Agreement Date', value: '17 June 2024',
        source: 'Facility-Agreement-2024.pdf', page: 'cover',
        before: ['s'],
        passage: 'Dated 17 June 2024.',
        after: ['m', 'l'],
      },
    ],
  },
]

const claimsEl = document.getElementById('claims')
const factsEl = document.getElementById('facts')
const headEl = document.getElementById('fact-head')
const countEl = document.getElementById('fact-count')

function rows(kinds: ('s' | 'm' | 'l')[]): string {
  return kinds.map((k) => `<span class="row ${k}"></span>`).join('')
}

function openDoc(fact: Fact): void {
  const modal = document.getElementById('doc-modal')
  const sub = document.getElementById('doc-sub')
  const body = document.getElementById('doc-body')
  if (!modal || !sub || !body) return
  // The head is a standing title. Which document this is belongs beneath it.
  sub.textContent = `${fact.source} · ${fact.page} · read once, under revision 36 · never re-read`
  body.innerHTML = rows(fact.before) + `<mark>${fact.passage}</mark>` + rows(fact.after)
  modal.hidden = false
}

function closeDoc(): void {
  const modal = document.getElementById('doc-modal')
  if (modal) modal.hidden = true
}

function showFacts(i: number): void {
  const claim = CLAIMS[i]
  if (!factsEl || !headEl || !countEl) return

  headEl.textContent = `${claim.section} — facts behind this sentence`
  const sources = new Set(claim.facts.map((f) => f.source))
  countEl.textContent = `${claim.facts.length} facts · ${sources.size} document${sources.size > 1 ? 's' : ''}`

  factsEl.innerHTML = ''
  claim.facts.forEach((fact) => {
    const b = document.createElement('button')
    b.className = 'fact'
    b.innerHTML =
      `<span class="grow"><span class="lab">${fact.label}</span>` +
      `<span class="val">${fact.value}</span></span>` +
      `<span class="src">${fact.source}<i>${fact.page}</i></span>`
    b.addEventListener('click', () => openDoc(fact))
    factsEl.appendChild(b)
  })

  document.querySelectorAll('.claim').forEach((c, n) => c.classList.toggle('lit', n === i))
}

if (claimsEl && factsEl) {
  CLAIMS.forEach((claim, i) => {
    const p = document.createElement('p')
    p.className = 'claim'
    p.tabIndex = 0
    p.innerHTML = `${claim.text}<sup>${i + 1}</sup>`
    p.addEventListener('click', () => showFacts(i))
    p.addEventListener('focus', () => showFacts(i))
    claimsEl.appendChild(p)
  })
  showFacts(0)

  document.getElementById('doc-close')?.addEventListener('click', closeDoc)
  document.getElementById('doc-modal')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeDoc()
  })
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDoc()
  })
}

// --- starter packs ---------------------------------------------------------

const PACKS: { name: string; note: string }[] = [
  { name: 'KYC and AML', note: 'Corporate identity, ownership and control, individuals, regulatory and screening, and the associated entities a counterparty banks, audits and insures with.' },
  { name: 'Trade Credit', note: 'Borrower overview, financial performance, working capital, existing indebtedness, security, trade flows and concentration.' },
  { name: 'Asset Based Loan Memo', note: 'Collateral schedules, valuation basis, advance rates, eligibility and ineligibility tests, and the borrowing base as reported.' },
  { name: 'Real Estate Loan Memo', note: 'Property and title, tenancy and income, valuation and basis, debt service, and the sponsor behind the transaction.' },
  { name: 'Lender Marketing Memo', note: 'The transaction as presented to a lender: the opportunity, the structure, the security, and what the borrower is asking for.' },
  { name: 'Anonymous Project “X” Memo', note: 'The same file with identities withheld, for circulation before a counterparty is named.' },
]

const trigger = document.getElementById('pack-trigger')
const list = document.getElementById('pack-list')
const nameEl = document.getElementById('pack-name')
const noteEl = document.getElementById('pack-note')

if (trigger && list && nameEl && noteEl) {
  let chosen = 0

  const paint = () => {
    nameEl.textContent = PACKS[chosen].name
    noteEl.textContent = PACKS[chosen].note
    list.querySelectorAll('button').forEach((b, n) =>
      b.setAttribute('aria-selected', String(n === chosen)))
  }

  PACKS.forEach((pack, i) => {
    const li = document.createElement('li')
    const b = document.createElement('button')
    b.setAttribute('role', 'option')
    b.innerHTML = `<b>${pack.name}</b><small>${pack.note}</small>`
    b.addEventListener('click', () => {
      chosen = i
      paint()
      list.hidden = true
      trigger.setAttribute('aria-expanded', 'false')
    })
    li.appendChild(b)
    list.appendChild(li)
  })
  paint()

  trigger.addEventListener('click', () => {
    const open = trigger.getAttribute('aria-expanded') === 'true'
    trigger.setAttribute('aria-expanded', String(!open))
    list.hidden = open
  })

  document.addEventListener('click', (e) => {
    const at = e.target as Node
    if (!trigger.contains(at) && !list.contains(at)) {
      list.hidden = true
      trigger.setAttribute('aria-expanded', 'false')
    }
  })

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      list.hidden = true
      trigger.setAttribute('aria-expanded', 'false')
    }
  })
}
