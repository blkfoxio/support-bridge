/**
 * SSE client for real-time conversation updates.
 * Mirrors the Flutter SseClient with exponential backoff reconnect.
 */

import type { SseEvent } from './types';

export type SseEventHandler = (event: SseEvent) => void;

export class SupportBridgeSse {
  private baseUrl: string;
  private getToken: () => string;
  private eventSource: EventSource | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 2000;
  private maxReconnectDelay = 30000;
  private handler: SseEventHandler | null = null;
  private conversationId: string | null = null;

  constructor(baseUrl: string, getToken: () => string) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.getToken = getToken;
  }

  connect(conversationId: string, handler: SseEventHandler): void {
    this.disconnect();
    this.conversationId = conversationId;
    this.handler = handler;
    this.reconnectDelay = 2000;
    this.doConnect();
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.handler = null;
    this.conversationId = null;
  }

  private doConnect(): void {
    if (!this.conversationId || !this.handler) return;

    const token = this.getToken();
    // Note: native EventSource doesn't support custom headers.
    // For auth, we pass the token as a query param. The backend
    // should accept ?token= as an alternative to the Authorization header,
    // or we use a polyfill. For now, use query param approach.
    const url = `${this.baseUrl}/api/v1/customer/stream/?conversation_id=${this.conversationId}&token=${encodeURIComponent(token)}`;

    const es = new EventSource(url);
    this.eventSource = es;

    es.onopen = () => {
      // Reset backoff on successful connection
      this.reconnectDelay = 2000;
    };

    es.onmessage = (event) => {
      this.handleRawEvent('message', event);
    };

    // Listen for named event types
    for (const eventType of [
      'message.created',
      'conversation.status_changed',
      'conversation.closed',
    ]) {
      es.addEventListener(eventType, ((event: MessageEvent) => {
        this.handleRawEvent(eventType, event);
      }) as EventListener);
    }

    es.onerror = () => {
      es.close();
      this.eventSource = null;
      this.scheduleReconnect();
    };
  }

  private handleRawEvent(eventType: string, event: MessageEvent): void {
    if (!this.handler) return;

    // Skip heartbeats
    if (eventType === 'heartbeat') return;

    try {
      const data = JSON.parse(event.data);
      this.handler({
        eventType,
        id: event.lastEventId || undefined,
        data,
      });
    } catch {
      // Ignore unparseable events
    }
  }

  private scheduleReconnect(): void {
    if (!this.conversationId || !this.handler) return;

    this.reconnectTimer = setTimeout(() => {
      this.doConnect();
    }, this.reconnectDelay);

    // Exponential backoff with jitter
    this.reconnectDelay = Math.min(
      this.reconnectDelay * 2 + Math.random() * 1000,
      this.maxReconnectDelay,
    );
  }
}
