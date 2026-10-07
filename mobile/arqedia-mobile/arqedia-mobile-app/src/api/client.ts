// STUBBED — no live API base URL, auth flow, or endpoint list exists in
// this project yet (identity_seats_spec_v1.md defines web/seat login only;
// no mobile-facing endpoints are documented). This file is the seam to
// wire later: swap the mock bodies below for real calls, keep the
// function signatures and types.

import { Memo, ShareGrant } from '@/types';

const MOCK_MEMOS: Memo[] = [
  {
    memo_id: 'memo_1',
    title: 'Meridian Capital — Q3 Diligence',
    memo_type: 'Credit memo',
    revision: 4,
    status: 'ready',
    generated_at: '2026-09-30T00:00:00Z',
    page_count: 17,
    file_size_bytes: 2_516_582,
  },
  {
    memo_id: 'memo_2',
    title: 'Harborline Logistics — Series B',
    memo_type: 'Investment memo',
    revision: 2,
    status: 'ready',
    generated_at: '2026-09-28T00:00:00Z',
    page_count: null,
    file_size_bytes: null,
  },
  {
    memo_id: 'memo_3',
    title: 'Dunemere Retail — Annual Review',
    memo_type: 'Credit memo',
    revision: 1,
    status: 'generating',
    generated_at: null,
    page_count: null,
    file_size_bytes: null,
  },
];

const MOCK_GRANTS: ShareGrant[] = [
  {
    grant_id: 'grant_1',
    tenant_id: 'tenant_1',
    memo_id: 'memo_2',
    viewer_account_id: 'viewer_1',
    viewer_email: 'j.reyes@harborline.com',
    sent_by_seat_id: 'seat_1',
    created_at: '2026-10-01T00:00:00Z',
    expires_at: '2026-10-31T00:00:00Z',
    expiry_set_by_tenant: false,
    revoked_at: null,
    revoked_by_seat_id: null,
    first_opened_at: '2026-10-02T00:00:00Z',
  },
];

function delay<T>(value: T, ms = 300): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

export const api = {
  listMemos(): Promise<Memo[]> {
    return delay(MOCK_MEMOS);
  },

  getMemo(memoId: string): Promise<Memo | undefined> {
    return delay(MOCK_MEMOS.find((m) => m.memo_id === memoId));
  },

  listRecentGrants(): Promise<ShareGrant[]> {
    return delay(MOCK_GRANTS);
  },

  sendShareGrant(input: {
    memo_id: string;
    recipient_email: string;
    note?: string;
  }): Promise<ShareGrant> {
    const grant: ShareGrant = {
      grant_id: `grant_${Date.now()}`,
      tenant_id: 'tenant_1',
      memo_id: input.memo_id,
      viewer_account_id: `viewer_${Date.now()}`,
      viewer_email: input.recipient_email,
      sent_by_seat_id: 'seat_1',
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 30 * 86400_000).toISOString(),
      expiry_set_by_tenant: false,
      revoked_at: null,
      revoked_by_seat_id: null,
      first_opened_at: null,
    };
    return delay(grant);
  },

  revokeGrant(grantId: string): Promise<void> {
    return delay(undefined);
  },
};
