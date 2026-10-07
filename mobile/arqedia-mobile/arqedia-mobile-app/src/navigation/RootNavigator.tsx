import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { colors } from '@/theme/colors';
import MemosScreen from '@/screens/MemosScreen';
import ShareScreen from '@/screens/ShareScreen';
import MemoDetailScreen from '@/screens/MemoDetailScreen';
import AccountScreen from '@/screens/AccountScreen';

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
