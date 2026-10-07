import React, { useEffect, useState } from 'react';
import { View, Text, FlatList, Pressable, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { colors } from '@/theme/colors';
import { api } from '@/api/client';
import { MemoRef } from '@/types';
import { RootStackParamList } from '@/navigation/RootNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'EngagementMemos'>;

// One engagement's live memos, newest line first and each line's revisions
// newest first - the order GET /engagements/{id}/memos returns them in.
export default function EngagementMemosScreen({ route, navigation }: Props) {
  const { engagement } = route.params;
  const [memos, setMemos] = useState<MemoRef[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.memos(engagement.engagement_id)
      .then((r) => setMemos(r.memos))
      .catch((err) => setError(err?.message || String(err)));
  }, [engagement.engagement_id]);

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => navigation.goBack()} hitSlop={10}>
          <Text style={styles.back}>{'‹'}</Text>
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.title} numberOfLines={1}>{engagement.engagement}</Text>
          {!!engagement.subject_name && (
            <Text style={styles.subtitle} numberOfLines={1}>{engagement.subject_name}</Text>
          )}
        </View>
      </View>

      {!!error && <Text style={styles.message}>{error}</Text>}
      {memos === null && !error && <Text style={styles.message}>Loading…</Text>}
      {memos !== null && memos.length === 0 && (
        <Text style={styles.message}>No memos in this engagement yet.</Text>
      )}

      <FlatList
        data={memos ?? []}
        keyExtractor={(item) => String(item.memo_id)}
        contentContainerStyle={{ paddingHorizontal: 12, paddingBottom: 12 }}
        renderItem={({ item }) => (
          <Pressable
            style={styles.row}
            onPress={() => navigation.navigate('MemoDetail', {
              memo: item, engagement: engagement.engagement,
            })}
          >
            <View style={styles.iconCircle} />
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle} numberOfLines={1}>{item.template_label}</Text>
              <Text style={styles.rowSubtitle} numberOfLines={1}>
                Memo {item.label} · {new Date(item.generated_at).toLocaleDateString()}
              </Text>
            </View>
            <Text style={styles.chevron}>{'›'}</Text>
          </Pressable>
        )}
      />
    </SafeAreaView>
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
  message: { paddingHorizontal: 20, paddingBottom: 8, fontSize: 14, color: colors.subtext },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 14,
    marginHorizontal: 8,
    marginBottom: 2,
    borderRadius: 14,
  },
  iconCircle: { width: 42, height: 42, borderRadius: 10, backgroundColor: colors.light },
  rowTitle: { fontSize: 15.5, fontWeight: '600', color: colors.ink },
  rowSubtitle: { fontSize: 13, color: colors.subtext, marginTop: 2 },
  chevron: { fontSize: 22, color: colors.muted },
});
