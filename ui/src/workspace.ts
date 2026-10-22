import { createContext, useContext } from "react";

/**
 * Which workspace the application is working in (PACK-01).
 *
 * A tenant's configuration is held in workspaces - Trade Finance, Real Estate
 * - each with its own document types, facts, memoranda and revisions. One is
 * active at a time, app-wide: Configure, uploading, the engagements, their
 * documents and their memoranda all follow it (decision of 22 October 2026).
 *
 * THE ACTIVE ONE TRAVELS ON EVERY REQUEST, from call() in api.ts as
 * ?workspace=<id>. Held here, outside React, so that one place adds it and no
 * screen has to remember to. The server checks it against the token's tenant
 * and answers with that workspace's rows only; a route with no use for it
 * ignores it.
 *
 * REMEMBERED PER BROWSER AND PER TENANT, so a person who works in Real Estate
 * comes back to Real Estate. Unreadable storage (a private window) is not an
 * error: the first workspace is chosen, visibly, in the header.
 *
 * Null until the shell has read the tenant's workspaces, and null for a
 * tenant with none yet: nothing is sent, and the server answers for "no
 * workspace", which is where a new tenant's Get started begins.
 */

export type WorkspaceRef = { workspace_id: number; name: string };

let active: number | null = null;
const listeners = new Set<() => void>();

/** What call() adds to a request. */
export function activeWorkspace(): number | null {
  return active;
}

const KEY = "arqedia.workspace.";

export function setActiveWorkspace(tenant: string, id: number | null) {
  active = id;
  try {
    if (id === null) localStorage.removeItem(KEY + tenant);
    else localStorage.setItem(KEY + tenant, String(id));
  } catch { /* a private window: this page only */ }
}

/** The one remembered for this tenant, where it is still one of theirs;
 *  otherwise the first. Null where the tenant holds none. */
export function chooseWorkspace(tenant: string,
                                held: WorkspaceRef[]): number | null {
  if (held.length === 0) return null;
  let kept: number | null = null;
  try {
    const raw = localStorage.getItem(KEY + tenant);
    kept = raw === null ? null : Number(raw);
  } catch { /* nothing remembered */ }
  return held.some((w) => w.workspace_id === kept)
    ? kept : held[0].workspace_id;
}

/** Something made a workspace - Get started's fork, or Add workspace. The
 *  shell reads the list again and the selector shows it. */
export function workspacesChanged() {
  listeners.forEach((fn) => fn());
}

export function onWorkspacesChanged(fn: () => void) {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

/** What a screen needs to say which workspace it is showing, and to change
 *  it. Provided by the shell. */
export type WorkspaceState = {
  workspaces: WorkspaceRef[];
  active: number | null;
  choose: (id: number) => void;
  /** Make a just-forked workspace the active one, before the list that
   *  names it has been read again. */
  adopt: (id: number) => void;
};

export const WorkspaceContext = createContext<WorkspaceState>({
  workspaces: [], active: null, choose: () => undefined,
  adopt: () => undefined,
});

export function useWorkspace() {
  return useContext(WorkspaceContext);
}

/** The active workspace's name, or null where there is none to name. */
export function activeName(state: WorkspaceState): string | null {
  return state.workspaces.find((w) => w.workspace_id === state.active)?.name
    ?? null;
}
