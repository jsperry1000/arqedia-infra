import { useEffect, useRef, useState } from "react";
import { drawStage, type Stage, type StageHandle } from "./flock";

/**
 * The four stages of the home page's sequence, still, in miniature, above the
 * configuration bar.
 *
 * It is the same engine the hero runs on - one file, imported by both - so a
 * stage here is the same picture as that stage there. No box and no caption:
 * four small drawings in a row, and the band beneath names the part in use.
 *
 * STAGE 1 IS NEVER LIT. It is the work the model does between a document
 * arriving and a fact being filed, and no part of the configuration screen
 * corresponds to it. It is also the one stage with no still form - a swarm
 * frozen is a smudge - so it alone moves, continuously and slowly, and not at
 * all where less motion has been asked for. The other three never move.
 *
 * STAGE 3 IS THE MARK. What is retrieved is an ARQEDIA memorandum, and at
 * 48px the mark's three bars are a thing a person recognises where fourteen
 * lines of text are a smear.
 *
 * The colours are a matter of CSS: flock.ts reads its palette from the canvas
 * element, and .stage-mini shadows the four it reads - dulled, or the lit set
 * for the stage in use.
 */

// The names are no longer drawn; they are kept because the order is the
// sequence and a bare list of numbers says nothing to whoever reads this next.
const STAGES: { stage: Stage; name: string }[] = [
  { stage: 0, name: "Documents" },
  { stage: 1, name: "Facts" },
  { stage: 2, name: "Filed" },
  { stage: 3, name: "Report" },
];

export function StageStrip({ lit }: { lit: Stage | null }) {
  const canvases = useRef<(HTMLCanvasElement | null)[]>([]);
  const handles = useRef<(StageHandle | null)[]>([]);
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
  const guard = (what: string, run: () => void) => {
    if (failed) return;
    try {
      run();
    } catch (err) {
      // Logged once, and said plainly: a picture is missing, nothing else.
      console.error("[stage-strip] %s failed; the strip is hidden", what, err);
      handles.current.forEach((h) => { try { h?.stop(); } catch { /* going */ } });
      handles.current = [];
      setFailed(true);
    }
  };

  // Mounted once. Each canvas keeps its own geometry, and the swarm keeps its
  // own clock and runs itself from here on.
  useEffect(() => {
    guard("drawing", () => {
      handles.current = STAGES.map((s, i) => {
        const cv = canvases.current[i];
        return cv ? drawStage(cv, s.stage) : null;
      });
    });
    return () => {
      handles.current.forEach((h) => { try { h?.stop(); } catch { /* going */ } });
      handles.current = [];
    };
    // guard closes over `failed`, which only ever goes false to true; the
    // strip is drawn once and this must not run again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A change of part moves the highlight, which is a class, which changes the
  // palette the canvas reads - so every stage is repainted. This runs after
  // the class is on the element, which is what makes the repaint pick up the
  // new colours. The swarm repaints itself anyway; the other three would not.
  useEffect(() => {
    guard("repainting", () => {
      handles.current.forEach((h) => h?.paint());
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lit]);

  // Nothing at all rather than four broken boxes.
  if (failed) return null;

  return (
    // Decorative: the band beneath already names the part in use, and a
    // screen reader being told about four canvases would learn nothing.
    <div className="stage-strip" aria-hidden="true">
      {STAGES.map((s, i) => (
        <div key={s.stage}
             className={"stage-mini" + (lit === s.stage ? " on" : "")}>
          <canvas ref={(el) => { canvases.current[i] = el; }} />
        </div>
      ))}
    </div>
  );
}
