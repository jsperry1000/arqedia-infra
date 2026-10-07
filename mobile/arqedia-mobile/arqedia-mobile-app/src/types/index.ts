// Shapes below follow the fields named in share_viewer_spec_v1.md's data
// model where they exist. Fields with no corresponding spec field are
// marked PROPOSED — display-only guesses from the mockup, not schema.

export type MemoStatus = 'ready' | 'generating';

export interface Memo {
  memo_id: string;
  title: string; // PROPOSED — no "memo title" field is named in the spec
  memo_type: string; // PROPOSED — e.g. "Credit memo" / "Investment memo"
  revision: number; // PROPOSED
  status: MemoStatus; // PROPOSED — spec treats memos as immutable once rendered;
  // "generating" is a pipeline-stage guess, not a spec field
  generated_at: string | null; // ISO 8601; null while generating
  page_count: number | null; // PROPOSED — not in spec
  file_size_bytes: number | null; // PROPOSED — not in spec
}

// share_grant, per share_viewer_spec_v1.md §8
export interface ShareGrant {
  grant_id: string;
  tenant_id: string;
  memo_id: string;
  viewer_account_id: string;
  viewer_email: string; // denormalized for display; lives on viewer_account in the spec
  sent_by_seat_id: string;
  created_at: string;
  expires_at: string;
  expiry_set_by_tenant: boolean;
  revoked_at: string | null;
  revoked_by_seat_id: string | null;
  first_opened_at: string | null;
}
