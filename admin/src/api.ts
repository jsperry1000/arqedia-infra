/**
 * The admin API, read-only.
 *
 * Every call carries the id token from the current Amplify session. The
 * gateway verifies it against the staff pool before the Lambda runs, so a
 * request without one never reaches a query.
 *
 * THREE ROUTES AND NO OTHERS. There is no post(), no put() and no del() in
 * this file, because there is nothing on the other end to call: the admin API
 * declares three GET routes. A write here would be a stage of its own, and
 * would start with a decision about what staff may change on a tenant's
 * behalf.
 */
import { fetchAuthSession } from "aws-amplify/auth";

import { config } from "./config";

export type Tenant = {
  tenant_id: number;
  name: string;
  /** tenant.plan - a copy, written from the subscription. */
  plan: string | null;
  /** plan.plan_key through subscription.plan_id - the plan itself. */
  subscription_plan: string | null;
  subscription_status: string | null;
  seats: number;
  created_at: string | null;
  trial_ends_at: string | null;
  active_revision: number | null;
};

export type Seat = {
  seat_id: number;
  email: string;
  role: string;
  invited_by: string | null;
  accepted_at: string | null;
};

export type Invitation = {
  invitation_id: number;
  email: string;
  role: string;
  invited_by: string | null;
  created_at: string | null;
  expires_at: string | null;
};

export type SeatsPage = {
  tenant_id: number;
  name: string;
  seats: Seat[];
  invitations: Invitation[];
};

export type SignupAttempt = {
  attempt_id: number;
  /** The domain, never the address: signup_attempt keeps a hash of that. */
  email_domain: string;
  email_hash: string;
  ip: string | null;
  outcome: string;
  detail: string | null;
  created_at: string | null;
};

export type SignupsPage = {
  attempts: SignupAttempt[];
  limit: number;
  offset: number;
  total: number;
  /** null at the end of the list, so a caller stops without arithmetic. */
  next_offset: number | null;
};

async function get<T>(path: string): Promise<T> {
  const session = await fetchAuthSession();
  const token = session.tokens?.idToken?.toString();
  if (!token) {
    throw new Error("Not signed in.");
  }

  const res = await fetch(config.apiUrl + path, {
    headers: { Authorization: "Bearer " + token },
  });

  if (!res.ok) {
    // The gateway answers 401 as {"message":"Unauthorized"} and the function
    // answers as {"error": "..."}. Both are read, so a refusal from either
    // reaches the screen as a sentence rather than as a status number.
    let said = "";
    try {
      const body = await res.json();
      said = body?.error || body?.message || "";
    } catch {
      said = "";
    }
    throw new Error(said || `${res.status} ${res.statusText}`);
  }

  return res.json() as Promise<T>;
}

export const api = {
  tenants: () => get<{ tenants: Tenant[] }>("/tenants"),
  seats: (tenantId: number) => get<SeatsPage>(`/tenants/${tenantId}/seats`),
  signups: (limit: number, offset: number) =>
    get<SignupsPage>(`/signups?limit=${limit}&offset=${offset}`),
};
