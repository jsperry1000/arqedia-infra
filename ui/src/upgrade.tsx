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

/**
 * What the Enterprise column says (18.5 stage 3).
 *
 * A SECOND COPY, AND THE ONLY ONE IN THIS BRANCH. Everything else on the plan
 * table now comes from the API, which reads the plan table, which migration
 * 033 fills from config/plans.json. Enterprise cannot take that route:
 * plan.seat_count, monthly_price_cents and monthly_credit_cents are NOT NULL,
 * so it is deliberately not a row - and config/plans.json is at the repository
 * root while the API bundle is lambda/api, so the Lambda cannot read it
 * either:
 *
 *     data "archive_file" "api" { source_dir = "${path.module}/lambda/api" }
 *
 * So these words live here, beside the address, on the same reasoning the
 * address already carries: the marketing site keeps its single copy in its own
 * HTML, and the application is not built from the site's files. One copy per
 * codebase, each declared.
 *
 * THE HONEST ALTERNATIVE is to get config/plans.json into the API bundle and
 * have /billing/subscription return Enterprise too, at which point this goes.
 * That is a build change and a decision; it is not taken here.
 *
 * The values are the pricing page's own, and config/plans.json records them as
 * the source of record for all three surfaces.
 */
export const ENTERPRISE_COLUMN = {
  name: "Enterprise",
  /** Rendered where the others show a price. A negotiated price must not be a
   *  release (CLAUDE.md, Money), so there is no number to render. */
  price: "negotiated",
  seats: "as contracted",
  monthly_credit: "as contracted",
  shares: "as contracted",
  field_sets: "10 by default",
  sections: "50 by default",
  daily_classification: "negotiated",
  topup: "$5",
} as const;

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
