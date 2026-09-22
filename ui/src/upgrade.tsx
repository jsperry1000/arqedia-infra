import { useEffect, useState, type ReactNode } from "react";
import { fetchAuthSession } from "aws-amplify/auth";
import { useNavigate } from "react-router-dom";

/**
 * Where a plan limit is met, and what to do about it.
 *
 * ONE COMPONENT, FIVE SENTENCES. Every throttled screen says what IT is
 * short of - seats, brand, balance - because "upgrade your plan" on its own
 * tells somebody nothing they did not already know. What is shared is the
 * shape and the destination: a note, and one control that lands on the plan
 * table.
 *
 * THE CONTROL IS NOT A GATE. Reading the plans is open to any seat, so
 * pressing it is harmless whoever presses it; changing the plan is an
 * administrator act and the server refuses a member
 * (`_require_seats_admin`). A member therefore sees the control disabled
 * with the reason stated, as the brand settings already do for the plan -
 * being shown a door that answers 403 is worse than being told who holds the
 * key.
 */

/** Where an Enterprise enquiry goes.
 *
 *  ONE COPY IN THIS CODEBASE. Settings and Account both import it, and the
 *  marketing site carries its own single copy in its own HTML - a static
 *  page that fetched its address from JavaScript would have nothing to say
 *  with JavaScript off, which is worse than two copies in two codebases.
 *
 *  THE MAILBOX DOES NOT EXIST YET. arqedia.com publishes no MX record, in
 *  Terraform or live, so mail to it is undeliverable today. Built anyway, by
 *  decision of 20 September; the mailbox is being fixed separately. */
export const ENTERPRISE_EMAIL = "enterprise@arqedia.com";

export const ENTERPRISE_MAILTO =
  "mailto:" + ENTERPRISE_EMAIL + "?subject=" +
  encodeURIComponent("ARQEDIA Enterprise enquiry");

/** Where the plans are, and where a top-up is. The tab is in the address so
 *  a control elsewhere can land on the right one (11.1). */
export const PLANS = "/account?tab=subscription";
export const BALANCE = "/account?tab=balance";
/** Where a colleague is actually invited. Named here with the other two
 *  because the second-administrator prompt on Get started points at it
 *  (18.8), and an address written into a screen is an address that drifts. */
export const SEATS = "/account?tab=seats";

const MEMBER_REASON =
  "Changing the plan is an administrator's. You can see what each one holds.";

/** The caller's role, from the same claim the API reads.
 *
 *  Not fetched from /settings: this sits on screens that have no reason to
 *  read settings, and the claim is already in the token the browser holds.
 *  Null while it is being read, and on any failure - an unknown role shows
 *  the control rather than hiding it, because the screen is not the control. */
export function useRole(): "admin" | "member" | null {
  const [role, setRole] = useState<"admin" | "member" | null>(null);
  useEffect(() => {
    let alive = true;
    fetchAuthSession()
      .then((session) => {
        const claims: any = session.tokens?.idToken?.payload ?? {};
        const found = String(claims["custom:role"] ?? "");
        if (alive && (found === "admin" || found === "member")) setRole(found);
      })
      .catch(() => undefined);
    return () => { alive = false; };
  }, []);
  return role;
}

export function UpgradePrompt({ children, action = "See plans",
                                to = PLANS, tone = "note" }: {
  /** The limit, in the words of the screen this sits on. */
  children: ReactNode;
  action?: string;
  to?: string;
  /** "note" beside ordinary copy; "warn" where the screen is already
   *  warning, so the prompt does not read as a second, calmer subject. */
  tone?: "note" | "warn";
}) {
  const navigate = useNavigate();
  const role = useRole();
  const member = role === "member";

  return (
    <div className="revision-note">
      <span className={tone === "warn" ? "warn" : undefined}>{children}</span>
      <div className="form-actions">
        <button disabled={member} onClick={() => navigate(to)}>{action}</button>
        {member && <span className="muted small">{MEMBER_REASON}</span>}
      </div>
    </div>
  );
}

/** "Talk to us about Enterprise" (11.4).
 *
 *  A plain mailto rather than a form: there is no route behind it, and a
 *  control that opens a composer the person can see is honest about what it
 *  does. Enterprise is negotiated and is deliberately not a plan row
 *  (CLAUDE.md, Money), so this is the only way to ask for it. */
export function EnterpriseLink({ className = "small" }: { className?: string }) {
  return (
    <a className={className} href={ENTERPRISE_MAILTO}>
      Talk to us about Enterprise
    </a>
  );
}
