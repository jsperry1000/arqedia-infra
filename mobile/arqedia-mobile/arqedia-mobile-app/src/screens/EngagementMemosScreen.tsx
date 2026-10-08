import React, { useEffect, useState } from 'react';
import { View, Text, FlatList, Pressable, StyleSheet, Alert, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { colors } from '@/theme/colors';
import { api } from '@/api/client';
import { MemoRef } from '@/types';
import { RootStackParamList } from '@/navigation/RootNavigator';

type Props = NativeStackScreenProps<RootStackParamList, 'EngagementMemos'>;

// One engagement's live memos, ordered by when each was generated - newest
// or oldest first, as the person chooses - and filtered by what they type.
export default function EngagementMemosScreen({ route, navigation }: Props) {
  const { engagement } = route.params;
  const [memos, setMemos] = useState<MemoRef[] | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [newestFirst, setNewestFirst] = useState(true);

  // A short list, so a text match and a date order are enough. The match is
  // on the label (12.3) and on the title.
  const q = query.trim().toLowerCase();
  const shown = (memos ?? [])
    .filter((m) => !q || m.label.toLowerCase().includes(q)
      || m.template_label.toLowerCase().includes(q))
    .sort((a, b) => {
      const d = new Date(a.generated_at).getTime() - new Date(b.generated_at).getTime();
      return newestFirst ? -d : d;
    });

  useEffect(() => {
    api.memos(engagement.engagement)
      .then((r) => setMemos(r.memos))
      .catch((err) => setError(err?.message || String(err)));
  }, [engagement.engagement]);

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

      <View style={styles.filterBar}>
        <TextInput
          style={styles.search}
          placeholder="Filter by label or title"
          placeholderTextColor={colors.muted}
          value={query}
          onChangeText={setQuery}
          autoCapitalize="none"
        />
        <Pressable style={styles.sort} onPress={() => setNewestFirst(!newestFirst)} hitSlop={4}>
          <Text style={styles.sortText}>{newestFirst ? 'Newest first' : 'Oldest first'}</Text>
        </Pressable>
      </View>

      {!!error && <Text style={styles.message}>{error}</Text>}
      {memos === null && !error && <Text style={styles.message}>Loading…</Text>}
      {memos !== null && memos.length === 0 && (
        <Text style={styles.message}>No memos in this engagement yet.</Text>
      )}
      {memos !== null && memos.length > 0 && shown.length === 0 && (
        <Text style={styles.message}>No memo matches “{query.trim()}”.</Text>
      )}

      <FlatList
        data={shown}
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
              {/* The title is cut to one line. Tapping it - not the row,
                  which opens the memo - shows the whole of it. */}
              <Pressable
                onPress={() => Alert.alert(item.template_label, `Memo ${item.label}`)}
                hitSlop={4}
              >
                <Text style={styles.rowTitle} numberOfLines={1}>{item.template_label}</Text>
              </Pressable>
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
  filterBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 20,
    paddingBottom: 12,
  },
  search: {
    flex: 1,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    height: 44,
    fontSize: 15,
    color: colors.ink,
  },
  sort: {
    height: 44,
    paddingHorizontal: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    justifyContent: 'center',
  },
  sortText: { fontSize: 13, fontWeight: '600', color: colors.deep },
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
