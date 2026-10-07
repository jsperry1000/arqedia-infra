import React, { useEffect, useState } from 'react';
import { View, Text, Pressable, StyleSheet, ScrollView, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { colors } from '@/theme/colors';
import { api } from '@/api/client';
import { Memo } from '@/types';
import { RootStackParamList } from '@/navigation/RootNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'MemoDetail'>;

export default function MemoDetailScreen({ route, navigation }: Props) {
  const [memo, setMemo] = useState<Memo | null>(null);

  useEffect(() => {
    api.getMemo(route.params.memoId).then((m) => setMemo(m ?? null));
  }, [route.params.memoId]);

  if (!memo) return null;

  // Download / open-in-viewer are not wired to a real file yet —
  // no PDF generation or storage endpoint is available to call here.
  const onDownload = () =>
    Alert.alert('Download PDF', 'Not wired to a live endpoint yet.');
  const onOpenViewer = () =>
    Alert.alert('Open in PDF viewer', 'Not wired to a live endpoint yet.');

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => navigation.goBack()} hitSlop={10}>
          <Text style={styles.back}>{'‹'}</Text>
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.title} numberOfLines={1}>
            {memo.title}
          </Text>
          <Text style={styles.subtitle}>
            {memo.memo_type} · rev. {memo.revision}
          </Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={styles.statusPill}>
            <Text style={styles.statusPillText}>
              {memo.status === 'ready' ? 'Ready' : 'Generating'}
            </Text>
          </View>
          {memo.generated_at && (
            <Text style={styles.meta}>
              Generated {new Date(memo.generated_at).toLocaleDateString()}
              {memo.page_count ? ` · ${memo.page_count} pages` : ''}
            </Text>
          )}
        </View>

        <View style={styles.card}>
          <Row label="File size" value={memo.file_size_bytes ? `${(memo.file_size_bytes / 1_000_000).toFixed(1)} MB` : '—'} />
          <Row label="Format" value="PDF" />
          <Row
            label="Status"
            value={memo.status === 'ready' ? 'Ready' : 'Generating'}
            last
          />
        </View>
      </ScrollView>

      <View style={styles.actionBar}>
        <Pressable style={styles.primaryBtn} onPress={onDownload}>
          <Text style={styles.primaryBtnText}>Download PDF</Text>
        </Pressable>
        <Pressable style={styles.secondaryBtn} onPress={onOpenViewer}>
          <Text style={styles.secondaryBtnText}>Open in PDF viewer</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

function Row({ label, value, last }: { label: string; value: string; last?: boolean }) {
  return (
    <View style={[styles.rowLine, !last && styles.rowLineBorder]}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
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
  statusPill: {
    backgroundColor: colors.light,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
  },
  statusPillText: { fontSize: 11.5, fontWeight: '600', color: colors.deep },
  meta: { fontSize: 12.5, color: colors.subtext },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
  },
  rowLine: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  rowLineBorder: { borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 13.5, color: colors.subtext },
  rowValue: { fontSize: 13.5, fontWeight: '600', color: colors.ink },
  actionBar: {
    padding: 20,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    gap: 10,
  },
  primaryBtn: {
    height: 50,
    borderRadius: 14,
    backgroundColor: colors.deep,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryBtnText: { color: colors.surface, fontSize: 16, fontWeight: '700' },
  secondaryBtn: {
    height: 46,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: colors.mid,
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryBtnText: { color: colors.deep, fontSize: 15, fontWeight: '600' },
});
