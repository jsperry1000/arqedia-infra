import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { WorkspaceRef } from '@/types';

/**
 * Which workspace the app is working in. Follows ui/src/workspace.ts.
 *
 * THE ACTIVE ONE TRAVELS ON EVERY REQUEST, from call() in api/client.ts as
 * ?workspace=<id>. Held here, outside React, so one place adds it and no
 * screen has to remember to. Without it the server picks for itself: an
 * administrator gets whichever it resolves, and a member with several
 * workspaces is refused.
 *
 * REMEMBERED PER PHONE AND PER TENANT, in AsyncStorage. A remembered one no
 * longer in the list is dropped for the first.
 *
 * Chosen on the Account tab. Memos and Share name it in their headers and
 * read again when it changes.
 */

let active: number | null = null;

/** What call() adds to a request. */
export function activeWorkspace(): number | null {
  return active;
}

const KEY = 'arqedia.workspace.';

async function remember(tenant: string, id: number | null) {
  try {
    if (id === null) await AsyncStorage.removeItem(KEY + tenant);
    else await AsyncStorage.setItem(KEY + tenant, String(id));
  } catch { /* storage unreadable: this run only */ }
}

/** The one remembered for this tenant, where it is still one of theirs;
 *  otherwise the first. Null where they hold none. */
async function choose(tenant: string, held: WorkspaceRef[]): Promise<number | null> {
  if (held.length === 0) return null;
  let kept: number | null = null;
  try {
    const raw = await AsyncStorage.getItem(KEY + tenant);
    kept = raw === null ? null : Number(raw);
  } catch { /* nothing remembered */ }
  return held.some((w) => w.workspace_id === kept) ? kept : held[0].workspace_id;
}

export type WorkspaceState = {
  /** loading until GET /settings has answered; error where it refused. */
  status: 'loading' | 'ready' | 'error';
  error: string;
  workspaces: WorkspaceRef[];
  active: number | null;
  /** Bumped on every change of workspace, so a screen reads its own again. */
  epoch: number;
  choose: (id: number) => void;
  reload: () => void;
};

const WorkspaceContext = createContext<WorkspaceState | null>(null);

export function useWorkspace(): WorkspaceState {
  const state = useContext(WorkspaceContext);
  if (!state) throw new Error('useWorkspace outside WorkspaceProvider');
  return state;
}

/** The active workspace's name, or null where there is none to name. */
export function activeName(state: WorkspaceState): string | null {
  return state.workspaces.find((w) => w.workspace_id === state.active)?.name ?? null;
}

export function WorkspaceProvider({ tenant, read, children }: {
  tenant: string;
  /** GET /settings' workspaces: every one for an administrator, a member's
   *  own. Passed in so this module does not import the client that imports
   *  it. */
  read: () => Promise<WorkspaceRef[]>;
  children: React.ReactNode;
}) {
  const [status, setStatus] = useState<WorkspaceState['status']>('loading');
  const [error, setError] = useState('');
  const [workspaces, setWorkspaces] = useState<WorkspaceRef[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [epoch, setEpoch] = useState(0);

  const load = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      const held = await read();
      const id = await choose(tenant, held);
      active = id;
      await remember(tenant, id);
      setWorkspaces(held);
      setActiveId(id);
      setEpoch((n) => n + 1);
      setStatus('ready');
    } catch (err: any) {
      setError(err?.message || String(err));
      setStatus('error');
    }
  }, [tenant, read]);

  useEffect(() => {
    load();
    // Signing out unmounts this; the next person starts with nothing.
    return () => { active = null; };
  }, [load]);

  const value: WorkspaceState = {
    status,
    error,
    workspaces,
    active: activeId,
    epoch,
    choose: (id: number) => {
      if (id === activeId) return;
      active = id;
      remember(tenant, id);
      setActiveId(id);
      setEpoch((n) => n + 1);
    },
    reload: () => { load(); },
  };

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}
