/**
 * Root widget component.
 * Renders the FAB and, when open, the panel with the active view.
 */

import { useEffect, useRef } from 'preact/hooks';
import {
  isOpen,
  currentView,
  conversations,
  isLoading,
  widgetConfig,
} from './state/store';
import { Fab } from './components/fab';
import { Panel } from './components/panel';
import { ConversationList } from './components/conversation-list';
import { ConversationDetail } from './components/conversation-detail';
import { NewConversation } from './components/new-conversation';
import { CsatFeedback } from './components/csat-feedback';
import { getClient } from './services';

export function Widget() {
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll conversations every 15s when panel is open
  useEffect(() => {
    if (!isOpen.value) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }

    const loadConversations = () => {
      const client = getClient();
      if (!client) return;

      client.getConversations().then((result) => {
        conversations.value = result;
      }).catch((err) => {
        console.error('Failed to load conversations:', err);
      });
    };

    // Load immediately
    loadConversations();

    // Then poll every 15s
    pollRef.current = setInterval(loadConversations, 15000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [isOpen.value]);

  // Initial load of conversations (for badge count even when closed)
  useEffect(() => {
    const client = getClient();
    if (!client) return;

    client.getConversations().then((result) => {
      conversations.value = result;
    }).catch(() => {});
  }, [widgetConfig.value?.token]);

  const view = currentView.value;

  return (
    <div class="sb-widget">
      {isOpen.value && (
        <Panel>
          {view === 'list' && <ConversationList />}
          {view === 'detail' && <ConversationDetail />}
          {view === 'new' && <NewConversation />}
          {view === 'csat' && <CsatFeedback />}
        </Panel>
      )}
      <Fab />
    </div>
  );
}
