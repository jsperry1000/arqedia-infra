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
 * THE SEQUENCE PLAYS ONCE ON ARRIVAL (18.3). Four still drawings in a row
 * say where a part sits in the business; they do not say that the business
 * RUNS left to right, which is the thing the home page spends fifteen
 * seconds making. So on opening Configure the highlight walks the four in
 * order, once, and then settles on the part in use. Nothing is redrawn that
 * was not redrawn before - the walk moves a class, and the class is the
 * palette.
 *
 * The swarm keeps moving afterwards because it always did: stage 1 drifts on
 * its own clock in flock.ts and is never stopped by anything here.
 *
 * NOT AT ALL WHERE LESS MOTION HAS BEEN ASKED FOR. The strip then opens on
 * the part in use, as it does today, and the swarm does not start either -
 * that is flock.ts's own check, and this is a second one for the walk.
 *
 * The colours are a matter of CSS: flock.ts reads its palette from the canvas
 * element, and .stage-mini shadows the four it reads - dulled, or the lit set
 * for the stage in use.
 */

/** How long each stage holds during the opening walk. Four of them, so the
 *  whole thing is under two seconds - long enough to read as a sequence,
 *  short enough that somebody who came to configure a report is not waiting
 *  for a picture. */
const STEP_MS = 420;

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
  // Which stage the opening walk is on, or null once it has finished - and
  // null from the start where less motion has been asked for, so the strip
  // opens on the part in use and never moves.
  const [walking, setWalking] = useState<number | null>(() =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ? null : 0);
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

  // The walk: one stage at a time, left to right, then done. Cleared on
  // unmount, so leaving the screen mid-walk leaves no timer behind.
  useEffect(() => {
    if (walking === null) return;
    const timer = window.setTimeout(
      () => setWalking(walking + 1 < STAGES.length ? walking + 1 : null),
      STEP_MS);
    return () => window.clearTimeout(timer);
  }, [walking]);

  // Which one is bright: the walk while it runs, the part in use afterwards.
  const shown = walking === null ? lit : STAGES[walking].stage;

  // A change of highlight moves a class, which changes the palette the canvas
  // reads - so every stage is repainted. This runs after the class is on the
  // element, which is what makes the repaint pick up the new colours. The
  // swarm repaints itself anyway; the other three would not.
  useEffect(() => {
    guard("repainting", () => {
      handles.current.forEach((h) => h?.paint());
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown]);

  // Nothing at all rather than four broken boxes.
  if (failed) return null;

  return (
    // Decorative: the band beneath already names the part in use, and a
    // screen reader being told about four canvases would learn nothing.
    <div className="stage-strip" aria-hidden="true">
      {STAGES.map((s, i) => (
        <div key={s.stage}
             className={"stage-mini" + (shown === s.stage ? " on" : "")}>
          <canvas ref={(el) => { canvases.current[i] = el; }} />
        </div>
      ))}
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
