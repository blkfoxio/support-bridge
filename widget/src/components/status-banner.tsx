/**
 * Status banner shown at the bottom of chat when conversation is resolved or closed.
 * - Resolved: "Was your issue resolved?" Yes/No buttons
 * - Closed: "This conversation is closed" + Reopen link
 */

import type { CustomerStatus } from '../api/types';

interface StatusBannerProps {
  status: CustomerStatus;
  onClose: () => void;
  onReopen: () => void;
}

export function StatusBanner({ status, onClose, onReopen }: StatusBannerProps) {
  if (status === 'resolved') {
    return (
      <div class="sb-status-banner sb-status-banner--resolved">
        <span>Was your issue resolved?</span>
        <div class="sb-status-banner-actions">
          <button class="sb-btn sb-btn--sm sb-btn--primary" onClick={onClose}>
            Yes, close it
          </button>
          <button class="sb-btn sb-btn--sm sb-btn--ghost" onClick={onReopen}>
            No, still need help
          </button>
        </div>
      </div>
    );
  }

  if (status === 'closed') {
    return (
      <div class="sb-status-banner sb-status-banner--closed">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
        <span>This conversation is closed</span>
        <button class="sb-btn sb-btn--link" onClick={onReopen}>
          Reopen
        </button>
      </div>
    );
  }

  return null;
}
