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
 * Two modes off one engine. 'hero' runs the full sequence and holds on the
 * final frame. 'work' holds the swarm indefinitely and lands when settle() is
 * called.
 *
 * NOTE ON 'work'. Nothing imports it. The application's working indicator
 * (UX-12) is a CSS bar, not this, so the mode is unused today - the comment
 * that once said otherwise was wrong and has gone.
 *
 * drawStage() is the third way in: one stage, still, for the strip above the
 * configuration bar. It shares the geometry and the drawing, so a stage there
 * is the same picture as the same stage in the hero.
 *
 * SPEED is the single time scale. Every boundary, the drift, the banking, the
 * density wave and the breathing all run off it.
 */

export type FlockMode = 'hero' | 'work'
export interface FlockHandle { stop(): void; settle(): void }

/** Which of the four. The names live in the markup that shows them. */
export type Stage = 0 | 1 | 2 | 3

/** A still stage, and - for the swarm alone - a way to move it a little. */
export interface StageHandle { paint(): void; nudge(): void; stop(): void }

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
const SPEED = 1.1 / 1.3

/** The moment the swarm is sampled from, in the engine's own milliseconds.
 *
 *  Half way between leaving the documents and landing on the wires: the body
 *  has reached its full spread (the envelope tops out at q = 0.3) and has not
 *  begun to draw in for the landing (q = 0.74). Anywhere else and the still
 *  picture is a swarm caught either forming or dispersing. */
export const SWARM_MOMENT = P.leave + (P.swarm - P.leave) / 2

/** One nudge: how far the swarm's own clock moves, and how long that takes on
 *  the wall clock. Slow on purpose - the strip is a picture that stirs, not
 *  an animation. */
const NUDGE_MS = 900
const NUDGE_FOR = 2000

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
function buildScene(W: number, H: number, N: number, random: () => number): Scene {
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
  let yy = py + 26
  while (yy < py + ph - 14) {
    const head = random() < 0.22
    lines.push({ y: yy, x: px + 18, w: (pw - 36) * (head ? 0.46 : rnd(0.72, 1)) })
    yy += head ? 26 : 13
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

export function mountFlock(cv: HTMLCanvasElement, mode: FlockMode): FlockHandle | null {
  const ctx = cv.getContext('2d')
  if (!ctx) return null

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const stagesEl = cv.parentElement?.querySelector('.stages')
  const spans = stagesEl ? Array.from(stagesEl.querySelectorAll('span')) : []

  const N = mode === 'hero' ? 1000 : 620
  const dpr = Math.min(window.devicePixelRatio || 1, 2)

  let W = 0, H = 0
  let pts: Pt[] = []
  let docs: Doc[] = []
  let wires: Wire[] = []
  let page: Page = { x: 0, y: 0, w: 0, h: 0 }
  let raf = 0, t0: number | null = null
  let stopped = false, frozen = false
  let phase: 'swarm' | 'landed' = 'swarm'
  let settleAt = 0
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

  const setStage = (i: number) => spans.forEach((el, n) => el.classList.toggle('on', n === i))

  function target(p: Pt, ms: number): [number, number] {
    if (mode === 'hero') {
      if (ms < P.leave) return [p.sx, p.sy]
      if (ms < P.swarm) return swarmAt(p, ms, W, H)
      if (ms < P.report) return (ms - P.swarm) / LAND < p.land ? swarmAt(p, ms, W, H) : [p.lx, p.ly]
      return [p.px, p.py]
    }
    if (phase === 'swarm') return swarmAt(p, ms, W, H, 0.86)
    return (ms - settleAt) / LAND < p.land ? swarmAt(p, ms, W, H, 0.86) : [p.lx, p.ly]
  }

  function frame(ts: number) {
    if (stopped) return
    if (t0 === null) t0 = ts
    const ms = (ts - t0) * SPEED

    const trailing = mode === 'hero'
      ? ms > P.leave && ms < P.swarm + LAND
      : phase === 'swarm' || ms < settleAt + LAND

    if (trailing) { ctx!.fillStyle = pal.trail; ctx!.fillRect(0, 0, W, H) }
    else ctx!.clearRect(0, 0, W, H)

    let ease: number
    if (mode === 'hero') {
      paintDocs(ctx!, docs, pal, 1 - smooth((ms - P.docsIn) / (P.leave - P.docsIn)))
      paintWires(ctx!, wires, pal, smooth((ms - P.swarm + 500) / 1600) * (1 - smooth((ms - P.report) / 600)))
      paintPage(ctx!, page, pal, smooth((ms - P.report + 400) / 900))
      ease = ms < P.swarm ? 0.036 : ms < P.swarm + LAND + 500 ? 0.05 : ms < P.report ? 0.09 : 0.075
      setStage(ms < P.leave ? 0 : ms < P.swarm ? 1 : ms < P.report ? 2 : 3)
    } else {
      paintWires(ctx!, wires, pal, phase === 'swarm' ? 0 : smooth((ms - settleAt + 500) / 1600))
      ease = phase === 'swarm' ? 0.036 : ms < settleAt + LAND + 500 ? 0.05 : 0.09
    }

    ctx!.fillStyle = pal.birds
    ctx!.globalAlpha = mode === 'hero' ? smooth(ms / P.docsIn) * 0.85 : 0.8
    for (const p of pts) {
      const [tx, ty] = target(p, ms)
      p.x += (tx - p.x) * ease * p.lag
      p.y += (ty - p.y) * ease * p.lag
      ctx!.fillRect(p.x, p.y, 1.4, 1.4)
    }
    ctx!.globalAlpha = 1

    const over = mode === 'hero'
      ? ms > P.report + 3300
      : phase === 'landed' && ms > settleAt + LAND + 1400
    if (over) { frozen = true; return }
    raf = requestAnimationFrame(frame)
  }

  function staticFrame() {
    ctx!.clearRect(0, 0, W, H)
    if (mode === 'hero') { paintPage(ctx!, page, pal, 1); setStage(3) } else paintWires(ctx!, wires, pal, 1)
    ctx!.fillStyle = pal.birds; ctx!.globalAlpha = 0.85
    for (const p of pts) mode === 'hero' ? ctx!.fillRect(p.px, p.py, 1.4, 1.4) : ctx!.fillRect(p.lx, p.ly, 1.4, 1.4)
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
    settle() {
      if (mode === 'hero' || phase !== 'swarm' || t0 === null) return
      phase = 'landed'
      settleAt = (performance.now() - t0) * SPEED
    },
  }
}

/**
 * One stage, still, in miniature.
 *
 * Stages 0, 2 and 3 never move: they are the documents as they arrive, the
 * facts as they are filed, and the page they are retrieved into. Stage 1 is
 * the work in between, and it has no still form - a swarm frozen is a smudge
 * - so it is sampled at one fixed moment (SWARM_MOMENT) from a fixed seed,
 * and stirs for two seconds when nudge() is called, easing in and out and
 * carrying on next time from wherever it stopped.
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
    // who is only resizing the window.
    scene = buildScene(W, H, count, seeded(seed))
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

  function nudge() {
    // Only the swarm moves, and only where motion is welcome. A nudge while
    // one is already running is ignored rather than stacked: two at once
    // would run the clock at double speed.
    if (stage !== 1 || reduce || stopped || raf) return
    const from = clock
    const began = performance.now()
    const step = (now: number) => {
      const t = Math.min(1, (now - began) / NUDGE_FOR)
      // Smoothstep: still at both ends, so it neither jerks into motion nor
      // stops dead.
      clock = from + NUDGE_MS * smooth(t)
      paint()
      if (t >= 1 || stopped) { raf = 0; return }
      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
  }

  if (!size()) return null
  paint()

  let rt = 0
  const onResize = () => {
    window.clearTimeout(rt)
    rt = window.setTimeout(() => { if (size()) paint() }, 180)
  }
  window.addEventListener('resize', onResize)

  return {
    paint,
    nudge,
    stop() {
      stopped = true
      cancelAnimationFrame(raf)
      window.clearTimeout(rt)
      window.removeEventListener('resize', onResize)
    },
  }
}
