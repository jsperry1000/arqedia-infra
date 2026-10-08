import React from 'react';
import { View, Text, Pressable, StyleSheet, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { colors } from '@/theme/colors';
import { RootStackParamList } from '@/navigation/RootNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'GrantDetail'>;

const day = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString() : '—');
const money = (cents: number) => `$${(cents / 100).toFixed(2)}`;

// One share, as GET /shares already returned it - read only. Revoking stays
// on the list, beside the row.
export default function GrantDetailScreen({ route, navigation }: Props) {
  const { grant: g } = route.params;
  const status = g.revoked ? 'Revoked' : g.expired ? 'Expired' : g.first_opened_at ? 'Viewed' : 'Sent';

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => navigation.goBack()} hitSlop={10}>
          <Text style={styles.back}>{'‹'}</Text>
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.title} numberOfLines={1}>{g.recipient_email}</Text>
          <Text style={styles.subtitle} numberOfLines={1}>Memo {g.memo_label} · {status}</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
        <View style={styles.card}>
          <Row label="Recipient" value={g.recipient_email} />
          <Row label="Memo" value={g.memo_label} />
          {!!g.subject && <Row label="Subject" value={g.subject} />}
          <Row label="Sent by" value={g.sent_by} />
          <Row label="Sent" value={day(g.sent_at)} />
          <Row label="Access ends" value={day(g.expires_at)} />
          <Row label="Period" value={g.expiry_set_by_tenant ? 'Fixed when sent' : 'Default'} last />
        </View>

        <View style={styles.card}>
          <Row label="Status" value={status} />
          <Row label="First opened" value={day(g.first_opened_at)} />
          <Row label="Opens" value={String(g.opens)} />
          <Row label="Downloads" value={String(g.downloads)} />
          {g.registered !== undefined && (
            <Row label="Registered" value={g.registered ? 'Yes' : 'No'} />
          )}
          <Row label="Expired" value={g.expired ? 'Yes' : 'No'} />
          <Row label="Revoked" value={g.revoked ? `${day(g.revoked_at)}${g.revoked_by ? ` by ${g.revoked_by}` : ''}` : 'No'} />
          {!!g.reinstated_at && <Row label="Reinstated" value={day(g.reinstated_at)} />}
          <Row label="Charged" value={g.charged_cents ? money(g.charged_cents) : 'Nothing'} last />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({ label, value, last }: { label: string; value: string; last?: boolean }) {
  return (
    <View style={[styles.rowLine, !last && styles.rowLineBorder]}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue} numberOfLines={2}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 12,
  },
  back: { fontSize: 28, color: colors.ink, width: 32, textAlign: 'center' },
  title: { fontSize: 17, fontWeight: '700', color: colors.ink },
  subtitle: { fontSize: 12.5, color: colors.subtext, marginTop: 1 },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
  },
  rowLine: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  rowLineBorder: { borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 13.5, color: colors.subtext },
  rowValue: { flexShrink: 1, textAlign: 'right', fontSize: 13.5, fontWeight: '600', color: colors.ink },
});
