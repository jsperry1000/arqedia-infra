import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { colors } from '@/theme/colors';
import { Engagement, MemoRef } from '@/types';
import MemosScreen from '@/screens/MemosScreen';
import EngagementMemosScreen from '@/screens/EngagementMemosScreen';
import ShareScreen from '@/screens/ShareScreen';
import MemoDetailScreen from '@/screens/MemoDetailScreen';
import AccountScreen from '@/screens/AccountScreen';

// Memos belong to an engagement, and the API lists them per engagement, so
// the Memos tab is a drill-down: engagements, then one engagement's memos,
// then a memo. The row already read is passed forward rather than fetched
// again - there is no single-row endpoint for either.
export type RootStackParamList = {
  Tabs: undefined;
  EngagementMemos: { engagement: Engagement };
  MemoDetail: { memo: MemoRef; engagement: string };
};

export type TabParamList = {
  Memos: undefined;
  Share: undefined;
  Account: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator<TabParamList>();

function Tabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.deep,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: { borderTopColor: colors.border },
      }}
    >
      <Tab.Screen name="Memos" component={MemosScreen} />
      <Tab.Screen name="Share" component={ShareScreen} />
      <Tab.Screen name="Account" component={AccountScreen} />
    </Tab.Navigator>
  );
}

export default function RootNavigator() {
  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        <Stack.Screen name="Tabs" component={Tabs} />
        <Stack.Screen name="EngagementMemos" component={EngagementMemosScreen} />
        <Stack.Screen name="MemoDetail" component={MemoDetailScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
