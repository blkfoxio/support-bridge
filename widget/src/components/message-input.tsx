/**
 * Message compose bar with textarea and send button.
 * Enter to send, Shift+Enter for newline.
 */

import { useRef } from 'preact/hooks';
import { isSending } from '../state/store';

interface MessageInputProps {
  onSend: (body: string) => void;
  disabled?: boolean;
}

export function MessageInput({ onSend, disabled = false }: MessageInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const el = textareaRef.current;
    if (!el) return;
    const body = el.value.trim();
    if (!body) return;
    onSend(body);
    el.value = '';
    el.style.height = 'auto';
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };

  return (
    <div class="sb-input-bar">
      <textarea
        ref={textareaRef}
        class="sb-input-textarea"
        placeholder="Type a message..."
        rows={1}
        disabled={disabled || isSending.value}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
      />
      <button
        class="sb-input-send"
        onClick={handleSend}
        disabled={disabled || isSending.value}
        aria-label="Send message"
      >
        {isSending.value ? (
          <span class="sb-spinner" />
        ) : (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
          </svg>
        )}
      </button>
    </div>
  );
}
