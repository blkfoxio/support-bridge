/**
 * Support Bridge API types.
 * Ported from Flutter: casi-mobile/lib/support_bridge/models.dart
 */

// --- Backend statuses (7-state machine) ---

export type BackendConversationStatus =
  | 'new'
  | 'queued'
  | 'assigned'
  | 'waiting_customer'
  | 'waiting_soc'
  | 'resolved'
  | 'closed';

// --- Customer-facing statuses (4 states) ---

export type CustomerStatus = 'active' | 'awaitingYou' | 'resolved' | 'closed';

/**
 * Map backend 7-status to customer-facing 4-status.
 * Same logic as Flutter SbConversationStatus.fromBackend().
 */
export function mapBackendStatus(raw: string | null | undefined): CustomerStatus {
  switch (raw) {
    case 'new':
    case 'queued':
    case 'assigned':
    case 'waiting_soc':
      return 'active';
    case 'waiting_customer':
      return 'awaitingYou';
    case 'resolved':
      return 'resolved';
    case 'closed':
      return 'closed';
    // Legacy values
    case 'open':
    case 'active':
      return 'active';
    default:
      return 'active';
  }
}

export function isInteractive(status: CustomerStatus): boolean {
  return status !== 'closed';
}

export function isTerminal(status: CustomerStatus): boolean {
  return status === 'resolved' || status === 'closed';
}

// --- Enums ---

export type MessageSender = 'customer' | 'analyst' | 'system';
export type FeedbackRating = 1 | 2 | 3;
export type Severity = 'critical' | 'high' | 'medium' | 'low';
export type IssueCategory = 'incident' | 'request' | 'question' | 'problem';

// --- Data interfaces ---

export interface SbConversation {
  id: string;
  customer_org_id: string;
  customer_org_name: string;
  customer_name: string;
  customer_email: string;
  subject: string;
  status: CustomerStatus;
  rawStatus: BackendConversationStatus;
  severity: string;
  issue_category: string;
  tier: string;
  opened_at: string;
  last_message_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
}

export interface SbMessage {
  id: string;
  conversation_id: string;
  actor_type: MessageSender;
  sender_name: string;
  body_plain: string;
  message_type: string;
  created_at: string;
}

export interface SbFeedback {
  id: number;
  conversation_id: string;
  rating: FeedbackRating;
  created_at: string;
}

export interface CreateConversationRequest {
  org_id: string;
  org_name: string;
  user_id: string;
  customer_name: string;
  customer_email: string;
  tier: string;
  issue_category: string;
  severity: string;
  source_channel: 'web';
  subject: string;
  message: string;
}

export interface CreateConversationResponse {
  conversation: RawConversation;
  message: RawMessage;
}

// --- Raw API response shapes (before mapping) ---

export interface RawConversation {
  id: string;
  customer_org_id: string;
  customer_org_name: string;
  customer_name: string;
  customer_email: string;
  subject: string;
  status: string;
  severity: string;
  issue_category: string;
  tier: string;
  queue_key: string;
  roam_thread_key: string;
  opened_at: string;
  assigned_at: string | null;
  first_response_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  last_message_at: string | null;
}

export interface RawMessage {
  id: string;
  conversation_id: string;
  actor_type: string;
  actor_id: string;
  sender_name: string;
  direction: string;
  body_plain: string;
  message_type: string;
  created_at: string;
}

// --- SSE ---

export interface SseEvent {
  eventType: string;
  id?: string;
  data: Record<string, unknown>;
}

// --- Widget config ---

export interface WidgetConfig {
  token: string;
  orgId: string;
  orgName?: string;
  userName: string;
  userEmail: string;
  userId?: string;
  baseUrl?: string;
}

// --- Mapping helpers ---

const UUID_RE = /^[A-Za-z]?-?[0-9a-f]{8}-[0-9a-f]{4}-/i;

function resolveSenderName(senderName: string | null | undefined, actorId?: string): string {
  if (senderName && senderName.length > 0 && !UUID_RE.test(senderName)) {
    return senderName;
  }
  return 'Cyflare Support';
}

export function parseConversation(raw: RawConversation): SbConversation {
  return {
    id: raw.id,
    customer_org_id: raw.customer_org_id,
    customer_org_name: raw.customer_org_name,
    customer_name: raw.customer_name,
    customer_email: raw.customer_email,
    subject: raw.subject,
    status: mapBackendStatus(raw.status),
    rawStatus: raw.status as BackendConversationStatus,
    severity: raw.severity,
    issue_category: raw.issue_category,
    tier: raw.tier,
    opened_at: raw.opened_at,
    last_message_at: raw.last_message_at,
    resolved_at: raw.resolved_at,
    closed_at: raw.closed_at,
  };
}

export function parseMessage(raw: RawMessage): SbMessage {
  let sender: MessageSender;
  switch (raw.actor_type) {
    case 'customer':
      sender = 'customer';
      break;
    case 'analyst':
      sender = 'analyst';
      break;
    default:
      sender = 'system';
  }

  return {
    id: raw.id,
    conversation_id: raw.conversation_id,
    actor_type: sender,
    sender_name: resolveSenderName(raw.sender_name, raw.actor_id),
    body_plain: raw.body_plain,
    message_type: raw.message_type,
    created_at: raw.created_at,
  };
}
