import { fetchAuthSession } from "aws-amplify/auth";
import { config } from "./config";

// Every request carries the token. The tenant travels inside it, signed:
// nothing here says which tenant we are, and nothing here could.
async function authHeaders(): Promise<Record<string, string>> {
  const session = await fetchAuthSession();
  const token = session.tokens?.idToken?.toString();
  if (!token) throw new Error("not signed in");
  return { Authorization: token, "content-type": "application/json" };
}

async function call(path: string, init: RequestInit = {}) {
  const headers = await authHeaders();
  const res = await fetch(config.apiUrl + path, { ...init, headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export type Engagement = {
  engagement: string;
  documents: number;
  last_activity: string;
};

export type Pending = {
  document_id: number;
  filename: string;
  proposed_type: string | null;
  pages: number | null;
  thin_text: boolean;
  chars: number | null;
  confidence: string | null;
  why: string | null;
  state: string;
  uploaded_by: string | null;
};

export type Doc = {
  document_id: number;
  filename: string;
  document_type: string | null;
  pages: number | null;
  method: string | null;
  filed_at: string;
  uploaded_by: string | null;
  active: boolean;
  state: string;
  deactivated_by: string | null;
  deactivated_at: string | null;
  extracted_at: string | null;
  values: number;
};

export type DocType = {
  key: string;
  label: string;
  category: string;
  description: string;
  read_mode: string;
  always_ocr: boolean;
};

export type Decision = {
  document_id: number;
  document_type: string | null;
  include: boolean;
};

export type MemoRef = {
  memo_id: number;
  template: string;
  generated_at: string;
  generated_by: string | null;
  parent_memo_id: number | null;
  revision: number;
  modified_by: string | null;
  modified_at: string | null;
  label: string;
  has_pdf: boolean;
};

export type Memo = {
  memo_id: number;
  generated_at: string;
  generated_by: string | null;
  parent_memo_id: number | null;
  revision: number;
  label: string;
  modified_by: string | null;
  modified_at: string | null;
  markdown: string;
  sources: { document_id: number; filename: string }[];
};

export type Passage = {
  document_id: number;
  filename: string;
  unit: number | null;
  unit_kind: string;
  unit_label: string | null;
  pages: number | null;
  text: string;
  source_url: string;
};

export type ExtractedValue = {
  field_id: string;
  label: string;
  value: string | null;
  locator_kind: string | null;
  locator_index: number | null;
  row: number;
};

export type DocumentDetail = {
  document_id: number;
  filename: string;
  document_type: string | null;
  pages: number | null;
  method: string | null;
  values: ExtractedValue[];
  missing: { field_id: string; label: string }[];
  expected: number;
};

export type Settings = {
  name: string;
  plan: string;
  may_brand: boolean;
  may_remove_footer: boolean;
  logo_key: string | null;
  logo_url: string | null;
  deep: string | null;
  mid: string | null;
  highlight: string | null;
};

export type ConfigSection = {
  key: string;
  numeral: string;
  title: string;
  kind: string;
  prompt: string | null;
  template_key: string;
  fields: string[];
};

export type ConfigColumn = {
  key: string;
  label: string;
  type: string;
  description: string | null;
};

export type ConfigField = {
  key: string;
  label: string;
  type: string;
  cardinality: string;
  description: string | null;
  is_group: boolean;
  columns: ConfigColumn[];
  found_in: string[];
};

export type ConfigDocumentType = {
  key: string;
  label: string;
  category: string;
  description: string;
  read_mode: string;
  always_ocr: boolean;
};

export type ConfigCategory = { key: string; label: string };

export type Draft = {
  sections: ConfigSection[];
  fields: ConfigField[];
  document_types: ConfigDocumentType[];
  categories: ConfigCategory[];
};

export type ConfigState = {
  active_revision: number;
  revisions: {
    revision: number; status: string; note: string | null;
    published_at: string | null; published_by: string | null;
  }[];
  draft: { revision: number; created_at: string; created_by: string } | null;
  validation?: Validation;
};

export type Validation = {
  revision: number;
  may_publish: boolean;
  fatal: { kind: string; detail: string }[];
  warnings: { kind: string; detail: string }[];
};

export type Pack = {
  revision: number;
  note: string | null;
  document_types: number;
  fields: number;
};

export const api = {
  // --- configuration -------------------------------------------------

  configState: (): Promise<ConfigState> => call("/config"),

  packs: (): Promise<{ packs: Pack[] }> => call("/config/packs"),

  forkPack: (revision: number) =>
    call("/config/fork", {
      method: "POST",
      body: JSON.stringify({ revision }),
    }),

  openDraft: () =>
    call("/config/draft", { method: "POST", body: "{}" }),

  discardDraft: () => call("/config/draft", { method: "DELETE" }),

  draft: (): Promise<Draft> => call("/config/draft"),

  validateDraft: (): Promise<Validation> => call("/config/draft/validate"),

  publish: (note: string) =>
    call("/config/publish", {
      method: "POST",
      body: JSON.stringify({ note }),
    }),

  saveSection: (body: Partial<ConfigSection>) =>
    call("/config/draft/sections", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteSection: (key: string) =>
    call(`/config/draft/sections/${encodeURIComponent(key)}`,
         { method: "DELETE" }),

  setSectionFields: (key: string, fields: string[]) =>
    call(`/config/draft/sections/${encodeURIComponent(key)}/fields`, {
      method: "PUT",
      body: JSON.stringify({ fields }),
    }),

  saveField: (body: Partial<ConfigField>) =>
    call("/config/draft/fields", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteField: (key: string) =>
    call(`/config/draft/fields/${encodeURIComponent(key)}`,
         { method: "DELETE" }),

  setFieldDocuments: (key: string, documents: string[]) =>
    call(`/config/draft/fields/${encodeURIComponent(key)}/documents`, {
      method: "PUT",
      body: JSON.stringify({ documents }),
    }),

  // The same relationship as setFieldDocuments, from the other end. Sent as
  // one list rather than a call per field, so the grouping is rebuilt once.
  setDocumentFields: (key: string, fields: string[]) =>
    call(`/config/draft/types/${encodeURIComponent(key)}/fields`, {
      method: "PUT",
      body: JSON.stringify({ fields }),
    }),

  saveDocumentType: (body: Partial<ConfigDocumentType>) =>
    call("/config/draft/types", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteDocumentType: (key: string) =>
    call(`/config/draft/types/${encodeURIComponent(key)}`,
         { method: "DELETE" }),

  saveCategory: (body: Partial<ConfigCategory>) =>
    call("/config/draft/categories", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteCategory: (key: string) =>
    call(`/config/draft/categories/${encodeURIComponent(key)}`,
         { method: "DELETE" }),

  settings: (): Promise<Settings> => call("/settings"),

  saveSettings: (body: Partial<Record<"deep" | "mid" | "highlight" | "logo_key", string | null>>):
    Promise<Settings> =>
    call("/settings", { method: "POST", body: JSON.stringify(body) }),

  // Two steps, as documents use: ask for a signed link, send the file
  // straight to storage, then record the key. The key is recorded only after
  // the upload succeeds, so a failure cannot leave the tenant pointing at a
  // logo that is not there.
  previewBranding: (): Promise<{ url: string; plan: string }> =>
    call("/settings/preview"),

  uploadLogo: async (file: File): Promise<Settings> => {
    const { url, key } = await call("/settings/logo", {
      method: "POST",
      body: JSON.stringify({ content_type: file.type }),
    });
    const put = await fetch(url, {
      method: "PUT",
      body: file,
      headers: { "content-type": file.type },
    });
    if (!put.ok) throw new Error("upload failed");
    return call("/settings/logo/confirm", {
      method: "POST",
      body: JSON.stringify({ key }),
    });
  },

  documentTypes: (): Promise<{ types: DocType[] }> => call("/document-types"),

  engagements: (): Promise<{ engagements: Engagement[] }> =>
    call("/engagements"),

  pending: (id: string): Promise<{ pending: Pending[] }> =>
    call(`/engagements/${encodeURIComponent(id)}/pending`),

  file: (id: string, decisions: Decision[]) =>
    call(`/engagements/${encodeURIComponent(id)}/file`, {
      method: "POST",
      body: JSON.stringify({ decisions }),
    }),

  documents: (id: string): Promise<{ documents: Doc[] }> =>
    call(`/engagements/${encodeURIComponent(id)}/documents`),

  setActive: (documentId: number, active: boolean) =>
    call(`/documents/${documentId}/active`, {
      method: "POST",
      body: JSON.stringify({ active }),
    }),

  documentValues: (documentId: number): Promise<DocumentDetail> =>
    call(`/documents/${documentId}/values`),

  memos: (id: string): Promise<{ memos: MemoRef[] }> =>
    call(`/engagements/${encodeURIComponent(id)}/memos`),

  generate: (id: string) =>
    call(`/engagements/${encodeURIComponent(id)}/generate`, { method: "POST" }),

  memo: (memoId: number): Promise<Memo> => call(`/memos/${memoId}`),

  revise: (memoId: number, markdown: string): Promise<{
    memo_id: number; parent_memo_id: number; revision: number; label: string;
  }> =>
    call(`/memos/${memoId}/revise`, {
      method: "POST",
      body: JSON.stringify({ markdown }),
    }),

  // The PDF is rendered when asked for, not stored. A rendering improvement
  // therefore reaches every memo rather than only the next one written.
  memoPdf: (memoId: number): Promise<{ url: string; bytes: number }> =>
    call(`/memos/${memoId}/pdf`),

  passage: (documentId: number, unit: number | null): Promise<Passage> =>
    call(`/documents/${documentId}/passage`
      + (unit ? `?unit=${unit}` : "")),

  // Two steps: ask for a signed link, then send the file straight to S3.
  // The file never passes through our servers.
  //
  // Every header the link was signed with must be sent back, or S3 refuses
  // the request. The uploader's email is one of them: the API knows who is
  // asking and the normalizer does not, so it travels with the object.
  upload: async (engagement: string, file: File) => {
    const { url, uploaded_by } = await call("/uploads", {
      method: "POST",
      body: JSON.stringify({ engagement, filename: file.name }),
    });

    const put = await fetch(url, {
      method: "PUT",
      body: file,
      headers: {
        "x-amz-server-side-encryption": "aws:kms",
        "x-amz-meta-uploaded-by": uploaded_by,
      },
    });

    if (!put.ok) {
      throw new Error(
        `${file.name} was refused by storage (${put.status}).`);
    }
  },
};
