/* flock.ts
 *
 * Documents -> facts -> filed -> retrieved, once, on load.
 *
 * Two modes off one engine. 'hero' runs the full sequence and holds on the
 * final frame. 'work' holds the swarm indefinitely and lands when settle() is
 * called — that mode is for the application's working indicator (UX-12) and is
 * exported here so the two never drift apart.
 *
 * SPEED is the single time scale. Every boundary, the drift, the banking, the
 * density wave and the breathing all run off it.
 */

export type FlockMode = 'hero' | 'work'
export interface FlockHandle { stop(): void; settle(): void }

interface Pt {
  x: number; y: number; sx: number; sy: number
  lx: number; ly: number; px: number; py: number
  a: number; r: number; lag: number; v: number; seed: number; land: number
}

const P = { docsIn: 1200, leave: 3890, swarm: 8610, report: 13800 }
const LAND = 2400
const SPEED = 1.1 / 1.3

const rnd = (a: number, b: number) => a + Math.random() * (b - a)
const smooth = (x: number) => { const t = Math.max(0, Math.min(1, x)); return t * t * (3 - 2 * t) }

/* Colour comes from the shared token file, never from a literal here. */
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
  let docs: { x: number; y: number; w: number; h: number; tilt: number }[] = []
  let wires: { x: number; y: number; w: number }[] = []
  let page = { x: 0, y: 0, w: 0, h: 0 }
  let raf = 0, t0: number | null = null
  let stopped = false, frozen = false
  let phase: 'swarm' | 'landed' = 'swarm'
  let settleAt = 0
  let pal: Palette = readPalette(cv)

  function build() {
    docs = []
    const dw = Math.min(74, W * 0.085), dh = dw * 1.32
    const ox = W * 0.06, oy = H / 2 - (3 * dh + 2 * 10) / 2
    for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++)
      docs.push({ x: ox + c * (dw + 12) + rnd(-3, 3), y: oy + r * (dh + 10) + rnd(-3, 3), w: dw, h: dh, tilt: rnd(-0.035, 0.035) })

    const ROWS = 7, per = Math.ceil(N / ROWS)
    const lw = Math.min(W * 0.42, 440), lh = Math.min(H * 0.6, 205)
    const lx = W * 0.29, ly = H / 2 - lh / 2
    const widths = [1, 0.86, 0.94, 0.72, 0.9, 0.79, 0.97]
    wires = widths.map((f, r) => ({ y: ly + (r / (ROWS - 1)) * lh, x: lx, w: lw * f }))

    const pw = Math.min(W * 0.24, 230), ph = Math.min(H * 0.78, 280)
    const px = W - pw - W * 0.08, py = H / 2 - ph / 2
    const lines: { x: number; y: number; w: number }[] = []
    let yy = py + 26
    while (yy < py + ph - 14) {
      const head = Math.random() < 0.22
      lines.push({ y: yy, x: px + 18, w: (pw - 36) * (head ? 0.46 : rnd(0.72, 1)) })
      yy += head ? 26 : 13
    }
    page = { x: px, y: py, w: pw, h: ph }

    pts = []
    for (let i = 0; i < N; i++) {
      const d = docs[i % docs.length], ln = lines[i % lines.length]
      const row = Math.min(ROWS - 1, Math.floor(i / per)), col = i % per, wire = wires[row]
      pts.push({
        x: d.x + rnd(4, d.w - 4), y: d.y + rnd(6, d.h - 6),
        sx: d.x + rnd(4, d.w - 4), sy: d.y + rnd(6, d.h - 6),
        lx: wire.x + (col / Math.max(1, per - 1)) * wire.w + rnd(-2, 2), ly: wire.y,
        px: ln.x + Math.random() * ln.w, py: ln.y,
        a: Math.random() * Math.PI * 2, r: rnd(8, 46), lag: rnd(0.5, 1),
        v: rnd(0.55, 1.4), seed: rnd(0, 6.283), land: rnd(0, 0.92),
      })
    }
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

  function drawDocs(a: number) {
    if (a <= 0.01) return
    ctx!.save(); ctx!.globalAlpha = a; ctx!.strokeStyle = pal.docs; ctx!.lineWidth = 1
    for (const d of docs) {
      ctx!.save(); ctx!.translate(d.x + d.w / 2, d.y + d.h / 2); ctx!.rotate(d.tilt)
      ctx!.strokeRect(-d.w / 2, -d.h / 2, d.w, d.h); ctx!.restore()
    }
    ctx!.restore()
  }

  function drawWires(a: number) {
    if (a <= 0.01) return
    ctx!.save(); ctx!.globalAlpha = a * 0.8; ctx!.strokeStyle = pal.wires; ctx!.lineWidth = 1
    ctx!.beginPath()
    for (const w of wires) { ctx!.moveTo(w.x - 12, w.y); ctx!.lineTo(w.x + w.w + 12, w.y) }
    ctx!.stroke(); ctx!.restore()
  }

  function drawPage(a: number) {
    if (a <= 0.01) return
    ctx!.save(); ctx!.globalAlpha = a; ctx!.strokeStyle = pal.page; ctx!.lineWidth = 1
    ctx!.strokeRect(page.x, page.y, page.w, page.h); ctx!.restore()
  }

  function swarmPos(p: Pt, ms: number, qFix?: number): [number, number] {
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

  function target(p: Pt, ms: number): [number, number] {
    if (mode === 'hero') {
      if (ms < P.leave) return [p.sx, p.sy]
      if (ms < P.swarm) return swarmPos(p, ms)
      if (ms < P.report) return (ms - P.swarm) / LAND < p.land ? swarmPos(p, ms) : [p.lx, p.ly]
      return [p.px, p.py]
    }
    if (phase === 'swarm') return swarmPos(p, ms, 0.86)
    return (ms - settleAt) / LAND < p.land ? swarmPos(p, ms, 0.86) : [p.lx, p.ly]
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
      drawDocs(1 - smooth((ms - P.docsIn) / (P.leave - P.docsIn)))
      drawWires(smooth((ms - P.swarm + 500) / 1600) * (1 - smooth((ms - P.report) / 600)))
      drawPage(smooth((ms - P.report + 400) / 900))
      ease = ms < P.swarm ? 0.036 : ms < P.swarm + LAND + 500 ? 0.05 : ms < P.report ? 0.09 : 0.075
      setStage(ms < P.leave ? 0 : ms < P.swarm ? 1 : ms < P.report ? 2 : 3)
    } else {
      drawWires(phase === 'swarm' ? 0 : smooth((ms - settleAt + 500) / 1600))
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
    if (mode === 'hero') { drawPage(1); setStage(3) } else drawWires(1)
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
