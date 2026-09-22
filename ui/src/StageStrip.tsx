import { useEffect, useRef, useState } from "react";
import { drawStage, mountFlock, type Stage, type StageHandle } from "./flock";

/**
 * The home page's sequence, above the configuration bar.
 *
 * THE SAME ENGINE, THE SAME SEQUENCE, THE SAME TIMINGS. mountFlock, the
 * function the hero on arqedia.com calls, runs here too: documents arrive,
 * dissolve into facts, the facts are filed, and a report is retrieved. Same
 * birds, same boundaries, same SPEED - there is one implementation of it and
 * both surfaces call it.
 *
 * IT DOES NOT FREEZE ON THE REPORT. The hero does, because the page is the
 * end of the story it tells. This sits above a screen somebody works on for
 * an hour, and a frozen picture at the top of it reads as something that has
 * broken - so it asks mountFlock for its other ending, thenSwarm: the
 * particles leave the page and go back to the swarm, which turns over slowly
 * for as long as the screen is open.
 *
 * NO CAPTIONS. mountFlock lights the hero's four descriptions through a
 * .stages element beside its canvas; there is none here, so it lights
 * nothing. The part in use is named by the band beneath and drawn by the
 * StageIcon in the margin - neither of which this touches.
 *
 * WHAT IT REPLACED: four still miniatures in a row, one per stage, with the
 * one in use brought forward. They said where a part sat in the sequence
 * without ever showing the sequence. One canvas cannot be four boxes, so the
 * strip is now a single drawing the width of the page - see .stage-strip.
 *
 * NOTHING MOVES WHERE LESS MOTION HAS BEEN ASKED FOR. mountFlock's own check
 * paints the final frame once and starts no animation at all.
 *
 * The colours are a matter of CSS: flock.ts reads its palette from the canvas
 * element.
 */

export function StageStrip() {
  const canvas = useRef<HTMLCanvasElement | null>(null);
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
   *  at all. It catches, puts the strip away, and leaves the screen alone. */
  useEffect(() => {
    if (failed) return;
    const cv = canvas.current;
    if (!cv) return;
    let handle: { stop(): void } | null = null;
    try {
      handle = mountFlock(cv, { thenSwarm: true });
    } catch (err) {
      console.error("[stage-strip] the sequence failed; the strip is hidden",
                    err);
      setFailed(true);
      return;
    }
    return () => { try { handle?.stop(); } catch { /* going */ } };
  }, [failed]);

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
      handle = drawStage(cv, stage);
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
