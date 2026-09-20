import { useEffect, useRef } from "react";
import { drawStage, type Stage, type StageHandle } from "./flock";

/**
 * The four stages of the home page's sequence, still, in miniature, above the
 * configuration bar.
 *
 * It is the same engine the hero runs on - one file, imported by both - so a
 * stage here is the same picture as that stage there. What differs is that
 * these do not move and are drawn dull: the strip says where in the whole
 * business the part on screen sits, and a moving picture beside a working
 * screen would be a distraction rather than an orientation.
 *
 * STAGE 1 IS NEVER LIT. It is the work the model does between a document
 * arriving and a fact being filed, and no part of the configuration screen
 * corresponds to it. It is also the one stage with no still form - a swarm
 * frozen is a smudge - so it alone is allowed to stir, for two seconds, when
 * the part changes.
 *
 * The colours are a matter of CSS: flock.ts reads its palette from the canvas
 * element, and .stage-mini:not(.on) shadows the four it reads.
 */

const STAGES: { stage: Stage; name: string }[] = [
  { stage: 0, name: "Documents" },
  { stage: 1, name: "Facts" },
  { stage: 2, name: "Filed" },
  { stage: 3, name: "Report" },
];

export function StageStrip({ lit }: { lit: Stage | null }) {
  const canvases = useRef<(HTMLCanvasElement | null)[]>([]);
  const handles = useRef<(StageHandle | null)[]>([]);

  // Mounted once. Each canvas keeps its own geometry and, for the swarm, its
  // own clock, so the stirring carries on from where it stopped rather than
  // starting again on every change of part.
  useEffect(() => {
    handles.current = STAGES.map((s, i) => {
      const cv = canvases.current[i];
      return cv ? drawStage(cv, s.stage) : null;
    });
    return () => {
      handles.current.forEach((h) => h?.stop());
      handles.current = [];
    };
  }, []);

  // A change of part moves the highlight, which is a class, which changes the
  // palette the canvas reads - so every stage is repainted, and the swarm is
  // nudged. This runs after the class is on the element, which is what makes
  // the repaint pick up the new colours.
  useEffect(() => {
    handles.current.forEach((h) => h?.paint());
    handles.current[1]?.nudge();
  }, [lit]);

  return (
    // Decorative: the band beneath already names the part in use, and a
    // screen reader being told about four canvases would learn nothing.
    <div className="stage-strip" aria-hidden="true">
      {STAGES.map((s, i) => (
        <figure key={s.stage}
                className={"stage-mini" + (lit === s.stage ? " on" : "")}>
          <canvas ref={(el) => { canvases.current[i] = el; }} />
          <figcaption>{s.name}</figcaption>
        </figure>
      ))}
    </div>
  );
}
