import React, { useCallback, useEffect, useState } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Amplify } from 'aws-amplify';
import { fetchUserAttributes, getCurrentUser, signOut } from 'aws-amplify/auth';
import { config } from '@/config';
import { colors } from '@/theme/colors';
import { SessionProvider, type Session } from '@/auth/session';
import SignInScreen from '@/auth/SignInScreen';
import RootNavigator from '@/navigation/RootNavigator';

// Amplify keeps the tokens in its own storage (AsyncStorage, through
// @aws-amplify/react-native) and refreshes them; nothing here stores one.
Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: config.userPoolId,
      userPoolClientId: config.userPoolClientId,
    },
  },
});

export default function App() {
  // undefined while Amplify is asked; null when nobody is signed in.
  const [session, setSession] = useState<Session | null | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      await getCurrentUser();
      const attrs = await fetchUserAttributes();
      setSession({
        email: attrs.email ?? '',
        signOut: async () => {
          await signOut();
          setSession(null);
        },
      });
    } catch {
      setSession(null);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      {session === undefined ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center',
                       backgroundColor: colors.background }}>
          <ActivityIndicator color={colors.deep} />
        </View>
      ) : session === null ? (
        <SignInScreen onSignedIn={load} />
      ) : (
        <SessionProvider value={session}>
          <RootNavigator />
        </SessionProvider>
      )}
    </SafeAreaProvider>
  );
}
