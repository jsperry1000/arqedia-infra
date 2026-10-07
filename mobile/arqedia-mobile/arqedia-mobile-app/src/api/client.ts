// The live API, called the way ui/src/api.ts calls it: the Cognito ID token
// as a bare Authorization header, no "Bearer". The tenant travels inside the
// token; nothing here says which tenant this is.

import { fetchAuthSession } from 'aws-amplify/auth';
import { randomUUID } from 'expo-crypto';
import { config } from '@/config';
import {
  Engagement, MemoRef, ShareAllowance, ShareGrant, ShareSend, ShareSent,
} from '@/types';

/** A refusal, carrying the status and the server's sentence. The handler
 *  answers a refusal as {"error": "..."}, written to be shown as it stands. */
export class ApiError extends Error {
  readonly status: number;
  readonly body: Record<string, unknown>;

  constructor(status: number, text: string) {
    let body: Record<string, unknown> = {};
    try {
      body = JSON.parse(text);
    } catch { /* not JSON; the text is the message */ }
    super(typeof body.error === 'string' ? body.error : text);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

/** Past the allowance, and the price was not accepted - or a different one
 *  was. Nothing was sent or charged. The price travels so the screen can put
 *  it to the person; it is never accepted for them. */
export class OverageRequired extends ApiError {
  readonly overageCents: number;

  constructor(text: string, overageCents: number) {
    super(409, text);
    this.name = 'OverageRequired';
    this.overageCents = overageCents;
  }
}

/** No balance at all. Sending is refused; revoking still works. */
export class Capped extends ApiError {
  constructor(text: string) {
    super(402, text);
    this.name = 'Capped';
  }
}

/** One click, one key: minted when the person presses Send, so a retry of
 *  the same press is answered rather than charged twice. */
export function chargeKey(): string {
  return randomUUID();
}

async function authHeaders(): Promise<Record<string, string>> {
  const session = await fetchAuthSession();
  const token = session.tokens?.idToken?.toString();
  if (!token) throw new Error('not signed in');
  return { Authorization: token, 'content-type': 'application/json' };
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(config.apiUrl + path, { ...init, headers });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}

export const api = {
  engagements(): Promise<{ engagements: Engagement[] }> {
    return call('/engagements');
  },

  /** BY NAME, NOT ID. The route's {id} is the engagement's name: the handler
   *  looks it up with engagement_named (lambda/api/app.py), as the web app
   *  calls it. An engagement_id here is read as a name and refused with
   *  "no engagement called 17". */
  memos(engagementName: string): Promise<{ memos: MemoRef[] }> {
    return call(`/engagements/${encodeURIComponent(engagementName)}/memos`);
  },

  /** The PDF is rendered when asked for, not stored. */
  memoPdf(memoId: number): Promise<{ url: string; bytes: number }> {
    return call(`/memos/${memoId}/pdf`);
  },

  /** Every share this workspace has sent, newest first, and the allowance. */
  shares(): Promise<{ grants: ShareGrant[]; allowance: ShareAllowance }> {
    return call('/shares');
  },

  /** Send a memorandum, or send it again. A 409 is OverageRequired and a 402
   *  is Capped; both mean nothing was sent or charged. */
  async sendShare(memoId: number, body: ShareSend): Promise<ShareSent> {
    try {
      return await call(`/memos/${memoId}/shares`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409
          && typeof err.body.overage_cents === 'number') {
        throw new OverageRequired(JSON.stringify(err.body), err.body.overage_cents);
      }
      if (err instanceof ApiError && err.status === 402) {
        throw new Capped(JSON.stringify(err.body));
      }
      throw err;
    }
  },

  /** End future access. It cannot recall a copy already downloaded. */
  revokeShare(grantId: string): Promise<ShareGrant> {
    return call(`/shares/${encodeURIComponent(grantId)}/revoke`, { method: 'POST' });
  },
};
