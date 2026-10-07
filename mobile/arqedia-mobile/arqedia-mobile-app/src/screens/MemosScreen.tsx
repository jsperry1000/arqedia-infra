import React, { useEffect, useState } from 'react';
import { View, Text, FlatList, Pressable, StyleSheet, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { colors } from '@/theme/colors';
import { api } from '@/api/client';
import { Memo } from '@/types';
import { RootStackParamList } from '@/navigation/RootNavigator';

type Nav = NativeStackNavigationProp<RootStackParamList>;

export default function MemosScreen() {
  const navigation = useNavigation<Nav>();
  const [memos, setMemos] = useState<Memo[]>([]);
  const [query, setQuery] = useState('');

  useEffect(() => {
    api.listMemos().then(setMemos);
  }, []);

  const filtered = memos.filter((m) =>
    m.title.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Memos</Text>
      </View>

      <View style={styles.searchWrap}>
        <TextInput
          style={styles.search}
          placeholder="Search memos"
          placeholderTextColor={colors.muted}
          value={query}
          onChangeText={setQuery}
        />
      </View>

      <FlatList
        data={filtered}
        keyExtractor={(item) => item.memo_id}
        contentContainerStyle={{ paddingHorizontal: 12, paddingBottom: 12 }}
        renderItem={({ item }) => (
          <Pressable
            style={styles.row}
            onPress={() => navigation.navigate('MemoDetail', { memoId: item.memo_id })}
          >
            <View
              style={[
                styles.iconCircle,
                { backgroundColor: item.status === 'ready' ? colors.light : colors.border },
              ]}
            />
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle} numberOfLines={1}>
                {item.title}
              </Text>
              <Text style={styles.rowSubtitle} numberOfLines={1}>
                {item.memo_type} · rev. {item.revision}
              </Text>
            </View>
            <View
              style={[
                styles.pill,
                { backgroundColor: item.status === 'ready' ? colors.light : colors.border },
              ]}
            >
              <Text style={[styles.pillText, item.status !== 'ready' && { color: colors.subtext }]}>
                {item.status === 'ready' ? 'Ready' : 'Generating'}
              </Text>
            </View>
          </Pressable>
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: 20, paddingTop: 8, paddingBottom: 12 },
  title: { fontSize: 28, fontWeight: '700', color: colors.ink },
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
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 14,
    marginHorizontal: 8,
    marginBottom: 2,
    borderRadius: 14,
  },
  iconCircle: { width: 42, height: 42, borderRadius: 10 },
  rowTitle: { fontSize: 15.5, fontWeight: '600', color: colors.ink },
  rowSubtitle: { fontSize: 13, color: colors.subtext, marginTop: 2 },
  pill: { paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999 },
  pillText: { fontSize: 11.5, fontWeight: '600', color: colors.deep },
});
