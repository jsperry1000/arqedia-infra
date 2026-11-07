import React from 'react';
import { View, Text, Pressable, StyleSheet, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '@/theme/colors';
import { useSession } from '@/auth/session';
import { useWorkspace } from '@/workspace';
import { useWorkspaceGate } from '@/screens/WorkspaceGate';

// Who is signed in, which workspace the app is working in, and signing out.
// Everything else about an account - plan, seats, card, brand - stays on the
// web. Workspaces are chosen here, not made: setup is the web's.
export default function AccountScreen() {
  const { email, signOut } = useSession();
  const workspace = useWorkspace();
  const gate = useWorkspaceGate();

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Account</Text>
        <Text style={styles.subtitle}>{email}</Text>
      </View>
      <ScrollView contentContainerStyle={styles.body}>
        <View>
          <Text style={styles.sectionLabel}>Workspace</Text>
          {gate ?? workspace.workspaces.map((w) => {
            const on = w.workspace_id === workspace.active;
            return (
              <Pressable
                key={w.workspace_id}
                style={[styles.row, on && styles.rowOn]}
                onPress={() => workspace.choose(w.workspace_id)}
                accessibilityRole="radio"
                accessibilityState={{ checked: on }}
              >
                <Text style={[styles.rowText, on && styles.rowTextOn]} numberOfLines={1}>
                  {w.name}
                </Text>
                {on && <Text style={styles.tick}>✓</Text>}
              </Pressable>
            );
          })}
        </View>

        <Pressable style={styles.button} onPress={signOut}>
          <Text style={styles.buttonText}>Sign out</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: 20, paddingTop: 8, paddingBottom: 14 },
  title: { fontSize: 28, fontWeight: '700', color: colors.ink },
  subtitle: { fontSize: 14, color: colors.subtext, marginTop: 2 },
  body: { paddingHorizontal: 20, paddingBottom: 20, gap: 24 },
  sectionLabel: {
    fontSize: 12, fontWeight: '600', letterSpacing: 0.6, color: colors.muted,
    textTransform: 'uppercase', marginBottom: 8,
  },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface, borderRadius: 14, padding: 14, marginBottom: 8,
    borderWidth: 1, borderColor: colors.border,
  },
  rowOn: { borderColor: colors.deep, borderWidth: 1.5 },
  rowText: { flex: 1, fontSize: 15.5, color: colors.ink },
  rowTextOn: { fontWeight: '600' },
  tick: { fontSize: 16, fontWeight: '700', color: colors.deep },
  button: {
    height: 46,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: colors.mid,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: { color: colors.deep, fontSize: 15, fontWeight: '600' },
});
