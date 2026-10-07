// The API's own shapes, copied from ui/src/api.ts. The web app's types are
// the reference: when a field changes there, it changes here by hand. Nothing
// in this file is invented - a field the API does not send is not here.

export type Standing = 'trial' | 'trial_ended' | 'active' | 'purchased_only';

// ui/src/api.ts:246
export interface Engagement {
  engagement_id: number;
  engagement: string;
  documents: number;
  last_activity: string;
  /** The company the memoranda are about. Null until somebody names one. */
  subject_name: string | null;
  /** open or archived. */
  status: string;
  archived_by: string | null;
  archived_at: string | null;
}

// ui/src/api.ts:339
export interface MemoRef {
  memo_id: number;
  /** The template's key. */
  template: string;
  /** The template's name as it stood in the revision this memo was written
   *  against, not as it stands today. */
  template_label: string;
  generated_at: string;
  generated_by: string | null;
  parent_memo_id: number | null;
  revision: number;
  modified_by: string | null;
  modified_at: string | null;
  label: string;
  has_pdf: boolean;
  /** live or archived. */
  state: string;
  archived_by: string | null;
  archived_at: string | null;
}

// ui/src/api.ts:762
export interface ShareAllowance {
  plan: string;
  trial: boolean;
  standing: Standing;
  period: string;
  period_ends_at: string | null;
  /** Null is unlimited, never zero. */
  allowance: number | null;
  used: number;
  remaining: number | null;
  overage_event: string;
  /** What one share past the allowance costs. Null where it is not priced -
   *  and an unpriced share is refused, never sent for nothing. */
  overage_cents: number | null;
  today: number;
  daily_limit: number;
  /** No balance at all: sending is refused, revoking is not. */
  capped: boolean;
}

// ui/src/api.ts:784. The link token is never here: it went to the recipient
// alone.
export interface ShareGrant {
  grant_id: string;
  memo_id: number;
  memo_label: string;
  subject: string | null;
  recipient_email: string;
  sent_by: string;
  created_at: string;
  sent_at: string;
  expires_at: string;
  expiry_set_by_tenant: boolean;
  first_opened_at: string | null;
  opens: number;
  downloads: number;
  revoked: boolean;
  revoked_at: string | null;
  revoked_by: string | null;
  reinstated_at: string | null;
  charged_cents: number | null;
  expired: boolean;
  registered?: boolean;
}

// ui/src/api.ts:807
export interface ShareSent extends ShareGrant {
  /** Whether SES accepted the email. The share stands either way. */
  sent: boolean;
  reinstated: boolean;
  charged_cents: number;
}

// ui/src/api.ts:814
export interface ShareSend {
  recipient: string;
  /** Required, and true. */
  authority_affirmed: boolean;
  /** Null for the default two weeks; a number is a period the tenant chose. */
  expiry_days: number | null;
  idempotency_key: string;
  /** The overage price the person accepted, where the send is past the
   *  allowance. Anything else is refused with the price, not charged. */
  accept_overage_cents?: number | null;
}
