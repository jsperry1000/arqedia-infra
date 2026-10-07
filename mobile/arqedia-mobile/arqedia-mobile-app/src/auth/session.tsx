import React, { createContext, useContext } from 'react';

// Whether somebody is signed in is Amplify's to know: it holds the tokens and
// refreshes them. This only lets a screen deep in the tree sign out and have
// the gate in App.tsx notice.
export interface Session {
  email: string;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<Session | null>(null);

export const SessionProvider = SessionContext.Provider;

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession outside SessionProvider');
  return session;
}

export default SessionContext;
