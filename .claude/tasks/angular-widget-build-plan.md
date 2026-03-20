# Support Bridge Embeddable Chat Widget Build Plan

## Context

The Angular webapp (cyflare_ng_app) currently uses the Zoho ASAP widget (a floating chat bubble injected via script in `customer-layout.component.ts:591-604`). We are replacing it with a custom Support Bridge floating chat widget that connects to the same backend the casi-mobile app uses, keeping conversations fully in sync across platforms.

The widget is a **standalone embeddable script** that lives in the support-bridge repo, built with **Preact + TypeScript**, and loaded via `<script>` tag -- the same pattern as the Zoho widget it replaces. It is framework-agnostic and can be embedded in any webapp.

## Tech Stack

- **Preact** (~3KB gzipped) for reactive UI rendering
- **@preact/signals** for state management
- **TypeScript** for type safety
- **Vite** for bundling to a single JS file
- **CSS-in-JS or scoped CSS** to avoid style conflicts with host app
- Self-contained: handles its own auth, API calls, SSE, and rendering

## Embedding

```html
<!-- In the host app (e.g., cyflare_ng_app index.html or layout template) -->
<script
  src="https://support-bridge-production.up.railway.app/widget/v1/widget.js"
  data-org-id="123"
  defer>
</script>
```

The script self-mounts: creates its own root element, attaches to `document.body`, and renders the floating FAB. The host app does not need to know about Preact or any widget internals.

Auth: The widget needs a Cognito JWT to authenticate with the support-bridge API. Options:
- `data-token` attribute on the script tag (host app provides the token)
- `window.SupportBridge.init({ token })` JS API called by the host app after auth
- Cookie-based auth if same-origin

## Widget Behavior

### Floating Button (Collapsed State)
- Fixed-position chat icon button at bottom-right of viewport
- Badge showing count of "Awaiting You" conversations
- Click opens the widget panel

### Widget Panel (Expanded State)

**View 1: Conversation List**
```
+---------------------------------------+
| SOC Support                      [x]  |
|---------------------------------------|
| [Active] [Resolved] [Closed]         |
|---------------------------------------|
| Login Alert Investigation        2m   |
| HIGH  AWAITING YOU                    |
|---------------------------------------|
| VPN Connection Issue            1h    |
| MEDIUM                                |
|---------------------------------------|
|                                       |
|          [+ New Conversation]         |
+---------------------------------------+
```

- Tabbed list (Active / Resolved / Closed)
- Each row: subject, severity badge, "awaiting you" badge, relative time
- Click row navigates to conversation detail view
- "New Conversation" button

**View 2: Conversation Detail (Chat)**
```
+---------------------------------------+
| [<] Login Alert Investigation    [x]  |
| Active  |  HIGH                       |
|---------------------------------------|
|     --- Mar 18, 2026 ---              |
|                                       |
| [Avatar] Analyst Name                 |
| We're investigating the alert...      |
|                                       |
|          Your message here     [you]  |
|                                       |
|---------------------------------------|
| [Type a message...        ] [Send]    |
+---------------------------------------+
```

- Back arrow returns to list view
- Chat bubbles: customer (right), analyst (left), system (centered)
- Message input with Enter to send
- Status banner for resolved/closed states
- Auto-scroll on new messages

**View 3: New Conversation (Form)**
- Subject, category dropdown, severity dropdown, message textarea
- Optional pre-fill from case context
- Submit creates conversation and navigates to detail view

**CSAT Dialog**: Shown after closing a conversation (3-face rating + skip)

### Panel Sizing
- Width: ~400px fixed
- Height: ~550-600px (or `calc(100vh - 120px)` with max-height)
- Position: fixed bottom-right, above the floating button
- Shadow and rounded corners for floating card feel
- Smooth slide-up/fade animation on open/close

## Project Structure (in support-bridge repo)

```
widget/
  package.json                    # Preact, @preact/signals, vite, typescript
  tsconfig.json
  vite.config.ts                  # Builds to single widget.js bundle
  src/
    index.ts                      # Entry: self-mount, read config from script tag
    widget.tsx                    # Root component: FAB + panel shell + view routing
    api/
      client.ts                   # HTTP client for support-bridge API
      sse.ts                      # SSE client with reconnect
      types.ts                    # API request/response types
    state/
      store.ts                    # Preact signals: conversations, messages, UI state
    components/
      fab.tsx                     # Floating action button with badge
      panel.tsx                   # Panel container with header + close
      conversation-list.tsx       # Tabbed conversation list
      conversation-detail.tsx     # Chat thread + input orchestration
      message-bubble.tsx          # Single message (customer/analyst/system)
      message-input.tsx           # Compose bar
      new-conversation.tsx        # New conversation form
      csat-feedback.tsx           # 3-face rating dialog
      status-banner.tsx           # Resolved/closed action bar
    styles/
      widget.css                  # Scoped styles (prefixed with .sb- namespace)
    utils/
      time.ts                     # Relative time formatting
      status.ts                   # Backend status mapping (7 -> 4)
```

## Data Models (`api/types.ts`)

Port from Flutter `lib/support_bridge/models.dart`:

```typescript
export type BackendStatus = 'new'|'queued'|'assigned'|'waiting_customer'|'waiting_soc'|'resolved'|'closed';
export type CustomerStatus = 'active'|'awaitingYou'|'resolved'|'closed';

export type MessageSender = 'customer'|'analyst'|'system';
export type FeedbackRating = 1|2|3;
export type Severity = 'critical'|'high'|'medium'|'low';
export type IssueCategory = 'incident'|'request'|'question'|'problem';

export interface SbConversation { ... }
export interface SbMessage { ... }
export interface SbFeedback { ... }
export interface CreateConversationRequest { ... }
```

## State Management (`state/store.ts`)

Uses @preact/signals for reactive state:

```typescript
export const conversations = signal<SbConversation[]>([]);
export const messages = signal<SbMessage[]>([]);
export const isOpen = signal(false);
export const currentView = signal<'list'|'detail'|'new'|'csat'>('list');
export const selectedConversationId = signal<string|null>(null);
export const isLoading = signal(false);
export const activeTab = signal<'active'|'resolved'|'closed'>('active');

export const awaitingYouCount = computed(() =>
  conversations.value.filter(c => c.status === 'awaitingYou').length
);
```

## API Client (`api/client.ts`)

```typescript
class SupportBridgeClient {
  constructor(private baseUrl: string, private getToken: () => string) {}

  getConversations(): Promise<SbConversation[]>
  getConversation(id: string): Promise<SbConversation>
  createConversation(req: CreateConversationRequest): Promise<{conversation: SbConversation, message: SbMessage}>
  getMessages(convId: string): Promise<SbMessage[]>
  sendMessage(convId: string, body: string): Promise<SbMessage>
  closeConversation(convId: string): Promise<SbConversation>
  reopenConversation(convId: string): Promise<SbConversation>
  submitFeedback(convId: string, rating: FeedbackRating): Promise<SbFeedback>
}
```

- All POSTs include `Idempotency-Key: {crypto.randomUUID()}`
- `source_channel: 'web'`
- `Authorization: Bearer {token}` on all requests

## SSE Client (`api/sse.ts`)

- Uses native `EventSource` or polyfill for custom headers
- `connect(conversationId): void` with exponential backoff reconnect (2s-30s)
- Handles: `message.created`, `conversation.status_changed`, `conversation.closed`
- Ignores: `heartbeat`
- `disconnect()` for cleanup

## Serving the Widget

The Django backend serves the built widget bundle:
- `GET /widget/v1/widget.js` returns the Vite-built JS bundle
- Add a Django view or use `whitenoise` / static files to serve it
- Alternatively, serve from a CDN or the Railway deployment directly

## Integration with Angular App

In `customer-layout.component.ts`:
- Replace `addZohoScript()` with a script that loads the support-bridge widget
- **Keep Zoho during development**: both widgets side-by-side for comparison
- Remove Zoho only after the support-bridge widget is fully verified

```typescript
addSupportBridgeWidget(): void {
  const script = document.createElement('script');
  script.src = `${environment.supportBridgeUrl}/widget/v1/widget.js`;
  script.defer = true;
  // Pass auth token via JS API after script loads
  script.onload = () => {
    (window as any).SupportBridge?.init({
      token: this.user.access_token,
      orgId: this.user.organization_id,
      userName: `${this.user.first_name} ${this.user.last_name}`,
      userEmail: this.user.email,
    });
  };
  document.body.appendChild(script);
}
```

### Environment Config
Add `supportBridgeUrl` to all Angular environment files:
- All envs: `'https://support-bridge-production.up.railway.app'`

## Implementation Phases

### Phase 1: Foundation
1. Scaffold `widget/` project: package.json, vite.config.ts, tsconfig.json
2. Create `api/types.ts`: port interfaces and status mapping from Flutter
3. Create `api/client.ts`: HTTP client for all support-bridge endpoints
4. Create `state/store.ts`: Preact signals for all widget state
5. Create `src/index.ts`: self-mount entry point reading config from script tag

### Phase 2: Widget Shell + List View
6. Create `widget.tsx`: root component with FAB + panel container
7. Create `fab.tsx`: floating button with badge
8. Create `panel.tsx`: panel container with header/close
9. Create `conversation-list.tsx`: tabbed list with styled rows
10. Create `styles/widget.css`: scoped styles

### Phase 3: Chat Detail View
11. Create `message-bubble.tsx`: three bubble styles
12. Create `message-input.tsx`: compose bar
13. Create `conversation-detail.tsx`: thread + input + auto-scroll
14. Create `status-banner.tsx`: resolved/closed states

### Phase 4: New Conversation + CSAT
15. Create `new-conversation.tsx`: form with dropdowns
16. Create `csat-feedback.tsx`: 3-face rating
17. Wire close -> CSAT -> closed flow
18. Wire reopen flow

### Phase 5: Real-Time (SSE)
19. Create `api/sse.ts`: EventSource with reconnect
20. Integrate into conversation-detail (5s polling fallback)
21. Message deduplication logic

### Phase 6: Django Serving + Angular Integration
22. Add Django URL/view to serve `widget.js` bundle
23. Add `supportBridgeUrl` to Angular environment files
24. Replace Zoho script in `customer-layout.component.ts` with widget loader
25. Keep Zoho alongside during testing

### Phase 7: Ticket/Case Integration (deferred)
26. JS API: `window.SupportBridge.openWithCase(caseId, subject)`
27. Talk-to-soc button calls this API from the ticket detail component

### Phase 8: End-to-End Verification
28. Full e2e test with live backend
29. Verify cross-platform sync (mobile <-> web)
30. Remove Zoho widget

## Verification

- Vite build produces a single `widget.js` bundle
- Loading the script on any HTML page shows the floating FAB
- Click opens widget panel with conversation list from live API
- Tab switching filters correctly (Active/Resolved/Closed)
- Selecting a conversation shows chat detail with bubbles
- Sending a message appears in thread
- Back arrow returns to list
- "New Conversation" form creates and navigates to detail
- Close -> CSAT -> closed flow works
- Badge shows awaiting-you count
- SSE events update chat in real-time
- Conversations sync between web widget and mobile app
