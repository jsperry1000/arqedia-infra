import React, { useEffect, useState } from 'react';
import { View, Text, Pressable, StyleSheet, TextInput, ScrollView, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '@/theme/colors';
import { api } from '@/api/client';
import { Memo, ShareGrant } from '@/types';

export default function ShareScreen() {
  const [memos, setMemos] = useState<Memo[]>([]);
  const [grants, setGrants] = useState<ShareGrant[]>([]);
  const [selectedMemoId, setSelectedMemoId] = useState<string | null>(null);
  const [recipient, setRecipient] = useState('');
  const [note, setNote] = useState('');

  useEffect(() => {
    api.listMemos().then((m) => {
      setMemos(m);
      setSelectedMemoId(m[0]?.memo_id ?? null);
    });
    api.listRecentGrants().then(setGrants);
  }, []);

  const onSend = async () => {
    if (!selectedMemoId || !recipient) return;
    const grant = await api.sendShareGrant({
      memo_id: selectedMemoId,
      recipient_email: recipient,
      note: note || undefined,
    });
    setGrants((g) => [grant, ...g]);
    setRecipient('');
    setNote('');
  };

  const onRevoke = async (grantId: string) => {
    await api.revokeGrant(grantId);
    setGrants((g) =>
      g.map((x) => (x.grant_id === grantId ? { ...x, revoked_at: new Date().toISOString() } : x))
    );
  };

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Share</Text>
        <Text style={styles.subtitle}>Send a memo to someone, right now</Text>
      </View>

      <ScrollView contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: 12, gap: 18 }}>
        <View>
          <Text style={styles.sectionLabel}>Memo to share</Text>
          {memos.map((m) => {
            const selected = m.memo_id === selectedMemoId;
            return (
              <Pressable
                key={m.memo_id}
                onPress={() => setSelectedMemoId(m.memo_id)}
                style={[
                  styles.memoPick,
                  { borderColor: selected ? colors.deep : colors.border, borderWidth: selected ? 1.5 : 1 },
                ]}
              >
                <View style={[styles.memoIcon, { backgroundColor: selected ? colors.light : colors.shade }]} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.memoTitle} numberOfLines={1}>{m.title}</Text>
                  <Text style={styles.memoSubtitle}>{m.memo_type} · rev. {m.revision}</Text>
                </View>
              </Pressable>
            );
          })}
        </View>

        <View>
          <Text style={styles.sectionLabel}>Send to</Text>
          <View style={styles.formCard}>
            <TextInput
              style={styles.input}
              placeholder="Recipient's email"
              placeholderTextColor={colors.muted}
              value={recipient}
              onChangeText={setRecipient}
              autoCapitalize="none"
              keyboardType="email-address"
            />
            <View style={styles.divider} />
            <TextInput
              style={styles.input}
              placeholder="Add a note (optional)"
              placeholderTextColor={colors.muted}
              value={note}
              onChangeText={setNote}
            />
          </View>
        </View>

        <View>
          <Text style={styles.sectionLabel}>Recently sent</Text>
          {grants.map((g) => (
            <View key={g.grant_id} style={styles.grantRow}>
              <View style={styles.avatar}>
                <Text style={styles.avatarText}>
                  {g.viewer_email.slice(0, 2).toUpperCase()}
                </Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.grantText} numberOfLines={1}>
                  <Text style={{ fontWeight: '600' }}>{g.viewer_email}</Text>
                  {'  '}
                  {memos.find((m) => m.memo_id === g.memo_id)?.title ?? g.memo_id}
                </Text>
              </View>
              <View style={{ alignItems: 'flex-end', gap: 3 }}>
                <Text style={[styles.grantStatus, g.revoked_at && { color: colors.muted }]}>
                  {g.revoked_at ? 'Revoked' : g.first_opened_at ? 'Viewed' : 'Sent'}
                </Text>
                {!g.revoked_at && (
                  <Pressable onPress={() => onRevoke(g.grant_id)} hitSlop={8}>
                    <Text style={styles.revokeText}>Revoke</Text>
                  </Pressable>
                )}
              </View>
            </View>
          ))}
        </View>
      </ScrollView>

      <View style={styles.sendBar}>
        <Pressable
          style={[styles.sendBtn, (!selectedMemoId || !recipient) && { opacity: 0.5 }]}
          disabled={!selectedMemoId || !recipient}
          onPress={onSend}
        >
          <Text style={styles.sendBtnText}>Send</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: 20, paddingTop: 8, paddingBottom: 14 },
  title: { fontSize: 28, fontWeight: '700', color: colors.ink },
  subtitle: { fontSize: 14, color: colors.subtext, marginTop: 2 },
  sectionLabel: {
    fontSize: 12, fontWeight: '600', letterSpacing: 0.6, color: colors.muted,
    textTransform: 'uppercase', marginBottom: 8,
  },
  memoPick: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface, borderRadius: 14, padding: 12, marginBottom: 8,
  },
  memoIcon: { width: 36, height: 36, borderRadius: 9 },
  memoTitle: { fontSize: 14, fontWeight: '600', color: colors.ink },
  memoSubtitle: { fontSize: 12, color: colors.subtext, marginTop: 1 },
  formCard: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 12,
  },
  input: { paddingHorizontal: 14, paddingVertical: 12, fontSize: 15, color: colors.ink },
  divider: { height: 1, backgroundColor: colors.border, marginHorizontal: 14 },
  grantRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10 },
  avatar: {
    width: 30, height: 30, borderRadius: 999, backgroundColor: colors.light,
    alignItems: 'center', justifyContent: 'center',
  },
  avatarText: { fontSize: 12, fontWeight: '700', color: colors.deep },
  grantText: { fontSize: 13.5, color: colors.ink },
  grantStatus: { fontSize: 11, fontWeight: '600', color: colors.mid },
  revokeText: { fontSize: 11, fontWeight: '600', color: colors.ink },
  sendBar: {
    padding: 20, paddingTop: 12, borderTopWidth: 1, borderTopColor: colors.border,
  },
  sendBtn: {
    height: 50, borderRadius: 14, backgroundColor: colors.deep,
    alignItems: 'center', justifyContent: 'center',
  },
  sendBtnText: { color: colors.surface, fontSize: 16, fontWeight: '700' },
});
