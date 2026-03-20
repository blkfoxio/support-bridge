/**
 * Floating Action Button with badge for unread/awaiting conversations.
 */

import { awaitingYouCount, isOpen, toggleWidget } from '../state/store';

export function Fab() {
  const count = awaitingYouCount.value;

  return (
    <button
      class="sb-fab"
      onClick={toggleWidget}
      aria-label={isOpen.value ? 'Close support chat' : 'Open support chat'}
    >
      {isOpen.value ? (
        // Close icon (X)
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      ) : (
        // Chat icon
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      )}
      {count > 0 && !isOpen.value && (
        <span class="sb-fab-badge">{count > 9 ? '9+' : count}</span>
      )}
    </button>
  );
}
