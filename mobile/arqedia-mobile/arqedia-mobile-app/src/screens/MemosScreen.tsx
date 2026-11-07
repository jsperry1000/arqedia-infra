import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, FlatList, Pressable, StyleSheet, TextInput, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { colors } from '@/theme/colors';
import { api } from '@/api/client';
import { Engagement } from '@/types';
import { RootStackParamList } from '@/navigation/RootNavigator';
import { activeName, useWorkspace } from '@/workspace';
import { useWorkspaceGate } from '@/screens/WorkspaceGate';

type Nav = NativeStackNavigationProp<RootStackParamList>;

// The first step of the drill-down: the open engagements. GET /engagements
// leaves archived ones out unless asked, and so does this.
export default function MemosScreen() {
  const navigation = useNavigation<Nav>();
  const [engagements, setEngagements] = useState<Engagement[] | null>(null);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState('');
  const workspace = useWorkspace();
  const gate = useWorkspaceGate();
  const { active, epoch } = workspace;

  // Read again whenever the workspace changes; the last one's engagements
  // are cleared first, so they are never shown under the new name.
  const load = useCallback(async () => {
    setError('');
    if (active === null) return;
    try {
      setEngagements((await api.engagements()).engagements);
    } catch (err: any) {
      setError(err?.message || String(err));
    }
  }, [active, epoch]);

  useEffect(() => {
    setEngagements(null);
    setQuery('');
    load();
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const name = activeName(workspace);

  const q = query.toLowerCase();
  const filtered = (engagements ?? []).filter((e) =>
    e.engagement.toLowerCase().includes(q)
    || (e.subject_name ?? '').toLowerCase().includes(q)
  );

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Memos</Text>
        {!!name && <Text style={styles.workspace} numberOfLines={1}>{name}</Text>}
        <Text style={styles.subtitle}>Choose an engagement</Text>
      </View>

      {gate ?? (<>

      <View style={styles.searchWrap}>
        <TextInput
          style={styles.search}
          placeholder="Search engagements"
          placeholderTextColor={colors.muted}
          value={query}
          onChangeText={setQuery}
        />
      </View>

      {!!error && <Text style={styles.message}>{error}</Text>}
      {engagements === null && !error && <Text style={styles.message}>Loading…</Text>}
      {engagements !== null && engagements.length === 0 && (
        <Text style={styles.message}>No open engagements.</Text>
      )}

      <FlatList
        data={filtered}
        keyExtractor={(item) => String(item.engagement_id)}
        contentContainerStyle={{ paddingHorizontal: 12, paddingBottom: 12 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        renderItem={({ item }) => (
          <Pressable
            style={styles.row}
            onPress={() => navigation.navigate('EngagementMemos', { engagement: item })}
          >
            <View style={styles.iconCircle} />
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle} numberOfLines={1}>{item.engagement}</Text>
              <Text style={styles.rowSubtitle} numberOfLines={1}>
                {item.subject_name ?? 'No subject named'}
              </Text>
            </View>
            <Text style={styles.chevron}>{'›'}</Text>
          </Pressable>
        )}
      />
      </>)}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: 20, paddingTop: 8, paddingBottom: 12 },
  title: { fontSize: 28, fontWeight: '700', color: colors.ink },
  subtitle: { fontSize: 14, color: colors.subtext, marginTop: 2 },
  // The active workspace, chosen on the Account tab.
  workspace: { fontSize: 15, fontWeight: '600', color: colors.mid, marginTop: 2 },
  searchWrap: { paddingHorizontal: 20, paddingBottom: 14 },
  search: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    height: 44,
    fontSize: 15,
    color: colors.ink,
  },
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
