import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Plugin } from 'vite'

/**
 * The Terms, Privacy and Refund pages, rendered from docs/legal at BUILD.
 *
 * ONE COPY OF THE TEXT. The words a person accepts are the files in
 * docs/legal, named by config/legal.json, and this writes them into
 * /terms, /privacy and /refunds while vite builds. Nothing is fetched at run
 * time, so the pages read with JavaScript off, as plans-table.ts does for the
 * pricing page.
 *
 * UNLINKED AND NOINDEX (decided 27 October 2026). The pages are public, as
 * Paddle's verification needs, but no footer or menu on the site links to
 * them; sign-up, the invitation page, recipient registration and the app do.
 * Each page carries its own <meta name="robots" content="noindex">.
 *
 * A SMALL MARKDOWN, NOT A LIBRARY. The documents use headings, paragraphs,
 * one- and two-level bullet lists, pipe tables, bold, code and links, and
 * nothing else. Anything this does not recognise is printed as a paragraph,
 * escaped - never dropped, so a construct added to a document later shows up
 * looking wrong rather than silently missing.
 *
 * EVERY FAILURE IS FATAL. A missing file, or a document whose version line
 * does not match config/legal.json, stops the build: a published page that
 * says version 1 while acceptances record version 2 is the one thing these
 * pages must never do.
 */

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(HERE, '..')
export const LEGAL_FILE = resolve(ROOT, 'config', 'legal.json')

/** Where a page's document goes: `<!-- @legal:terms -->`. */
const MARKER = /<!-- @legal:(\w+) -->/

type Legal = {
  agreement_version: number
  effective: string
  documents: Record<string, { path: string; title: string }>
}

class LegalError extends Error {
  constructor(said: string) {
    super(`legal pages: ${said}`)
    this.name = 'LegalError'
  }
}

export function readLegal(file = LEGAL_FILE): Legal {
  let raw: string
  try {
    raw = readFileSync(file, 'utf8')
  } catch {
    throw new LegalError(`cannot read ${file}`)
  }
  const legal = JSON.parse(raw) as Legal
  if (!Number.isInteger(legal.agreement_version) || legal.agreement_version < 1) {
    throw new LegalError('agreement_version must be a whole number from 1')
  }
  if (!legal.documents || typeof legal.documents !== 'object') {
    throw new LegalError('documents is missing')
  }
  return legal
}

const escape = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

/** Bold, code, links and bare email addresses, after escaping. */
function inline(text: string): string {
  return escape(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>')
    .replace(/(^|[\s(])([\w.+-]+@[\w-]+\.[\w.-]*\w)/g,
             '$1<a href="mailto:$2">$2</a>')
}

function cells(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|')
    .map((c) => c.trim())
}

/** The document as HTML. The first heading and the version line under it are
 *  returned apart, for the page's own head. */
export function renderMarkdown(md: string): { title: string; version: string; body: string } {
  const lines = md.replace(/\r\n/g, '\n').split('\n')
  let title = ''
  let version = ''
  const out: string[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) { i++; continue }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line)
    if (heading) {
      const level = heading[1].length
      if (level === 1 && !title) {
        title = heading[2].trim()
        // The version line sits directly under the title.
        let j = i + 1
        while (j < lines.length && !lines[j].trim()) j++
        if (j < lines.length && /^Version \d+/.test(lines[j].trim())) {
          version = lines[j].trim()
          i = j + 1
          continue
        }
      } else {
        out.push(`<h${level}>${inline(heading[2].trim())}</h${level}>`)
      }
      i++
      continue
    }

    if (line.trim().startsWith('|')) {
      const rows: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[i++])
      const [head, , ...body] = rows
      out.push('<div class="legal-table"><table>')
      out.push('<thead><tr>' + cells(head).map((c) => `<th scope="col">${inline(c)}</th>`).join('') + '</tr></thead>')
      out.push('<tbody>' + body.map((r) =>
        '<tr>' + cells(r).map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') + '</tbody>')
      out.push('</table></div>')
      continue
    }

    if (/^-\s/.test(line)) {
      // One level, with a second level indented four spaces under an item.
      const items: string[] = []
      while (i < lines.length && /^( {4})?-\s/.test(lines[i])) {
        const top = lines[i].replace(/^-\s+/, '')
        i++
        const sub: string[] = []
        while (i < lines.length && /^ {4}-\s/.test(lines[i])) {
          sub.push(`<li>${inline(lines[i].replace(/^ {4}-\s+/, ''))}</li>`)
          i++
        }
        items.push(`<li>${inline(top)}${sub.length ? `<ul>${sub.join('')}</ul>` : ''}</li>`)
      }
      out.push(`<ul>${items.join('')}</ul>`)
      continue
    }

    // A paragraph runs to the next blank line.
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !/^(#{1,3}\s|\||-\s)/.test(lines[i])) {
      para.push(lines[i++].trim())
    }
    out.push(`<p>${inline(para.join(' '))}</p>`)
  }

  return { title, version, body: out.join('\n') }
}

/** The three documents, each pointing at the other two. The only links to
 *  them on the site are these, on their own pages. */
function siblings(legal: Legal, current: string): string {
  const links = Object.entries(legal.documents).map(([key, doc]) =>
    key === current
      ? `<span aria-current="page">${escape(doc.title)}</span>`
      : `<a href="/${key}">${escape(doc.title)}</a>`)
  return `<nav class="legal-nav">${links.join(' · ')}</nav>`
}

export function renderDocument(key: string, legal = readLegal()): string {
  const doc = legal.documents[key]
  if (!doc) throw new LegalError(`no document "${key}" in config/legal.json`)
  let md: string
  try {
    md = readFileSync(resolve(ROOT, doc.path), 'utf8')
  } catch {
    throw new LegalError(`cannot read ${doc.path}`)
  }
  const { title, version, body } = renderMarkdown(md)
  const expected = `Version ${legal.agreement_version}`
  if (!version.startsWith(expected + ' ')) {
    throw new LegalError(
      `${doc.path} says "${version || 'no version line'}"; config/legal.json says ${expected}`)
  }
  return [
    '<section class="hero"><div class="wrap">',
    `  <h1>${escape(title)}</h1>`,
    `  <p class="lede legal-version">${escape(version)}</p>`,
    `  ${siblings(legal, key)}`,
    '</div></section>',
    '<section class="hair"><div class="wrap"><article class="legal">',
    body,
    '</article></div></section>',
  ].join('\n')
}

export function legalPages(): Plugin {
  return {
    name: 'arqedia-legal-pages',
    transformIndexHtml: {
      order: 'pre',
      handler(html: string) {
        const found = MARKER.exec(html)
        if (!found) return html
        return html.replace(MARKER, renderDocument(found[1]))
      },
    },
  }
}
