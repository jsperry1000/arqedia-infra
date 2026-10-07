import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '@/theme/colors';
import { useSession } from '@/auth/session';

// Who is signed in, and signing out. Everything else about an account - plan,
// seats, card, brand - stays on the web.
export default function AccountScreen() {
  const { email, signOut } = useSession();

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Account</Text>
        <Text style={styles.subtitle}>{email}</Text>
      </View>
      <View style={styles.body}>
        <Pressable style={styles.button} onPress={signOut}>
          <Text style={styles.buttonText}>Sign out</Text>
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
  body: { paddingHorizontal: 20 },
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
