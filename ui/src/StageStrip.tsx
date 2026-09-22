import { useEffect, useRef, useState } from "react";
import { drawStage, mountStrip, type Stage, type StageHandle,
         type StripHandle } from "./flock";

/**
 * The four stages in a row, with one flock crossing them (18.3).
 *
 * THE WIREFRAMES STAY DRAWN. Documents, facts, wires, mark - the shape of the
 * business, and a shape that appears and disappears is an animation rather
 * than a bearing. The birds are what moves: they start in the documents,
 * leave and fly, settle on the wires, move into the mark, and then go back to
 * the facts and murmurate there for as long as the screen is open.
 *
 * ONE CANVAS, FOUR CELLS. The flock has to cross them, so they cannot be four
 * canvases; the engine draws a quarter each and moves the birds between them.
 *
 * 30% FASTER THAN THE HERO, on the strip's own scale - see STRIP_SPEED. The
 * hero is the thing somebody came to look at; this sits above a screen they
 * came to work on.
 *
 * NO CAPTIONS, no boxes. The part in use is named by the band beneath, and
 * shown here by its own wireframe being drawn at full strength while the
 * other two are dimmed. That mapping is the part's stage: Document types the
 * documents, Facts the wires they are filed on, Report sections the mark.
 *
 * IT RUNS ONCE EACH TIME CONFIGURE OPENS, because the component mounts with
 * the screen. Under prefers-reduced-motion it draws one still frame - the
 * wireframes, and the birds already home in the facts - and starts nothing.
 */

export function StageStrip({ lit }: { lit: Stage | null }) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const handle = useRef<StripHandle | null>(null);
  // Which cell is prominent. Held in a ref as well as passed, so the mount
  // below can read it without taking it as a dependency - the sequence runs
  // once on arrival and must not restart when somebody changes part.
  const litRef = useRef<Stage | null>(lit);
  // Set where drawing threw. This is decoration; the screen behind it is the
  // work.
  const [failed, setFailed] = useState(false);

  /** THE STRIP MUST NEVER TAKE THE PAGE DOWN WITH IT.
   *
   *  An error thrown in an effect with no boundary above it unmounts the
   *  whole tree, which is exactly what happened on 20 September: a canvas too
   *  short to hold a single line of the page made buildScene read a property
   *  off undefined, and the Configure screen rendered blank. The cause is
   *  fixed in flock.ts; this is the guard that stops any future one mattering
   *  at all. It catches, puts the strip away, and leaves the screen alone.
   *
   *  MOUNTED ONCE. The sequence runs on arrival and must not restart every
   *  time somebody changes part - which is why the lit stage is handed to the
   *  handle below rather than being a dependency here. */
  useEffect(() => {
    if (failed) return;
    const cv = canvas.current;
    if (!cv) return;
    try {
      handle.current = mountStrip(cv, litRef.current);
    } catch (err) {
      console.error("[stage-strip] the sequence failed; the strip is hidden",
                    err);
      setFailed(true);
      return;
    }
    return () => {
      try { handle.current?.stop(); } catch { /* going */ }
      handle.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [failed]);

  // The prominence moves without remounting anything.
  useEffect(() => {
    litRef.current = lit;
    handle.current?.setLit(lit);
  }, [lit]);

  // Nothing at all rather than a broken box.
  if (failed) return null;

  return (
    // Decorative: the band beneath names the part in use in words.
    <div className="stage-strip" aria-hidden="true">
      <canvas ref={canvas} />
    </div>
  );
}

/**
 * The part in use, drawn once more and larger, beside the band (18.3).
 *
 * The strip says where every part sits in the sequence; this says which one
 * is on screen, in the same picture rather than in another word - the band's
 * own tab already carries the words. Drawn from the same engine, so it is
 * the strip's miniature enlarged and not a second illustration of the same
 * idea.
 *
 * IT IS NEVER DULLED. The strip dulls the three that are not in use, which
 * is what makes the fourth read as chosen; there is only one here, and it is
 * by definition the chosen one. So it declares no palette and inherits
 * ARQEDIA's own - never the tenant's; this is chrome.
 *
 * Redrawn from scratch on a change of part rather than repainted: the scene
 * is built per stage, and stage 0 is not stage 3 with different colours.
 */
export function StageIcon({ stage }: { stage: Stage | null }) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (failed || stage === null) return;
    const cv = canvas.current;
    if (!cv) return;
    let handle: StageHandle | null = null;
    try {
      // Heavier than the hero's hairline: at this size a one-pixel stroke
      // reads as a scratch rather than as a drawing (18.3).
      handle = drawStage(cv, stage, 300, 20260920, 2);
    } catch (err) {
      // The same guard the strip carries, and for the same reason: this is
      // decoration, and the screen behind it is the work.
      console.error("[stage-icon] drawing failed; the icon is hidden", err);
      setFailed(true);
      return;
    }
    return () => { try { handle?.stop(); } catch { /* going */ } };
  }, [stage, failed]);

  if (failed || stage === null) return null;

  return (
    // Decorative: the tab beside it names the part in words.
    <div className="stage-icon" aria-hidden="true">
      <canvas ref={canvas} />
    </div>
  );
}
