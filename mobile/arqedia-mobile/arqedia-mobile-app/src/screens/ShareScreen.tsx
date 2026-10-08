import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, Pressable, StyleSheet, TextInput, ScrollView, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '@/theme/colors';
import { api, chargeKey, Capped, OverageRequired } from '@/api/client';
import { Engagement, MemoRef, ShareAllowance, ShareGrant, ShareSent } from '@/types';

// Sending a memorandum, and taking it back. Follows ui/src/Share.tsx: the
// allowance is shown before anything is pressed, the person affirms they are
// entitled to share, and a share past the allowance goes only at a price the
// person has accepted on this screen - never one accepted for them.

const day = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString() : '');
const money = (cents: number) => `$${(cents / 100).toFixed(2)}`;

// The default is not a date the tenant set: two weeks, and six months once
// the recipient registers. A chosen period is a ceiling registering never
// moves. The same three choices as the web.
const EXPIRY: { value: number | null; label: string }[] = [
  { value: null, label: '2 weeks, or 6 months if they register' },
  { value: 30, label: '30 days, fixed' },
  { value: 90, label: '90 days, fixed' },
];

function AllowanceLine({ a }: { a: ShareAllowance }) {
  if (a.capped) {
    return (
      <Text style={styles.warn}>
        This workspace has no balance, so it cannot share. Revoking still works.
        Top up on the web, under Settings, Account management.
      </Text>
    );
  }
  const span = a.trial ? 'during the trial' : `this month (to ${day(a.period_ends_at)})`;
  if (a.allowance === null) {
    return <Text style={styles.small}>{a.used} shared {span}. No limit on this plan.</Text>;
  }
  const over = a.overage_cents === null
    ? 'Sharing past it is not priced yet, so it is refused.'
    : `Each one past it costs ${money(a.overage_cents)}.`;
  return (
    <Text style={styles.small}>
      {a.used} of {a.allowance} included shares used {span}
      {a.remaining === 0 ? ' — all of them. ' : `, ${a.remaining} left. `}
      {over} At most {a.daily_limit} a day ({a.today} today).
    </Text>
  );
}

function Check({ checked, onPress, children }: {
  checked: boolean; onPress: () => void; children: React.ReactNode;
}) {
  return (
    <Pressable style={styles.checkRow} onPress={onPress} hitSlop={6}>
      <View style={[styles.box, checked && styles.boxOn]}>
        {checked && <Text style={styles.tick}>✓</Text>}
      </View>
      <Text style={styles.checkText}>{children}</Text>
    </Pressable>
  );
}

export default function ShareScreen() {
  const [engagements, setEngagements] = useState<Engagement[] | null>(null);
  const [engagement, setEngagement] = useState<Engagement | null>(null);
  const [memos, setMemos] = useState<MemoRef[] | null>(null);
  const [memo, setMemo] = useState<MemoRef | null>(null);

  const [grants, setGrants] = useState<ShareGrant[]>([]);
  const [allowance, setAllowance] = useState<ShareAllowance | null>(null);

  const [recipient, setRecipient] = useState('');
  const [expiry, setExpiry] = useState<number | null>(null);
  const [affirmed, setAffirmed] = useState(false);
  // The price this send will be charged at, once the person has been shown
  // it - up front from the allowance, or from a 409 - and whether they have
  // accepted it. Both are cleared after every send.
  const [price, setPrice] = useState<number | null>(null);
  const [accepted, setAccepted] = useState(false);

  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [sent, setSent] = useState<ShareSent | null>(null);

  const loadShares = useCallback(async () => {
    try {
      const r = await api.shares();
      setGrants(r.grants);
      setAllowance(r.allowance);
    } catch (err: any) {
      setError(err?.message || String(err));
    }
  }, []);

  useEffect(() => {
    api.engagements()
      .then((r) => setEngagements(r.engagements))
      .catch((err) => setError(err?.message || String(err)));
    loadShares();
  }, [loadShares]);

  // Past the allowance already, and priced: the price is put to the person
  // before they press anything.
  const past = !!allowance && allowance.allowance !== null && allowance.remaining === 0;
  const upFront = past && allowance?.overage_cents != null ? allowance.overage_cents : null;
  const cost = price ?? upFront;

  const pickEngagement = async (e: Engagement) => {
    setEngagement(e);
    setMemo(null);
    setMemos(null);
    try {
      setMemos((await api.memos(e.engagement)).memos);
    } catch (err: any) {
      setError(err?.message || String(err));
    }
  };

  const onSend = async () => {
    if (!memo) return;
    setSending(true);
    setError('');
    setSent(null);
    try {
      const result = await api.sendShare(memo.memo_id, {
        recipient: recipient.trim(),
        authority_affirmed: affirmed,
        expiry_days: expiry,
        // One press, one key.
        idempotency_key: chargeKey(),
        accept_overage_cents: cost !== null && accepted ? cost : null,
      });
      setSent(result);
      setRecipient('');
      setAffirmed(false);
      setPrice(null);
      setAccepted(false);
      loadShares();
    } catch (err: any) {
      if (err instanceof OverageRequired) {
        // Nothing was sent or charged. The price is shown, and the next
        // press sends only if the person ticks to accept it.
        setPrice(err.overageCents);
        setAccepted(false);
        setError(err.message);
        loadShares();
      } else if (err instanceof Capped) {
        setError(err.message);
        loadShares();
      } else {
        setError(err?.message || String(err));
      }
    } finally {
      setSending(false);
    }
  };

  const onRevoke = async (grantId: string) => {
    setBusy(grantId);
    setError('');
    try {
      const updated = await api.revokeShare(grantId);
      setGrants((g) => g.map((x) => (x.grant_id === grantId ? updated : x)));
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy('');
    }
  };

  const capped = !!allowance?.capped;
  const ready = !!memo && !!recipient.trim() && affirmed && !sending
    && !!allowance && !capped && (cost === null || accepted);

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Share</Text>
        <Text style={styles.subtitle}>Send a memo to someone, right now</Text>
      </View>

      <ScrollView contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: 12, gap: 18 }}>
        {allowance ? <AllowanceLine a={allowance} />
                   : !error && <Text style={styles.small}>Reading the allowance…</Text>}

        <View>
          <Text style={styles.sectionLabel}>Memo to share</Text>

          {!engagement && (
            <>
              {engagements === null && <Text style={styles.small}>Loading…</Text>}
              {engagements?.length === 0 && <Text style={styles.small}>No open engagements.</Text>}
              {engagements?.map((e) => (
                <Pressable key={e.engagement_id} style={styles.pick} onPress={() => pickEngagement(e)}>
                  <View style={[styles.pickIcon, { backgroundColor: colors.shade }]} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.engagementName} numberOfLines={1}>{e.engagement}</Text>
                    <Text style={styles.pickSubtitle} numberOfLines={1}>
                      {e.subject_name ?? 'No subject named'}
                    </Text>
                  </View>
                  <Text style={styles.chevron}>{'›'}</Text>
                </Pressable>
              ))}
            </>
          )}

          {engagement && (
            <>
              <Pressable onPress={() => { setEngagement(null); setMemo(null); }} hitSlop={6}>
                <Text style={styles.backLink}>‹ {engagement.engagement}</Text>
              </Pressable>
              {memos === null && <Text style={styles.small}>Loading…</Text>}
              {memos?.length === 0 && <Text style={styles.small}>No memos in this engagement yet.</Text>}
              {memos?.map((m) => {
                const selected = m.memo_id === memo?.memo_id;
                return (
                  <Pressable
                    key={m.memo_id}
                    onPress={() => setMemo(m)}
                    style={[
                      styles.pick,
                      { borderColor: selected ? colors.deep : colors.border, borderWidth: selected ? 1.5 : 1 },
                    ]}
                  >
                    <View style={[styles.pickIcon, { backgroundColor: selected ? colors.light : colors.shade }]} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.pickTitle} numberOfLines={1}>{m.template_label}</Text>
                      <Text style={styles.pickSubtitle}>Memo {m.label} · {day(m.generated_at)}</Text>
                    </View>
                  </Pressable>
                );
              })}
            </>
          )}
        </View>

        <View>
          <Text style={styles.sectionLabel}>Send to</Text>
          <View style={styles.formCard}>
            <TextInput
              style={styles.input}
              placeholder="name@firm.com"
              placeholderTextColor={colors.muted}
              value={recipient}
              onChangeText={setRecipient}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
            />
          </View>
        </View>

        <View>
          <Text style={styles.sectionLabel}>Access</Text>
          {EXPIRY.map((o) => (
            <Check key={String(o.value)} checked={expiry === o.value} onPress={() => setExpiry(o.value)}>
              {o.label}
            </Check>
          ))}
        </View>

        <Text style={styles.small}>
          The recipient gets a link by email to this memorandum and nothing else:
          not the source documents, not your configuration, not the rest of the
          engagement. Revoking ends access in ARQEDIA; it cannot recall a copy
          already downloaded, and every page of that copy carries their address.
        </Text>

        <Check checked={affirmed} onPress={() => setAffirmed(!affirmed)}>
          I am entitled to share this memorandum with this person. It carries
          third-party identity material, and that assurance is mine to give.
        </Check>

        {cost !== null && (
          <View style={styles.costBox}>
            <Text style={styles.warn}>
              This is past the shares your plan includes. Sending it costs {money(cost)},
              charged when you press Send.
            </Text>
            <Check checked={accepted} onPress={() => setAccepted(!accepted)}>
              I accept the {money(cost)} charge for this share.
            </Check>
          </View>
        )}

        {!!error && <Text style={styles.error}>{error}</Text>}

        {sent && (
          <Text style={styles.small}>
            {sent.reinstated ? 'Sent again, and access restored, ' : 'Sent '}
            to {sent.recipient_email}. Access ends {day(sent.expires_at)}.
            {sent.charged_cents > 0 && ` Charged ${money(sent.charged_cents)}.`}
            {!sent.sent && ' The email could not be delivered; the share stands, '
              + 'and sending it again retries the email.'}
          </Text>
        )}

        <View>
          <Text style={styles.sectionLabel}>Recently sent</Text>
          {grants.length === 0 && <Text style={styles.small}>Nothing shared yet.</Text>}
          {grants.map((g) => (
            <View key={g.grant_id} style={styles.grantRow}>
              <View style={styles.avatar}>
                <Text style={styles.avatarText}>{g.recipient_email.slice(0, 2).toUpperCase()}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.grantText} numberOfLines={1}>
                  <Text style={{ fontWeight: '600' }}>{g.recipient_email}</Text>
                  {'  '}Memo {g.memo_label}
                </Text>
                <Text style={styles.grantMeta} numberOfLines={1}>
                  {g.opens} opens · {g.downloads} downloads
                </Text>
              </View>
              <View style={{ alignItems: 'flex-end', gap: 3 }}>
                <Text style={[styles.grantStatus, (g.revoked || g.expired) && { color: colors.muted }]}>
                  {g.revoked ? 'Revoked' : g.expired ? 'Expired' : g.first_opened_at ? 'Viewed' : 'Sent'}
                </Text>
                {!g.revoked && !g.expired && (
                  busy === g.grant_id
                    ? <ActivityIndicator size="small" color={colors.ink} />
                    : (
                      <Pressable onPress={() => onRevoke(g.grant_id)} hitSlop={8} disabled={!!busy}>
                        <Text style={styles.revokeText}>Revoke</Text>
                      </Pressable>
                    )
                )}
              </View>
            </View>
          ))}
        </View>
      </ScrollView>

      <View style={styles.sendBar}>
        <Pressable
          style={[styles.sendBtn, !ready && { opacity: 0.5 }]}
          disabled={!ready}
          onPress={onSend}
        >
          {sending ? <ActivityIndicator color={colors.surface} />
                   : <Text style={styles.sendBtnText}>
                       {capped ? 'Sharing is paused' : cost !== null ? `Send — ${money(cost)}` : 'Send'}
                     </Text>}
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
  small: { fontSize: 13, color: colors.subtext, lineHeight: 18 },
  warn: { fontSize: 13.5, color: colors.ink, lineHeight: 19 },
  error: { fontSize: 13.5, color: colors.ink },
  // The engagement's name, wherever the picker shows it: the row to choose it,
  // and the line above its memos that goes back. Larger than the memo titles,
  // because it is what the person is choosing between.
  engagementName: { fontSize: 18, fontWeight: '700', color: colors.ink },
  backLink: { fontSize: 18, fontWeight: '700', color: colors.mid, marginBottom: 10 },
  chevron: { fontSize: 22, color: colors.muted },
  pick: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface, borderRadius: 14, padding: 12, marginBottom: 8,
    borderWidth: 1, borderColor: colors.border,
  },
  pickIcon: { width: 36, height: 36, borderRadius: 9 },
  pickTitle: { fontSize: 14, fontWeight: '600', color: colors.ink },
  pickSubtitle: { fontSize: 12, color: colors.subtext, marginTop: 1 },
  formCard: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 12,
  },
  input: { paddingHorizontal: 14, paddingVertical: 12, fontSize: 15, color: colors.ink },
  checkRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingVertical: 6 },
  box: {
    width: 20, height: 20, borderRadius: 4, borderWidth: 1.5, borderColor: colors.muted,
    alignItems: 'center', justifyContent: 'center', marginTop: 1,
  },
  boxOn: { backgroundColor: colors.deep, borderColor: colors.deep },
  tick: { color: colors.surface, fontSize: 13, fontWeight: '700' },
  checkText: { flex: 1, fontSize: 13.5, color: colors.ink, lineHeight: 19 },
  costBox: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: 12, padding: 12, gap: 6,
  },
  grantRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10 },
  avatar: {
    width: 30, height: 30, borderRadius: 999, backgroundColor: colors.light,
    alignItems: 'center', justifyContent: 'center',
  },
  avatarText: { fontSize: 12, fontWeight: '700', color: colors.deep },
  grantText: { fontSize: 13.5, color: colors.ink },
  grantMeta: { fontSize: 12, color: colors.subtext, marginTop: 1 },
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
