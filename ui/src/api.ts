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

export type Doc = {
  document_id: number;
  filename: string;
  document_type: string | null;
  pages: number | null;
  method: string | null;
  filed_at: string;
  values: number;
};

export type MemoRef = {
  memo_id: number;
  template: string;
  generated_at: string;
};

export const api = {
  engagements: (): Promise<{ engagements: Engagement[] }> =>
    call("/engagements"),

  documents: (id: string): Promise<{ documents: Doc[] }> =>
    call(`/engagements/${encodeURIComponent(id)}/documents`),

  memos: (id: string): Promise<{ memos: MemoRef[] }> =>
    call(`/engagements/${encodeURIComponent(id)}/memos`),

  generate: (id: string) =>
    call(`/engagements/${encodeURIComponent(id)}/generate`, { method: "POST" }),

  memo: (memoId: number): Promise<{ markdown: string; generated_at: string }> =>
    call(`/memos/${memoId}`),

  // Two steps: ask for a signed link, then send the file straight to S3.
  // The file never passes through our servers.
  upload: async (engagement: string, file: File) => {
    const { url } = await call("/uploads", {
      method: "POST",
      body: JSON.stringify({ engagement, filename: file.name }),
    });
    const put = await fetch(url, {
      method: "PUT",
      body: file,
      headers: { "x-amz-server-side-encryption": "aws:kms" },
    });
    if (!put.ok) throw new Error("upload failed");
  },
};
