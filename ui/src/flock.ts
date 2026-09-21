/* flock.ts
 *
 * Documents -> facts -> filed -> retrieved, once, on load.
 *
 * ONE SOURCE, TWO SURFACES. This file lives in the application and the
 * marketing site imports it from here, the same footing tokens.css uses. The
 * hero on arqedia.com and the stage strip on the configuration screen are the
 * same four stages drawn by the same code; two copies would drift, and then
 * the site would be promising a product that no longer looks like itself.
 *
 * mountFlock() runs the full sequence once and holds on the final frame.
 *
 * THERE WAS A SECOND MODE, 'work', and it is gone (15.3). It held the swarm
 * indefinitely and landed when settle() was called, and it was written for
 * the application's working indicator - which was built as a CSS bar
 * (UX-12), so nothing ever imported it. It survived one correction already:
 * the comment claiming it drove that indicator was removed while the code it
 * described was left. Dead code with an honest comment is still dead code,
 * and it carried a branch through every function in the engine.
 *
 * drawStage() is the other way in: one stage, still, for the strip above the
 * configuration bar. It shares the geometry and the drawing, so a stage there
 * is the same picture as the same stage in the hero.
 *
 * SPEED is the single time scale. Every boundary, the drift, the banking, the
 * density wave and the breathing all run off it.
 */

export interface FlockHandle { stop(): void }

/** Which of the four. The names live in the markup that shows them. */
export type Stage = 0 | 1 | 2 | 3

/** A stage on the strip: repaint it (the palette is a class away) and put it
 *  away. The swarm runs itself; the other three never move. */
export interface StageHandle { paint(): void; stop(): void }

interface Pt {
  x: number; y: number; sx: number; sy: number
  lx: number; ly: number; px: number; py: number
  a: number; r: number; lag: number; v: number; seed: number; land: number
}

interface Doc { x: number; y: number; w: number; h: number; tilt: number }
interface Wire { x: number; y: number; w: number }
interface Page { x: number; y: number; w: number; h: number }
interface Scene { docs: Doc[]; wires: Wire[]; page: Page; pts: Pt[] }

const P = { docsIn: 1200, leave: 3890, swarm: 8610, report: 13800 }
const LAND = 2400

/** The single time scale, and the only place the sequence's pace is set.
 *
 *  Engine milliseconds run at SPEED against the wall clock, so a boundary at
 *  P.report arrives at P.report / SPEED in real time. Every boundary, every
 *  fade, the drift, the banking, the density wave and the breathing are
 *  measured in engine milliseconds and therefore all move together.
 *
 *  MADE 5% FASTER ON 21 SEPTEMBER (15.1) by multiplying the scale rather than
 *  dividing seventeen constants: dividing every duration and transition by
 *  1.05 and multiplying the clock they are measured against by 1.05 are the
 *  same arithmetic, and one of them can be got wrong in sixteen places. The
 *  whole sequence now runs 20.2 seconds instead of 21.2.
 *
 *  IT DOES NOT REACH drawStage. The strip's stages are drawn from the scene
 *  and, for the swarm, from SWARM_MOMENT and DRIFT_RATE; none of the three
 *  reads this. The application's strip is unchanged by anything here. */
const SPEED = (1.1 / 1.3) * 1.05

/** The moment the swarm is sampled from, in the engine's own milliseconds.
 *
 *  Half way between leaving the documents and landing on the wires: the body
 *  has reached its full spread (the envelope tops out at q = 0.3) and has not
 *  begun to draw in for the landing (q = 0.74). Anywhere else and the still
 *  picture is a swarm caught either forming or dispersing. */
export const SWARM_MOMENT = P.leave + (P.swarm - P.leave) / 2

/** How fast the swarm's own clock runs in the strip, against the wall clock.
 *  Just under a third of real time: the body turns over and breathes without
 *  ever catching the eye of somebody working on the screen below it. */
const DRIFT_RATE = 0.3

/** The mark's three bars, as fractions of its 64-unit square.
 *
 *  Read from brand/logo-deep.svg, which draws them as
 *    x 16, y 21, w 32   x 16, y 30, w 24   x 16, y 39, w 29
 *  each 2.8 high with fully rounded ends, inside a square that is itself
 *  outlined. The y here is the centre of each bar, which is where a line of
 *  particles belongs. */
const LOGO_BARS = [
  { x: 16 / 64, w: 32 / 64, y: 22.4 / 64 },
  { x: 16 / 64, w: 24 / 64, y: 31.4 / 64 },
  { x: 16 / 64, w: 29 / 64, y: 40.4 / 64 },
]

const smooth = (x: number) => { const t = Math.max(0, Math.min(1, x)); return t * t * (3 - 2 * t) }

/** A deterministic stream. A still stage must be the same picture on every
 *  load, so the strip seeds this; the hero keeps Math.random, because it runs
 *  once, moving, and nobody sees it twice. */
function seeded(seed: number): () => number {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 4294967296
  }
}

/* Colour comes from the shared token file, never from a literal here. The
   element is read, not the document, so a canvas that redeclares the
   variables - the strip does, in grey - draws itself in what it declares. */
interface Palette { birds: string; docs: string; wires: string; page: string; trail: string }

function readPalette(el: Element): Palette {
  const cs = getComputedStyle(el)
  const t = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback
  const paper = t('--paper', '#ffffff')
  return {
    birds: t('--medium', '#278aca'),
    docs:  t('--rule', '#c3d0de'),
    wires: t('--light', '#c7e4f8'),
    page:  t('--deep', '#002561'),
    trail: hexToRgba(paper, 0.26),
  }
}

function hexToRgba(hex: string, a: number): string {
  const h = hex.replace('#', '')
  const f = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  const n = parseInt(f, 16)
  if (Number.isNaN(n)) return `rgba(255,255,255,${a})`
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

/** Where everything sits, at one size. The documents on the left, the wires
 *  they are filed on in the middle, the page they are retrieved into on the
 *  right, and every particle's place in all three.
 *
 *  The random stream is given rather than taken, so the hero can be different
 *  every load and a still stage can be the same every time. */
function buildScene(W: number, H: number, N: number, random: () => number,
                   logo = false): Scene {
  const rnd = (a: number, b: number) => a + random() * (b - a)

  const docs: Doc[] = []
  const dw = Math.min(74, W * 0.085), dh = dw * 1.32
  const ox = W * 0.06, oy = H / 2 - (3 * dh + 2 * 10) / 2
  for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++)
    docs.push({ x: ox + c * (dw + 12) + rnd(-3, 3), y: oy + r * (dh + 10) + rnd(-3, 3), w: dw, h: dh, tilt: rnd(-0.035, 0.035) })

  const ROWS = 7, per = Math.ceil(N / ROWS)
  const lw = Math.min(W * 0.42, 440), lh = Math.min(H * 0.6, 205)
  const lx = W * 0.29, ly = H / 2 - lh / 2
  const widths = [1, 0.86, 0.94, 0.72, 0.9, 0.79, 0.97]
  const wires: Wire[] = widths.map((f, r) => ({ y: ly + (r / (ROWS - 1)) * lh, x: lx, w: lw * f }))

  const pw = Math.min(W * 0.24, 230), ph = Math.min(H * 0.78, 280)
  const px = W - pw - W * 0.08, py = H / 2 - ph / 2
  const lines: Wire[] = []
  if (logo) {
    // The page the facts are retrieved into IS the mark, in miniature: three
    // bars in the proportions brand/logo-deep.svg draws them, inside the same
    // outlined square. What is retrieved is an ARQEDIA memorandum, and at
    // 48px a page of fourteen text lines is a grey smear where three bars are
    // a thing you recognise.
    for (const b of LOGO_BARS) {
      lines.push({ x: px + pw * b.x, y: py + ph * b.y, w: pw * b.w })
    }
  } else {
    let yy = py + 26
    while (yy < py + ph - 14) {
      const head = random() < 0.22
      lines.push({ y: yy, x: px + 18, w: (pw - 36) * (head ? 0.46 : rnd(0.72, 1)) })
      yy += head ? 26 : 13
    }
    // A SHORT CANVAS PRODUCES NO LINES AT ALL, and every particle reads one.
    // The first line sits 26 below the top of the page and the last must
    // clear its foot by 14, so a page under about 52px high has room for
    // none. `lines` was then empty, `i % 0` is NaN, `lines[NaN]` is
    // undefined, and reading .x off it threw - which took the whole Configure
    // screen down with it, because an error in an effect with no boundary
    // above it unmounts the tree.
    //
    // The strip no longer comes this way - stage 3 draws the mark - but the
    // guard stays: the next caller with a small canvas should get a line
    // rather than a crash. The hero never reaches it either; at its shortest,
    // 230px, the loop yields eight.
    if (lines.length === 0) {
      lines.push({ y: py + ph / 2, x: px + 6, w: Math.max(6, pw - 12) })
    }
  }
  const page: Page = { x: px, y: py, w: pw, h: ph }

  const pts: Pt[] = []
  for (let i = 0; i < N; i++) {
    const d = docs[i % docs.length], ln = lines[i % lines.length]
    const row = Math.min(ROWS - 1, Math.floor(i / per)), col = i % per, wire = wires[row]
    pts.push({
      x: d.x + rnd(4, d.w - 4), y: d.y + rnd(6, d.h - 6),
      sx: d.x + rnd(4, d.w - 4), sy: d.y + rnd(6, d.h - 6),
      lx: wire.x + (col / Math.max(1, per - 1)) * wire.w + rnd(-2, 2), ly: wire.y,
      px: ln.x + random() * ln.w, py: ln.y,
      a: random() * Math.PI * 2, r: rnd(8, 46), lag: rnd(0.5, 1),
      v: rnd(0.55, 1.4), seed: rnd(0, 6.283), land: rnd(0, 0.92),
    })
  }

  return { docs, wires, page, pts }
}

/** Where one particle is while the body is in the air. */
function swarmAt(p: Pt, ms: number, W: number, H: number, qFix?: number): [number, number] {
  const tt = ms / 1000
  const q = qFix !== undefined ? qFix : Math.min(1, (ms - P.leave) / (P.swarm - P.leave))
  const grow = smooth(q / 0.3), draw = 1 - 0.32 * smooth((q - 0.74) / 0.26)
  const env = (0.16 + 0.84 * grow) * draw
  const cx = W * (0.17 + 0.25 * smooth(q * 1.25)) + Math.sin(tt * 0.44) * W * 0.09 + Math.sin(tt * 0.21 + 2.1) * W * 0.04
  const cy = H * 0.5 + Math.sin(tt * 0.61 + 1.1) * H * 0.12 + Math.cos(tt * 0.29) * H * 0.05
  const bank = Math.sin(tt * 0.34) * 0.55
  const wave = 1 + 0.4 * Math.sin(p.a * 2 - tt * 1.45)
  const breath = 1 + 0.16 * Math.sin(tt * 0.58 + p.seed)
  const a = p.a + tt * p.v * 0.5, nr = p.r / 46
  const ex = Math.cos(a) * (W * 0.3) * nr * env * wave * breath
  const ey = Math.sin(a) * (H * 0.3) * nr * env * wave * breath
  const cs = Math.cos(bank), sn = Math.sin(bank)
  return [cx + ex * cs - ey * sn, cy + ex * sn + ey * cs]
}

/* The three things that are drawn besides the particles. Shared by the hero
   and by a still stage, so a document in the strip is the document in the
   hero. */

function paintDocs(ctx: CanvasRenderingContext2D, docs: Doc[], pal: Palette, a: number) {
  if (a <= 0.01) return
  ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = pal.docs; ctx.lineWidth = 1
  for (const d of docs) {
    ctx.save(); ctx.translate(d.x + d.w / 2, d.y + d.h / 2); ctx.rotate(d.tilt)
    ctx.strokeRect(-d.w / 2, -d.h / 2, d.w, d.h); ctx.restore()
  }
  ctx.restore()
}

function paintWires(ctx: CanvasRenderingContext2D, wires: Wire[], pal: Palette, a: number) {
  if (a <= 0.01) return
  ctx.save(); ctx.globalAlpha = a * 0.8; ctx.strokeStyle = pal.wires; ctx.lineWidth = 1
  ctx.beginPath()
  for (const w of wires) { ctx.moveTo(w.x - 12, w.y); ctx.lineTo(w.x + w.w + 12, w.y) }
  ctx.stroke(); ctx.restore()
}

function paintPage(ctx: CanvasRenderingContext2D, page: Page, pal: Palette, a: number) {
  if (a <= 0.01) return
  ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = pal.page; ctx.lineWidth = 1
  ctx.strokeRect(page.x, page.y, page.w, page.h); ctx.restore()
}

export function mountFlock(cv: HTMLCanvasElement): FlockHandle | null {
  const ctx = cv.getContext('2d')
  if (!ctx) return null

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const stagesEl = cv.parentElement?.querySelector('.stages')
  const spans = stagesEl ? Array.from(stagesEl.querySelectorAll('span')) : []

  const N = 1000
  const dpr = Math.min(window.devicePixelRatio || 1, 2)

  let W = 0, H = 0
  let pts: Pt[] = []
  let docs: Doc[] = []
  let wires: Wire[] = []
  let page: Page = { x: 0, y: 0, w: 0, h: 0 }
  let raf = 0, t0: number | null = null
  let stopped = false, frozen = false
  let pal: Palette = readPalette(cv)

  function build() {
    const scene = buildScene(W, H, N, Math.random)
    docs = scene.docs; wires = scene.wires; page = scene.page; pts = scene.pts
  }

  function resize(): boolean {
    W = cv.clientWidth; H = cv.clientHeight
    if (!W || !H) return false
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr)
    ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
    pal = readPalette(cv)
    build()
    return true
  }

  /** Which stage is running, and which have run (15.2).
   *
   *  'on' is the one happening now: it takes the extra width and the deep
   *  band. 'done' is every stage up to and including it, and it is what keeps
   *  a description on screen after its stage has passed - so the final frame
   *  shows all four stages with what each one did, rather than one sentence
   *  about the last of them and three bare headings.
   *
   *  Both are set from here rather than left to CSS, because only this knows
   *  where the sequence has got to. What they LOOK like is site.css's. */
  const setStage = (i: number) => spans.forEach((el, n) => {
    el.classList.toggle('on', n === i)
    el.classList.toggle('done', n <= i)
  })

  function target(p: Pt, ms: number): [number, number] {
    if (ms < P.leave) return [p.sx, p.sy]
    if (ms < P.swarm) return swarmAt(p, ms, W, H)
    if (ms < P.report) return (ms - P.swarm) / LAND < p.land ? swarmAt(p, ms, W, H) : [p.lx, p.ly]
    return [p.px, p.py]
  }

  function frame(ts: number) {
    if (stopped) return
    if (t0 === null) t0 = ts
    const ms = (ts - t0) * SPEED

    const trailing = ms > P.leave && ms < P.swarm + LAND

    if (trailing) { ctx!.fillStyle = pal.trail; ctx!.fillRect(0, 0, W, H) }
    else ctx!.clearRect(0, 0, W, H)

    paintDocs(ctx!, docs, pal, 1 - smooth((ms - P.docsIn) / (P.leave - P.docsIn)))
    paintWires(ctx!, wires, pal, smooth((ms - P.swarm + 500) / 1600) * (1 - smooth((ms - P.report) / 600)))
    paintPage(ctx!, page, pal, smooth((ms - P.report + 400) / 900))
    const ease = ms < P.swarm ? 0.036 : ms < P.swarm + LAND + 500 ? 0.05 : ms < P.report ? 0.09 : 0.075
    setStage(ms < P.leave ? 0 : ms < P.swarm ? 1 : ms < P.report ? 2 : 3)

    ctx!.fillStyle = pal.birds
    ctx!.globalAlpha = smooth(ms / P.docsIn) * 0.85
    for (const p of pts) {
      const [tx, ty] = target(p, ms)
      p.x += (tx - p.x) * ease * p.lag
      p.y += (ty - p.y) * ease * p.lag
      ctx!.fillRect(p.x, p.y, 1.4, 1.4)
    }
    ctx!.globalAlpha = 1

    if (ms > P.report + 3300) { frozen = true; return }
    raf = requestAnimationFrame(frame)
  }

  /** What somebody who has asked for less motion sees: the last frame, drawn
   *  once and never touched again - the page outlined, every particle already
   *  on the line it was retrieved into, and setStage(3) marking all four
   *  stages done, so the descriptions are the same four the sequence ends on
   *  (15.2). No animation is started at all. */
  function staticFrame() {
    ctx!.clearRect(0, 0, W, H)
    paintPage(ctx!, page, pal, 1)
    setStage(3)
    ctx!.fillStyle = pal.birds; ctx!.globalAlpha = 0.85
    for (const p of pts) ctx!.fillRect(p.px, p.py, 1.4, 1.4)
    ctx!.globalAlpha = 1
  }

  if (!resize()) return null

  let rt = 0
  const onResize = () => {
    window.clearTimeout(rt)
    rt = window.setTimeout(() => { if (resize() && frozen) staticFrame() }, 180)
  }
  window.addEventListener('resize', onResize)

  if (reduce) staticFrame()
  else raf = requestAnimationFrame(frame)

  return {
    stop() { stopped = true; cancelAnimationFrame(raf); window.removeEventListener('resize', onResize) },
  }
}

/**
 * One stage, still, in miniature.
 *
 * Stages 0, 2 and 3 never move: they are the documents as they arrive, the
 * facts as they are filed, and the mark they are retrieved into. Stage 1 is
 * the work in between, and it has no still form - a swarm frozen is a smudge
 * - so it begins at one fixed moment (SWARM_MOMENT) from a fixed seed and
 * then turns over continuously at DRIFT_RATE, slowly enough to read as
 * breathing rather than as an animation.
 *
 * Nothing moves where less motion has been asked for.
 *
 * The palette is read from the canvas, so a grey stage is a matter of the
 * four variables declared on the element and not of anything here.
 */
export function drawStage(
  cv: HTMLCanvasElement,
  stage: Stage,
  count = 300,
  seed = 20260920,
): StageHandle | null {
  const ctx = cv.getContext('2d')
  if (!ctx) return null

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const dpr = Math.min(window.devicePixelRatio || 1, 2)

  let W = 0, H = 0
  let scene: Scene | null = null
  let clock = SWARM_MOMENT
  let raf = 0
  let stopped = false

  function size(): boolean {
    W = cv.clientWidth; H = cv.clientHeight
    if (!W || !H) return false
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr)
    ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
    // The same seed every time, so the picture does not change under somebody
    // who is only resizing the window. Stage 3 is the mark rather than a page
    // of text.
    scene = buildScene(W, H, count, seeded(seed), stage === 3)
    return true
  }

  function paint() {
    if (stopped || !scene) return
    const pal = readPalette(cv)
    ctx!.clearRect(0, 0, W, H)

    if (stage === 0) paintDocs(ctx!, scene.docs, pal, 1)
    if (stage === 2) paintWires(ctx!, scene.wires, pal, 1)
    if (stage === 3) paintPage(ctx!, scene.page, pal, 1)

    // A dot small enough that a hundred of them read as a body rather than a
    // rash, and never thinner than the device can draw.
    const dot = Math.max(0.8, Math.min(1.4, W / 150))
    ctx!.fillStyle = pal.birds
    ctx!.globalAlpha = 0.85
    for (const p of scene.pts) {
      const [x, y] = stage === 0 ? [p.sx, p.sy]
        : stage === 1 ? swarmAt(p, clock, W, H)
        : stage === 2 ? [p.lx, p.ly]
        : [p.px, p.py]
      ctx!.fillRect(x, y, dot, dot)
    }
    ctx!.globalAlpha = 1
  }

  /** The swarm, turning over continuously.
   *
   *  It stirred for two seconds at a time on a change of part, which made the
   *  one stage that is alive look broken between changes. It now runs at
   *  DRIFT_RATE against the wall clock - slow enough to read as breathing
   *  rather than as an animation - and stops for nobody except a person who
   *  has asked for less motion, where it never starts.
   *
   *  requestAnimationFrame does not run in a hidden tab, so a strip nobody is
   *  looking at costs nothing. */
  let last = 0
  function drift(now: number) {
    if (stopped) return
    clock += (last ? now - last : 0) * DRIFT_RATE
    last = now
    paint()
    raf = requestAnimationFrame(drift)
  }

  if (!size()) return null
  paint()
  if (stage === 1 && !reduce) raf = requestAnimationFrame(drift)

  let rt = 0
  const onResize = () => {
    window.clearTimeout(rt)
    rt = window.setTimeout(() => { if (size()) paint() }, 180)
  }
  window.addEventListener('resize', onResize)

  return {
    paint,
    stop() {
      stopped = true
      cancelAnimationFrame(raf)
      window.clearTimeout(rt)
      window.removeEventListener('resize', onResize)
    },
  }
}
