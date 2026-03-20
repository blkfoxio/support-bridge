/**
 * Panel container with header and close button.
 * Renders the active view inside.
 */

import type { ComponentChildren } from 'preact';
import { closeWidget, currentView, navigateToList, selectedConversation } from '../state/store';

interface PanelProps {
  children: ComponentChildren;
}

export function Panel({ children }: PanelProps) {
  const view = currentView.value;
  const conv = selectedConversation.value;

  const showBack = view === 'detail' || view === 'new' || view === 'csat';
  const title =
    view === 'new'
      ? 'New Conversation'
      : view === 'csat'
        ? 'Rate Your Experience'
        : view === 'detail' && conv
          ? conv.subject || 'Conversation'
          : 'SOC Support';

  return (
    <div class="sb-panel">
      <div class="sb-panel-header">
        <div class="sb-panel-header-left">
          {showBack && (
            <button class="sb-panel-back" onClick={navigateToList} aria-label="Back to list">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
          )}
          <span class="sb-panel-title">{title}</span>
        </div>
        <button class="sb-panel-close" onClick={closeWidget} aria-label="Close panel">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
      <div class="sb-panel-body">{children}</div>
    </div>
  );
}
