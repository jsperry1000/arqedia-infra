import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, type SubscriptionView } from "./api";
import { useRole } from "./upgrade";

/**
 * The trial ending, said on every working screen (19.2).
 *
 * BEFORE THIS the countdown lived on Account > Subscription alone, a tab a
 * person has to go looking for, and the first most tenants knew of the end
 * was File answering "Not enough balance". This is the same fact, drawn in
 * the shell above every screen.
 *
 * WHEN, decided 17 October 2026:
 *   7 to 4 days left   a note
 *   3 to 2 days left   a warning
 *   1 day, or today    the strongest
 *   ended              persistent until a subscription exists
 * Every day from seven, not only on the seventh, third and first: somebody who
 * does not sign in on those days would otherwise see nothing until the last.
 *
 * PUT AWAY UNTIL THE NEXT STEP, decided the same day. Hiding the note at seven
 * days brings it back at three; hiding it at three brings it back at one.
 * The ended banner cannot be put away - filing and generating refuse, and
 * this is where that is explained. Remembered in this browser only: it is a
 * convenience, not a record, and a blocked store simply shows the banner.
 *
 * READ FROM standing, as Account does, never from the absence of a Paddle
 * status: a tenant whose trial has run out has no status either. Any seat
 * may read GET /billing/subscription; only an administrator can subscribe,
 * so a Member is told who can rather than given a control that answers 403.
 *
 * Read again on every change of screen, so subscribing on Account clears it
 * on the way out rather than after a reload. A failed read draws nothing:
 * not knowing is not a reason to tell somebody their trial is ending.
 */

/** The API's datetime, "2026-10-16 14:24:44" in UTC, as a Date. The same
 *  reading Account.tsx's when() makes; kept here rather than reached for, so
 *  this file does not depend on a screen. */
function when(value: string | null): Date | null {
  if (!value) return null;
  const parsed = new Date(value.replace(" ", "T") + "Z");
  return isNaN(parsed.getTime()) ? null : parsed;
}

function on(date: Date) {
  return date.toLocaleDateString(undefined,
    { day: "numeric", month: "long", year: "numeric" });
}

/** Which step of the countdown, or null before it starts. */
function stepOf(daysLeft: number): 7 | 3 | 1 | null {
  if (daysLeft <= 1) return 1;
  if (daysLeft <= 3) return 3;
  if (daysLeft <= 7) return 7;
  return null;
}

function hiddenKey(tenant: string, endsAt: string, step: number) {
  return `trial-banner:${tenant}:${endsAt}:${step}`;
}

function isHidden(key: string): boolean {
  try { return window.localStorage.getItem(key) === "1"; } catch { return false; }
}

export function TrialBanner({ tenant }: { tenant: string }) {
  const [view, setView] = useState<SubscriptionView | null>(null);
  const [, setTick] = useState(0);
  const role = useRole();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  useEffect(() => {
    let alive = true;
    api.subscription()
      .then((v) => { if (alive) setView(v); })
      .catch(() => { if (alive) setView(null); });
    return () => { alive = false; };
  }, [pathname]);

  if (!view || !view.trial_ends_at) return null;
  const ends = when(view.trial_ends_at);
  if (!ends) return null;

  const subscribe = role === "admin" ? (
    <> <a onClick={() => navigate("/account?tab=subscription")}>Subscribe</a></>
  ) : role === "member" ? (
    <> An administrator in your firm can subscribe.</>
  ) : null;

  if (view.standing === "trial_ended") {
    return (
      <p className="revision-note fatal" role="status">
        <strong>Your trial ended on {on(ends)}.</strong>{" "}
        Filing and generating stop until you subscribe. Everything already
        filed or generated stays readable and downloadable.
        {subscribe}
      </p>
    );
  }

  if (view.standing !== "trial") return null;

  const daysLeft = Math.max(0,
    Math.ceil((ends.getTime() - Date.now()) / 86400000));
  const step = stepOf(daysLeft);
  if (step === null) return null;

  const key = hiddenKey(tenant, view.trial_ends_at, step);
  if (isHidden(key)) return null;

  const hide = () => {
    try { window.localStorage.setItem(key, "1"); } catch { /* shown again */ }
    setTick((n) => n + 1);
  };

  const headline = daysLeft === 0 ? "Your trial ends today."
    : daysLeft === 1 ? `Your trial ends tomorrow, ${on(ends)}.`
    : `Your trial ends in ${daysLeft} days, on ${on(ends)}.`;

  return (
    <p className={step === 7 ? "revision-note" : "revision-note fatal"} role="status">
      <strong>{headline}</strong>{" "}
      After that, filing and generating stop until you subscribe.
      {subscribe}
      {" · "}
      <a className="small" onClick={hide}>
        {step === 1 ? "Hide" : `Hide until ${step === 7 ? 3 : 1} day${step === 7 ? "s" : ""} left`}
      </a>
    </p>
  );
}
