import React from 'react';
import { Text, Pressable, StyleSheet, View } from 'react-native';
import { colors } from '@/theme/colors';
import { useSession } from '@/auth/session';
import { useWorkspace } from '@/workspace';

/** What Memos and Share show in place of their content until there is a
 *  workspace to work in. Null once there is one.
 *
 *  An administrator with no workspace is sent to the web: setup is not
 *  offered here (decision of 7 November 2026). A member with none is told
 *  what the server would tell them (NO_WORKSPACE_ASSIGNED, lambda/api/app.py). */
export function useWorkspaceGate(): React.ReactElement | null {
  const { role } = useSession();
  const ws = useWorkspace();

  if (ws.status === 'ready' && ws.active !== null) return null;

  let text: string;
  if (ws.status === 'loading') text = 'Reading your workspaces…';
  else if (ws.status === 'error') text = ws.error;
  else if (role === 'admin') {
    text = 'There is no workspace yet. Set one up in ARQEDIA on the web, '
      + 'then come back here.';
  } else {
    text = 'No workspace is assigned to you yet. Ask an administrator to add '
      + 'you to one on the seats screen.';
  }

  return (
    <View style={styles.wrap}>
      <Text style={styles.message}>{text}</Text>
      {ws.status !== 'loading' && (
        <Pressable onPress={ws.reload} hitSlop={6}>
          <Text style={styles.retry}>Try again</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingHorizontal: 20, gap: 10 },
  message: { fontSize: 14, color: colors.subtext, lineHeight: 20 },
  retry: { fontSize: 14, fontWeight: '600', color: colors.mid },
});
