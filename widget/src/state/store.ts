/**
 * Widget state management using Preact signals.
 */

import { signal, computed } from '@preact/signals';
import type { SbConversation, SbMessage, WidgetConfig, CustomerStatus } from '../api/types';

// --- UI State ---

export const isOpen = signal(false);
export const currentView = signal<'list' | 'detail' | 'new' | 'csat'>('list');
export const selectedConversationId = signal<string | null>(null);
export const activeTab = signal<'active' | 'resolved' | 'closed'>('active');
export const isLoading = signal(false);
export const isSending = signal(false);
export const error = signal<string | null>(null);

// --- Data State ---

export const conversations = signal<SbConversation[]>([]);
export const messages = signal<SbMessage[]>([]);

// --- Config ---

export const widgetConfig = signal<WidgetConfig | null>(null);

// --- Computed ---

export const awaitingYouCount = computed(() =>
  conversations.value.filter((c) => c.status === 'awaitingYou').length,
);

export const selectedConversation = computed(() =>
  conversations.value.find((c) => c.id === selectedConversationId.value) ?? null,
);

export const filteredConversations = computed(() => {
  const tab = activeTab.value;
  return conversations.value.filter((c) => {
    switch (tab) {
      case 'active':
        return c.status === 'active' || c.status === 'awaitingYou';
      case 'resolved':
        return c.status === 'resolved';
      case 'closed':
        return c.status === 'closed';
    }
  });
});

export const sortedMessages = computed(() =>
  [...messages.value].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  ),
);

// --- Actions ---

export function openWidget(): void {
  isOpen.value = true;
}

export function closeWidget(): void {
  isOpen.value = false;
}

export function toggleWidget(): void {
  isOpen.value = !isOpen.value;
}

export function navigateToList(): void {
  currentView.value = 'list';
  selectedConversationId.value = null;
  messages.value = [];
}

export function navigateToDetail(conversationId: string): void {
  selectedConversationId.value = conversationId;
  currentView.value = 'detail';
}

export function navigateToNew(): void {
  currentView.value = 'new';
}

export function navigateToCsat(): void {
  currentView.value = 'csat';
}

export function setTab(tab: 'active' | 'resolved' | 'closed'): void {
  activeTab.value = tab;
}

export function clearError(): void {
  error.value = null;
}
