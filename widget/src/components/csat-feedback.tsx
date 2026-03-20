/**
 * CSAT feedback dialog with 3-face rating (Bad / OK / Great) + Skip.
 * Shown after closing a conversation.
 */

import { useState } from 'preact/hooks';
import { navigateToList, selectedConversationId } from '../state/store';
import { getClient } from '../services';
import type { FeedbackRating } from '../api/types';

const RATINGS: { value: FeedbackRating; emoji: string; label: string }[] = [
  { value: 1, emoji: '\u{1F61E}', label: 'Bad' },
  { value: 2, emoji: '\u{1F610}', label: 'OK' },
  { value: 3, emoji: '\u{1F60A}', label: 'Great' },
];

export function CsatFeedback() {
  const convId = selectedConversationId.value;
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleRate = async (rating: FeedbackRating) => {
    const client = getClient();
    if (!client || !convId) return;

    setSubmitting(true);
    try {
      await client.submitFeedback(convId, rating);
      setSubmitted(true);
      setTimeout(navigateToList, 1500);
    } catch (err) {
      console.error('Failed to submit feedback:', err);
      navigateToList();
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div class="sb-csat">
        <div class="sb-csat-thanks">
          <span class="sb-csat-check">&#x2714;</span>
          <p>Thank you for your feedback!</p>
        </div>
      </div>
    );
  }

  return (
    <div class="sb-csat">
      <p class="sb-csat-prompt">How was your support experience?</p>
      <div class="sb-csat-faces">
        {RATINGS.map((r) => (
          <button
            key={r.value}
            class="sb-csat-face"
            onClick={() => handleRate(r.value)}
            disabled={submitting}
            aria-label={r.label}
          >
            <span class="sb-csat-emoji">{r.emoji}</span>
            <span class="sb-csat-label">{r.label}</span>
          </button>
        ))}
      </div>
      <button class="sb-btn sb-btn--link sb-csat-skip" onClick={navigateToList}>
        Skip
      </button>
    </div>
  );
}
