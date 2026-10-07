import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { View, Text } from 'react-native';
import { colors } from '@/theme/colors';
import MemosScreen from '@/screens/MemosScreen';
import ShareScreen from '@/screens/ShareScreen';
import MemoDetailScreen from '@/screens/MemoDetailScreen';

export type RootStackParamList = {
  Tabs: undefined;
  MemoDetail: { memoId: string };
};

export type TabParamList = {
  Memos: undefined;
  Share: undefined;
  Account: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator<TabParamList>();

function AccountScreen() {
  // Placeholder — identity_seats_spec_v1.md defines seat/session concepts
  // but no mobile account-screen content; left as a stub.
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.background }}>
      <Text style={{ color: colors.subtext }}>Account</Text>
    </View>
  );
}

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
        <Stack.Screen name="MemoDetail" component={MemoDetailScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
