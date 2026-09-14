import './styles/site.css'
import { mountFlock } from './flock'

/* The hero animation, and the citation panel. Nothing else on the page moves. */

const canvas = document.querySelector<HTMLCanvasElement>('canvas[data-flock]')
if (canvas) mountFlock(canvas, 'hero')

const scope = document.querySelector<HTMLElement>('[data-cites]')
if (scope) {
  const claims = Array.from(scope.querySelectorAll<HTMLElement>('.claim'))
  const spans = Array.from(scope.querySelectorAll<HTMLElement>('.doc .span'))
  const light = (i: number) => {
    claims.forEach((c, n) => c.classList.toggle('lit', n === i))
    spans.forEach((s, n) => s.classList.toggle('lit', n === i))
  }
  claims.forEach((c, i) => {
    c.tabIndex = 0
    c.addEventListener('click', () => light(i))
    c.addEventListener('focus', () => light(i))
  })
  light(0)
}
