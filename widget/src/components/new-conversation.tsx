/**
 * New conversation form with subject, category, severity, and message fields.
 */

import { useRef, useState } from 'preact/hooks';
import { conversations, isLoading, navigateToDetail, navigateToList, widgetConfig } from '../state/store';
import { getClient } from '../services';
import type { IssueCategory, Severity } from '../api/types';

const CATEGORIES: { value: IssueCategory; label: string }[] = [
  { value: 'incident', label: 'Incident' },
  { value: 'request', label: 'Request' },
  { value: 'question', label: 'Question' },
  { value: 'problem', label: 'Problem' },
];

const SEVERITIES: { value: Severity; label: string }[] = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

interface NewConversationProps {
  caseId?: string;
  caseSubject?: string;
}

export function NewConversation({ caseId, caseSubject }: NewConversationProps) {
  const config = widgetConfig.value;
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const subjectRef = useRef<HTMLInputElement>(null);
  const messageRef = useRef<HTMLTextAreaElement>(null);
  const [category, setCategory] = useState<IssueCategory>('question');
  const [severity, setSeverity] = useState<Severity>('medium');

  const defaultSubject = caseId && caseSubject ? `Re: [#${caseId}] ${caseSubject}` : '';

  const handleSubmit = async (e: Event) => {
    e.preventDefault();
    const client = getClient();
    if (!client || !config) return;

    const subject = subjectRef.current?.value.trim() || '';
    const message = messageRef.current?.value.trim() || '';

    if (!message) {
      setError('Please enter a message');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const result = await client.createConversation({
        org_id: config.orgId,
        org_name: config.orgName || '',
        user_id: config.userId || '',
        customer_name: config.userName,
        customer_email: config.userEmail,
        tier: 'standard',
        issue_category: category,
        severity,
        source_channel: 'web',
        subject: subject || `${category} - ${severity}`,
        message,
      });

      // Add to conversations list
      conversations.value = [result.conversation, ...conversations.value];

      // Navigate to the new conversation
      navigateToDetail(result.conversation.id);
    } catch (err) {
      setError('Failed to create conversation. Please try again.');
      console.error('Create conversation error:', err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form class="sb-new-conv" onSubmit={handleSubmit}>
      <div class="sb-field">
        <label class="sb-label">Subject</label>
        <input
          ref={subjectRef}
          class="sb-input"
          type="text"
          placeholder="Brief description of your issue"
          value={defaultSubject}
        />
      </div>

      <div class="sb-field-row">
        <div class="sb-field sb-field--half">
          <label class="sb-label">Category</label>
          <select
            class="sb-select"
            value={category}
            onChange={(e) => setCategory((e.target as HTMLSelectElement).value as IssueCategory)}
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>

        <div class="sb-field sb-field--half">
          <label class="sb-label">Severity</label>
          <select
            class="sb-select"
            value={severity}
            onChange={(e) => setSeverity((e.target as HTMLSelectElement).value as Severity)}
          >
            {SEVERITIES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div class="sb-field">
        <label class="sb-label">Message</label>
        <textarea
          ref={messageRef}
          class="sb-textarea"
          rows={4}
          placeholder="Describe your issue..."
          required
        />
      </div>

      {error && <div class="sb-error">{error}</div>}

      <div class="sb-form-actions">
        <button
          type="button"
          class="sb-btn sb-btn--ghost"
          onClick={navigateToList}
          disabled={submitting}
        >
          Cancel
        </button>
        <button type="submit" class="sb-btn sb-btn--primary" disabled={submitting}>
          {submitting ? 'Creating...' : 'Start Conversation'}
        </button>
      </div>
    </form>
  );
}
