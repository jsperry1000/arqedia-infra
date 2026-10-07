import React, { useState } from 'react';
import { View, Text, TextInput, Pressable, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { signIn, confirmSignIn, type SignInOutput } from 'aws-amplify/auth';
import { colors } from '@/theme/colors';

/** Which shape the card is in.
 *
 *  "in"       email and password
 *  "new"      the first-sign-in challenge: an account made by an invitation
 *             or by signup sets its own password here (ui/src/App.tsx:190)
 *  "totp"     a code from an authenticator app. The pool allows MFA; on
 *             7 October no customer had it on and the web app offers no way
 *             to turn it on, but a person who has it must still get in.
 *
 *  Any other step Cognito asks for is not built here, and the card says so
 *  rather than failing quietly. */
type Step = 'in' | 'new' | 'totp';

export default function SignInScreen({ onSignedIn }: { onSignedIn: () => void }) {
  const [step, setStep] = useState<Step>('in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  function next(res: SignInOutput) {
    const s = res.nextStep.signInStep;
    if (res.isSignedIn || s === 'DONE') {
      onSignedIn();
    } else if (s === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
      setAnswer('');
      setStep('new');
    } else if (s === 'CONFIRM_SIGN_IN_WITH_TOTP_CODE') {
      setAnswer('');
      setStep('totp');
    } else {
      setError(`This account needs a sign-in step the app does not do yet (${s}). `
        + 'Sign in on the web.');
    }
  }

  async function submit() {
    setBusy(true);
    setError('');
    try {
      if (step === 'in') {
        next(await signIn({ username: email.trim(), password }));
      } else {
        next(await confirmSignIn({ challengeResponse: answer.trim() }));
      }
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  const ready = !busy && (step === 'in' ? !!email.trim() && !!password : !!answer.trim());

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.card}>
        <Text style={styles.title}>ARQEDIA</Text>

        {step === 'in' && (
          <>
            <TextInput
              style={styles.input}
              placeholder="Email"
              placeholderTextColor={colors.muted}
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
            />
            <TextInput
              style={styles.input}
              placeholder="Password"
              placeholderTextColor={colors.muted}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoComplete="password"
            />
          </>
        )}

        {step === 'new' && (
          <>
            <Text style={styles.note}>Choose a password for this account.</Text>
            <TextInput
              style={styles.input}
              placeholder="New password"
              placeholderTextColor={colors.muted}
              value={answer}
              onChangeText={setAnswer}
              secureTextEntry
              autoComplete="password-new"
            />
          </>
        )}

        {step === 'totp' && (
          <>
            <Text style={styles.note}>Enter the code from your authenticator app.</Text>
            <TextInput
              style={styles.input}
              placeholder="6-digit code"
              placeholderTextColor={colors.muted}
              value={answer}
              onChangeText={setAnswer}
              keyboardType="number-pad"
              autoComplete="one-time-code"
              maxLength={6}
            />
          </>
        )}

        {!!error && <Text style={styles.error}>{error}</Text>}

        <Pressable
          style={[styles.button, !ready && { opacity: 0.5 }]}
          disabled={!ready}
          onPress={submit}
        >
          {busy ? <ActivityIndicator color={colors.surface} />
                : <Text style={styles.buttonText}>
                    {step === 'new' ? 'Set the password' : step === 'totp' ? 'Verify' : 'Sign in'}
                  </Text>}
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background, justifyContent: 'center' },
  card: { marginHorizontal: 20, gap: 12 },
  title: { fontSize: 28, fontWeight: '700', color: colors.deep, marginBottom: 8 },
  note: { fontSize: 14, color: colors.subtext },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    height: 48,
    fontSize: 15,
    color: colors.ink,
  },
  error: { fontSize: 13.5, color: colors.ink },
  button: {
    height: 50,
    borderRadius: 14,
    backgroundColor: colors.deep,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 4,
  },
  buttonText: { color: colors.surface, fontSize: 16, fontWeight: '700' },
});
