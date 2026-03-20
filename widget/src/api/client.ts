/**
 * HTTP client for the Support Bridge customer API.
 * Mirrors the Flutter SupportBridgeService API calls.
 */

import type {
  CreateConversationRequest,
  CreateConversationResponse,
  FeedbackRating,
  RawConversation,
  RawMessage,
  SbConversation,
  SbFeedback,
  SbMessage,
} from './types';
import { parseConversation, parseMessage } from './types';

export class SupportBridgeClient {
  private baseUrl: string;
  private getToken: () => string;

  constructor(baseUrl: string, getToken: () => string) {
    // Strip trailing slash
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.getToken = getToken;
  }

  private get apiBase(): string {
    return `${this.baseUrl}/api/v1/customer`;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
  ): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${this.getToken()}`,
      ...(options.headers as Record<string, string> || {}),
    };

    // Add idempotency key for mutations
    if (options.method && options.method !== 'GET') {
      headers['Idempotency-Key'] = crypto.randomUUID();
    }

    const response = await fetch(`${this.apiBase}${path}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new Error(
        `Support Bridge API error: ${response.status} ${response.statusText} - ${body}`,
      );
    }

    return response.json() as Promise<T>;
  }

  // --- Conversations ---

  async getConversations(): Promise<SbConversation[]> {
    const raw = await this.request<RawConversation[]>('/conversations/');
    return raw.map(parseConversation);
  }

  async getConversation(id: string): Promise<SbConversation> {
    const raw = await this.request<RawConversation>(`/conversations/${id}/`);
    return parseConversation(raw);
  }

  async createConversation(
    req: CreateConversationRequest,
  ): Promise<{ conversation: SbConversation; message: SbMessage }> {
    const raw = await this.request<CreateConversationResponse>(
      '/conversations/',
      {
        method: 'POST',
        body: JSON.stringify(req),
      },
    );
    return {
      conversation: parseConversation(raw.conversation),
      message: parseMessage(raw.message),
    };
  }

  // --- Messages ---

  async getMessages(conversationId: string): Promise<SbMessage[]> {
    const raw = await this.request<RawMessage[]>(
      `/conversations/${conversationId}/messages/`,
    );
    return raw.map(parseMessage);
  }

  async sendMessage(
    conversationId: string,
    body: string,
  ): Promise<SbMessage> {
    const raw = await this.request<RawMessage>(
      `/conversations/${conversationId}/messages/`,
      {
        method: 'POST',
        body: JSON.stringify({ message: body }),
      },
    );
    return parseMessage(raw);
  }

  // --- Lifecycle ---

  async closeConversation(conversationId: string): Promise<SbConversation> {
    const raw = await this.request<RawConversation>(
      `/conversations/${conversationId}/close/`,
      { method: 'POST', body: '{}' },
    );
    return parseConversation(raw);
  }

  async reopenConversation(conversationId: string): Promise<SbConversation> {
    const raw = await this.request<RawConversation>(
      `/conversations/${conversationId}/reopen/`,
      { method: 'POST', body: '{}' },
    );
    return parseConversation(raw);
  }

  // --- Feedback ---

  async submitFeedback(
    conversationId: string,
    rating: FeedbackRating,
  ): Promise<SbFeedback> {
    return this.request<SbFeedback>(
      `/conversations/${conversationId}/feedback/`,
      {
        method: 'POST',
        body: JSON.stringify({ rating }),
      },
    );
  }
}
