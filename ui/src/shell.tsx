import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";

/**
 * The shell's one Back, and what the screens beneath it need from the shell.
 *
 * Back is drawn once, by the shell, in the same place on every screen and
 * held there while the page scrolls (UX-16). What it does belongs to the
 * screen: a memo keeps unsaved work before it goes, and the proposer returns
 * to the editor rather than leaving Configure. A screen hands its leave action
 * up with useBackAction; with none, Back goes to the previous page.
 */

type Register = (leave: () => void) => () => void;

export const BackContext = createContext<Register>(() => () => {});

/** The only Back in the product. One component, one class. */
export function BackPill({ onClick }: { onClick: () => void }) {
  return <a className="back-pill" onClick={onClick}>Back</a>;
}

/** Hand the shell this screen's leave action for as long as it is mounted. */
export function useBackAction(leave: () => void) {
  const register = useContext(BackContext);
  const latest = useRef(leave);
  useLayoutEffect(() => { latest.current = leave; });
  useEffect(() => register(() => latest.current()), [register]);
}

/** Where a pinned head sits: beneath the site header and the Back strip.
 *  Measured rather than assumed, because both change height with the width
 *  of the window and the length of the signed-in address. */
export function usePinTop() {
  const [top, setTop] = useState(0);
  useLayoutEffect(() => {
    const held = [".shell header", ".back-strip"]
      .map((selector) => document.querySelector(selector))
      .filter((el): el is Element => el !== null);
    if (held.length === 0) return;
    const measure = () => setTop(held.reduce(
      (sum, el) => sum + el.getBoundingClientRect().height, 0));
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const watch = new ResizeObserver(measure);
    held.forEach((el) => watch.observe(el));
    return () => watch.disconnect();
  }, []);
  return top;
}
