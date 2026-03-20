/**
 * Tabbed conversation list with Active / Resolved / Closed tabs.
 */

import { activeTab, filteredConversations, navigateToDetail, navigateToNew, setTab } from '../state/store';
import { relativeTime } from '../utils/time';
import { severityColor, severityLabel } from '../utils/status';
import type { SbConversation } from '../api/types';

const TABS = [
  { id: 'active' as const, label: 'Active' },
  { id: 'resolved' as const, label: 'Resolved' },
  { id: 'closed' as const, label: 'Closed' },
];

export function ConversationList() {
  const current = activeTab.value;
  const items = filteredConversations.value;

  return (
    <div class="sb-conv-list">
      {/* Tabs */}
      <div class="sb-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            class={`sb-tab ${current === tab.id ? 'sb-tab--active' : ''}`}
            onClick={() => setTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* List */}
      <div class="sb-conv-list-items">
        {items.length === 0 ? (
          <div class="sb-empty">
            <p>No {current} conversations</p>
          </div>
        ) : (
          items.map((conv) => (
            <ConversationRow key={conv.id} conversation={conv} />
          ))
        )}
      </div>

      {/* New Conversation Button */}
      <div class="sb-conv-list-footer">
        <button class="sb-btn sb-btn--primary" onClick={navigateToNew}>
          + New Conversation
        </button>
      </div>
    </div>
  );
}

function ConversationRow({ conversation: conv }: { conversation: SbConversation }) {
  const time = relativeTime(conv.last_message_at || conv.opened_at);

  return (
    <button class="sb-conv-row" onClick={() => navigateToDetail(conv.id)}>
      <div class="sb-conv-row-top">
        <span class="sb-conv-row-subject">{conv.subject || 'No subject'}</span>
        <span class="sb-conv-row-time">{time}</span>
      </div>
      <div class="sb-conv-row-bottom">
        <span
          class="sb-badge sb-badge--severity"
          style={{ backgroundColor: severityColor(conv.severity) }}
        >
          {severityLabel(conv.severity)}
        </span>
        {conv.status === 'awaitingYou' && (
          <span class="sb-badge sb-badge--awaiting">AWAITING YOU</span>
        )}
      </div>
    </button>
  );
}
