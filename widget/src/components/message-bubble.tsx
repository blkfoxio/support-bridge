/**
 * Chat message bubble with three styles:
 * - customer: right-aligned, primary background
 * - analyst: left-aligned, bordered, avatar + name
 * - system: centered, muted pill
 */

import type { SbMessage } from '../api/types';
import { formatMessageTime } from '../utils/time';

interface MessageBubbleProps {
  message: SbMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const time = formatMessageTime(message.created_at);

  if (message.actor_type === 'system') {
    return (
      <div class="sb-msg sb-msg--system">
        <span class="sb-msg-system-text">{message.body_plain}</span>
      </div>
    );
  }

  if (message.actor_type === 'customer') {
    return (
      <div class="sb-msg sb-msg--customer">
        <div class="sb-msg-bubble sb-msg-bubble--customer">
          <p class="sb-msg-body">{message.body_plain}</p>
          <span class="sb-msg-time">{time}</span>
        </div>
      </div>
    );
  }

  // analyst
  const initials = message.sender_name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div class="sb-msg sb-msg--analyst">
      <div class="sb-msg-avatar" title={message.sender_name}>
        {initials}
      </div>
      <div class="sb-msg-content">
        <span class="sb-msg-sender">{message.sender_name}</span>
        <div class="sb-msg-bubble sb-msg-bubble--analyst">
          <p class="sb-msg-body">{message.body_plain}</p>
          <span class="sb-msg-time">{time}</span>
        </div>
      </div>
    </div>
  );
}
