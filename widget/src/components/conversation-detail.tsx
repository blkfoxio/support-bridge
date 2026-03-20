/**
 * Conversation detail view: message thread + input bar + status banner.
 * Manages SSE connection and polling fallback.
 */

import { useEffect, useRef } from 'preact/hooks';
import {
  conversations,
  messages,
  selectedConversation,
  selectedConversationId,
  sortedMessages,
  isLoading,
  isSending,
  navigateToCsat,
} from '../state/store';
import { isInteractive, isTerminal } from '../api/types';
import type { SbMessage } from '../api/types';
import { MessageBubble } from './message-bubble';
import { MessageInput } from './message-input';
import { StatusBanner } from './status-banner';
import { formatDateSeparator } from '../utils/time';
import { severityColor, severityLabel, statusLabel } from '../utils/status';
import { getClient, getSse } from '../services';

export function ConversationDetail() {
  const conv = selectedConversation.value;
  const convId = selectedConversationId.value;
  const msgs = sortedMessages.value;
  const scrollRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load messages and connect SSE
  useEffect(() => {
    if (!convId) return;

    const client = getClient();
    if (!client) return;

    isLoading.value = true;
    client.getMessages(convId).then((result) => {
      messages.value = result;
      isLoading.value = false;
    }).catch(() => {
      isLoading.value = false;
    });

    // SSE connection
    const sse = getSse();
    if (sse) {
      sse.connect(convId, (event) => {
        if (event.eventType === 'message.created') {
          const data = event.data as unknown as { id: string };
          if (!messages.value.find((m: SbMessage) => m.id === data.id)) {
            const msg = event.data as unknown as SbMessage;
            messages.value = [...messages.value, msg];
          }
        }
        if (event.eventType === 'conversation.status_changed' || event.eventType === 'conversation.closed') {
          client.getConversation(convId).then((updated) => {
            conversations.value = conversations.value.map((c) =>
              c.id === convId ? updated : c,
            );
          });
        }
      });
    }

    // Polling fallback (5s)
    pollRef.current = setInterval(() => {
      client.getMessages(convId).then((result) => {
        messages.value = result;
      }).catch(() => {});
    }, 5000);

    return () => {
      sse?.disconnect();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [convId]);

  // Auto-scroll on new messages
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [msgs.length]);

  if (!conv) {
    return <div class="sb-empty"><p>Conversation not found</p></div>;
  }

  const handleSend = async (body: string) => {
    const client = getClient();
    if (!client || !convId) return;

    isSending.value = true;
    try {
      const msg = await client.sendMessage(convId, body);
      if (!messages.value.find((m: SbMessage) => m.id === msg.id)) {
        messages.value = [...messages.value, msg];
      }
    } catch (err) {
      console.error('Failed to send message:', err);
    } finally {
      isSending.value = false;
    }
  };

  const handleClose = async () => {
    const client = getClient();
    if (!client || !convId) return;

    try {
      await client.closeConversation(convId);
      navigateToCsat();
    } catch (err) {
      console.error('Failed to close conversation:', err);
    }
  };

  const handleReopen = async () => {
    const client = getClient();
    if (!client || !convId) return;

    try {
      const updated = await client.reopenConversation(convId);
      conversations.value = conversations.value.map((c) =>
        c.id === convId ? updated : c,
      );
    } catch (err) {
      console.error('Failed to reopen conversation:', err);
    }
  };

  const messagesWithDates = buildMessageGroups(msgs);

  return (
    <div class="sb-detail">
      <div class="sb-detail-info">
        <span class="sb-detail-status">{statusLabel(conv.status)}</span>
        <span class="sb-detail-sep">|</span>
        <span
          class="sb-badge sb-badge--severity"
          style={{ backgroundColor: severityColor(conv.severity) }}
        >
          {severityLabel(conv.severity)}
        </span>
      </div>

      <div class="sb-detail-thread" ref={scrollRef}>
        {isLoading.value && msgs.length === 0 ? (
          <div class="sb-empty"><span class="sb-spinner" /></div>
        ) : (
          messagesWithDates.map((item) => {
            if (item.type === 'separator') {
              return (
                <div key={item.key} class="sb-date-separator">
                  <span>{item.label}</span>
                </div>
              );
            }
            return <MessageBubble key={item.key} message={item.message} />;
          })
        )}
      </div>

      {isTerminal(conv.status) && (
        <StatusBanner
          status={conv.status}
          onClose={handleClose}
          onReopen={handleReopen}
        />
      )}

      {isInteractive(conv.status) && (
        <MessageInput onSend={handleSend} disabled={!isInteractive(conv.status)} />
      )}
    </div>
  );
}

type MessageGroupItem =
  | { type: 'separator'; key: string; label: string }
  | { type: 'message'; key: string; message: SbMessage };

function buildMessageGroups(msgs: SbMessage[]): MessageGroupItem[] {
  const items: MessageGroupItem[] = [];
  let lastDate = '';

  for (const msg of msgs) {
    const dateStr = new Date(msg.created_at).toDateString();
    if (dateStr !== lastDate) {
      items.push({
        type: 'separator',
        key: `sep-${dateStr}`,
        label: formatDateSeparator(msg.created_at),
      });
      lastDate = dateStr;
    }
    items.push({ type: 'message', key: msg.id, message: msg });
  }

  return items;
}
