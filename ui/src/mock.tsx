/**
 * Mock data for the three screens that have no API behind them yet:
 * Wallet, Share and the Viewer.
 *
 * EVERY invented figure in the product is in this one file. When the wallet
 * and sharing endpoints land, this file is deleted and the three screens read
 * `api` instead. Nothing else has to be found and unpicked.
 *
 * The plan figures, the metered rates and the bucket rules are NOT invented -
 * they are the settled tables in the plans and wallet specifications. The
 * counterparties, people, dates and ledger rows are.
 */

import { useState } from "react";

// --- the marker every dead end wears --------------------------------------

/** A control that is drawn, correct, and does nothing. Says so on click
 *  rather than failing silently or pretending to work. */
export function Inert({ children, what }: { children: string; what: string }) {
  const [said, setSaid] = useState(false);
  return (
    <>
      <button onClick={() => setSaid(true)}>{children}</button>
      {said && <span className="mock-said">{what} is not connected yet.</span>}
    </>
  );
}

/** The banner at the head of a screen that has no API behind it. */
export function NotConnected({ what }: { what: string }) {
  return (
    <p className="revision-note mock-flag">
      <strong>Mock.</strong> {what} has no endpoint behind it yet. The figures
      below are from the settled plan and wallet tables; the names, dates and
      ledger rows are invented. Every control is drawn and inert.
    </p>
  );
}

// --- wallet ----------------------------------------------------------------
//
// GONE. The wallet is live: Account reads /wallet and /wallet/ledger.
//
// WALLET, BUCKETS and LEDGER were removed rather than left unused, because an
// exported fake balance is a trap - the next screen that needs a number finds
// one here and never learns it was not real.

// --- sharing ---------------------------------------------------------------

export const SHAREABLE = [
  { memo_id: 101, label: "Credit Memorandum", subject: "Meridian Trading Ltd", generated: "4 March 2026" },
  { memo_id: 102, label: "KYC Memorandum", subject: "Meridian Trading Ltd", generated: "4 March 2026" },
  { memo_id: 103, label: "Lender Memorandum", subject: "Ardmore Logistics Ltd", generated: "12 February 2026" },
];

export const GRANTS = [
  {
    to: "j.ferrers@northbank.com", memo: "Credit Memorandum - Meridian Trading Ltd",
    sent: "4 Mar", opened: "4 Mar", opens: 3, downloads: 1, expires: "3 Apr", registered: true,
  },
  {
    to: "credit.committee@vmac.com", memo: "Credit Memorandum - Meridian Trading Ltd",
    sent: "4 Mar", opened: null, opens: 0, downloads: 0, expires: "3 Apr", registered: false,
  },
  {
    to: "s.abara@ardmore.example", memo: "Lender Memorandum - Ardmore Logistics Ltd",
    sent: "12 Feb", opened: "13 Feb", opens: 1, downloads: 0, expires: "14 Mar", registered: false,
  },
];

/** What a grant carries, and what it does not. The scope is settled in the
 *  share specification; only the values shown are mock. */
export const GRANT_SCOPE = [
  { what: "The rendered memorandum", given: true },
  { what: "The source documents behind each claim", given: false },
  { what: "Your configuration", given: false },
  { what: "Anything else in the engagement", given: false },
];

// --- the viewer ------------------------------------------------------------

/** A stand-in tenant palette, so the one screen where both palettes meet
 *  shows the boundary. The application uses none of this. */
export const TENANT_PALETTE = {
  deep: "#1d3a63",
  mid: "#3f6ea8",
  highlight: "#c9a227",
  light: "#cfe0f2",
};

export const VIEWER_MEMO = {
  label: "Credit Memorandum",
  subject: "Meridian Trading Ltd",
  preparedBy: "TESTCO A",
  generated: "4 March 2026",
  revision: 36,
  expires: "3 April 2026",
  sections: [
    {
      numeral: "IV",
      title: "Existing Indebtedness",
      paragraphs: [
        { text: "The borrower reports senior facilities of USD 24.6m drawn against a committed line of USD 30.0m.", cite: "Audited-Accounts-FY2025.pdf" },
        { text: "Net leverage stands at 2.8\u00d7 on trailing twelve-month EBITDA of USD 8.8m.", cite: "Audited-Accounts-FY2025.pdf" },
      ],
      pill: "Covenant position",
      after: "No financial maintenance covenant ratio is stated in the facility agreement provided.",
    },
  ],
};

// --- subscription ----------------------------------------------------------
//
// SUBSCRIPTION and PLANS are gone. The tab is live: it reads
// /billing/subscription, and the plan table is built from the plan ROWS in
// that response.
//
// Removed rather than left unused, like the fake balance and the fake
// colleagues before them. PLANS was the more dangerous of the two: it listed
// three plans where the database holds two - there is no Enterprise row - so
// the next screen needing "the plans we sell" would have found it here and
// offered one that cannot be bought. It also marked Small Business as the
// current plan of a tenant that had no subscription at all.
//
// INVOICES stays below. Invoices are out of scope on this branch (decision
// record item 8) and those four rows are still invented.

// SEATS is gone. The Seats tab is live: it reads /seats and writes through
// the four routes beside it.
//
// Removed rather than left unused, for the same reason the fake balance was -
// an exported list of make-believe colleagues is a trap, and the next screen
// that needs one finds it here and never learns it was not real.

export const INVOICES = [
  { date: "28 Aug 2026", what: "Small Business, monthly", amount: "$65.00", status: "Paid" },
  { date: "2 Sep 2026", what: "Top-up", amount: "$25.00", status: "Paid" },
  { date: "28 Jul 2026", what: "Small Business, monthly", amount: "$65.00", status: "Paid" },
  { date: "28 Jun 2026", what: "Base, monthly", amount: "$25.00", status: "Paid" },
];

// --- signing up ------------------------------------------------------------

// SIGNUP_PACKS is gone. Signup no longer asks which memorandum somebody
// wants: the choice is made on Get started, after signing in, against the
// memoranda that actually ship and with each one's headings under its section
// count (TPL-02).
//
// Removed rather than left unused, like the fake balance and the fake
// colleagues before it - and this one was worse than either. It named six
// memoranda of which one exists, so the next screen needing "the memoranda we
// offer" would have found it here and offered five that cannot be had.
//
// The marketing site keeps its own copy of that list, in site/src/main.ts, and
// the two had already drifted apart. Recorded in the TPL-02 specification.

/** Where a tenant's data lives. Confirmed once at signup and immutable
 *  afterwards, so it is asked plainly rather than assumed. */
export const REGIONS = [
  { code: "us-east-2", label: "United States \u00b7 Ohio" },
  { code: "eu-west-1", label: "European Union \u00b7 Ireland" },
  { code: "ap-southeast-1", label: "Asia Pacific \u00b7 Singapore" },
];

export const JURISDICTIONS = [
  "United Kingdom", "United States", "Ireland", "Germany", "France",
  "Netherlands", "Switzerland", "United Arab Emirates", "Singapore",
  "Hong Kong SAR", "Australia", "Canada", "Other",
];
