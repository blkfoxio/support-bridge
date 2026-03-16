1. PRD v2
   Product name

Cyflare Support Bridge API

Product summary

A Django-based, API-first support orchestration service that lets customers chat from the Cyflare mobile app while SOC analysts work from Roam, and exposes internal APIs for queueing, assignment, KPI reporting, group management, and transcript operations for future embedding into the Cloudflare One application.

Why this product exists

Today, customer chat and SOC handling are split across different systems. That creates friction in analyst workflows, weakens reporting, and makes future internal tooling harder.

This product creates one support backend that:

keeps customer chat inside Cyflare surfaces

keeps analysts inside Roam

centralizes queueing, routing, and KPIs in Cyflare-owned infrastructure

enables a later admin UI without reworking backend logic

Product goals
Primary goals

validate mobile-first customer chat from the Flutter iOS app

let SOC analysts respond entirely from Roam

expose operational capabilities through APIs before any admin UI exists

make the Django service the system of record for support state and metrics

Secondary goals

support multiple queues and transfers

support future admin embedding inside Cloudflare One

establish a clean base for transcripts, SLA tracking, and analyst reporting

Non-goals for prototype

polished admin UI

full omnichannel support

advanced workforce management

AI triage/copilot

deep CRM/ticketing sync

full attachment system unless required for a critical use case

Users
External

customer admins

customer end users

mobile app users

Internal

SOC analyst

SOC manager

ops admin

engineering admin

Core user jobs
Customer

start support chat from the mobile app

receive live analyst replies

understand whether the conversation is open, waiting, or closed

SOC analyst

see incoming customer issues in Roam

reply in Roam threads

claim, transfer, and close conversations

avoid switching into another chat tool

Ops/admin

inspect queues and backlog

monitor KPIs and SLA risk

manage queue/group mappings

export transcripts and audit histories

Success metrics
Prototype success

customer can complete a full conversation from iOS app

analyst can handle that conversation from Roam

message sync succeeds at 95 percent or better

median sync latency is under 3 seconds in normal conditions

at least one queue and one transfer flow works end to end

KPI endpoints return first response time, resolution time, queue depth, and handled counts

v1 success

reduced analyst tool switching

reduced first response time

reduced queue assignment delays

reliable transcript retention

usable admin API for future embedded Cloudflare One tooling

Product principles

API first

mobile first for customer validation

Roam is workspace, not source of truth

backend owns routing, assignment, SLA, and metrics

every operational action should be possible via API

2. Scope for the first prototype
   In scope

Flutter iOS customer chat flow

Django REST API

SSE for live customer updates

one to two queues

Roam queue-group integration

analyst replies from Roam

claim, assign, transfer, close via API

KPI summary endpoints

transcript retrieval endpoint

audit logging and idempotent webhook handling

Out of scope

web customer chat

embedded admin UI

advanced attachments

push notifications

CSAT

AI features

workforce scheduling

3. Product requirements
   3.1 Customer chat

The mobile app must be able to:

create a conversation

send messages

receive live analyst replies

fetch history

show typing indicator state if available

close or reopen a conversation

recover conversation state after reconnect/app restart

3.2 Analyst workflow

Analysts must be able to:

see customer conversations appear in Roam queue groups

reply inside the corresponding thread

claim or assign work

transfer work between queues

close a conversation with reason/tag metadata

3.3 Operations/API requirements

The API must support:

queue list/detail

active and historical conversation retrieval

queue metrics

assignment and transfer actions

group-to-queue mapping

routing rule management

transcript retrieval

audit event retrieval

3.4 Reporting/KPIs

The backend must compute:

queue depth

first response time

time to assignment

resolution time

transfer count

reopen count

message volume by hour/day

analyst handled count

SLA breached / near breach counts

3.5 Reliability

Must include:

idempotency for customer send/create

idempotent webhook ingestion

retry with backoff for Roam API failures

audit logging

failure visibility

replay-safe event processing

3.6 Security

Must include:

authenticated customer API access

tenant-aware authorization

secret-managed Roam credentials

signed or otherwise verifiable webhook intake where possible

least-privilege ops/admin permissions

retention-aware transcript storage

4. Recommended product model
   Core model

one queue in your app maps to one Roam group

one conversation maps to one Roam thread

conversation.id is your canonical identifier

conversation.id is reused as Roam threadKey

all canonical state lives in your Django/Postgres system

Roam is a mirrored analyst-facing workspace

Roam’s threadKey is explicitly intended for external integrations that want a stable identifier for threaded posting, which makes it a strong fit for your conversation model.

Why this model

It avoids:

creating one Roam group per customer

exploding group count

burying business state inside Roam

needing a later migration when admin APIs/UI get more sophisticated

5. Django technical spec
   Stack

Python 3.12

Django

Django REST Framework

drf-spectacular

PostgreSQL

Redis

Celery

ASGI deployment

pytest

Why Django here

Django keeps your backend aligned with the rest of your app stack, supports async under ASGI, and supports streaming responses suitable for SSE prototypes when served correctly. Django’s docs also note important caveats around StreamingHttpResponse, including middleware limitations and the need for async iterators under ASGI.

Service boundaries
conversations

conversation lifecycle and status

messaging

message creation, persistence, fanout, transcript assembly

routing

queue selection and rule evaluation

queues

queue config, SLA policies, mapping to Roam groups

analytics

KPI computation and aggregate queries

integrations_roam

Roam API client, webhook ingestion, delivery sync

customer_api

mobile-facing endpoints

ops_api

internal operational endpoints

admin_config

routing and queue/group configuration endpoints

audit

event log and traceability

6. Suggested Django app structure
   cyflare_support_bridge/
   manage.py
   pyproject.toml
   config/
   settings/
   base.py
   local.py
   prod.py
   urls.py
   asgi.py
   celery.py
   apps/
   conversations/
   messaging/
   routing/
   queues/
   analytics/
   integrations_roam/
   customer_api/
   ops_api/
   admin_config/
   audit/
   common/
   auth/
   permissions/
   sse/
   types/
   utils/
   tests/
   scripts/
   docs/
7. Domain model
   Queue

Fields:

id

key

name

active

priority_order

sla_first_response_seconds

sla_resolution_seconds

created_at

updated_at

QueueGroupMapping

Fields:

id

queue_id

roam_group_id

roam_group_name

active

created_at

updated_at

Conversation

Fields:

id (UUID)

customer_org_id

customer_user_id

source_channel (mobile_ios, later web, mobile_android)

status (new, queued, assigned, waiting_customer, waiting_soc, resolved, closed)

priority

severity

issue_category

queue_id

assigned_analyst_id nullable

roam_thread_key

opened_at

assigned_at nullable

first_response_at nullable

resolved_at nullable

closed_at nullable

last_message_at

created_at

updated_at

Message

Fields:

id

conversation_id

actor_type (customer, analyst, system)

actor_id

direction (inbound, outbound)

source (customer_api, roam_webhook, internal)

external_message_id nullable

body_plain

body_markdown nullable

message_type (text, system_note, status)

created_at

delivered_at nullable

failed_at nullable

metadata jsonb

Assignment

Fields:

id

conversation_id

analyst_id

assigned_by

reason

assigned_at

ended_at nullable

Tag / ConversationTag

Standard tag mapping for disposition and reporting.

RoutingRule

Fields:

id

name

active

match_json

target_queue_id

priority

created_at

updated_at

AnalystProfile

Fields:

id

external_user_id

display_name

email

active

default_queue_id nullable

SlaPolicy

Fields:

id

queue_id

first_response_seconds

resolution_seconds

active

EventLog

Fields:

id

event_type

idempotency_key unique

source

conversation_id nullable

payload jsonb

processed_at nullable

created_at

8. API design
   Customer API

Prefix: /api/v1/customer/

POST /conversations

Create a conversation and initial message.

Request:

{
"org_id": "org_123",
"user_id": "user_456",
"tier": "enterprise",
"issue_category": "incident",
"severity": "high",
"source_channel": "mobile_ios",
"message": "We are seeing failed logins across multiple tenants."
}

Response:

{
"conversation": {
"id": "uuid",
"status": "queued",
"queue_key": "soc-triage",
"roam_thread_key": "uuid",
"opened_at": "2026-03-15T14:20:00Z"
},
"message": {
"id": "msg_1",
"actor_type": "customer",
"body_plain": "We are seeing failed logins across multiple tenants.",
"created_at": "2026-03-15T14:20:00Z"
}
}
GET /conversations/{id}

Return conversation state.

GET /conversations/{id}/messages

Return timeline.

POST /conversations/{id}/messages

Append a customer message.

POST /conversations/{id}/typing

Set ephemeral typing state.

POST /conversations/{id}/close

Close customer-visible conversation.

POST /conversations/{id}/reopen

Reopen if allowed.

GET /stream?conversation_id={id}

SSE endpoint for live events.

Ops API

Prefix: /api/v1/ops/

GET /queues

List queues with counts.

GET /queues/{id}

Queue detail.

GET /queues/{id}/metrics

Queue KPI summary.

GET /conversations

Filterable list:

queue

status

severity

assigned_analyst

opened_after

opened_before

GET /conversations/{id}

Ops detail.

POST /conversations/{id}/claim

Claim conversation.

POST /conversations/{id}/assign

Assign to analyst.

POST /conversations/{id}/transfer

Transfer queue.

POST /conversations/{id}/resolve

Resolve conversation.

POST /conversations/{id}/close

Close conversation.

POST /conversations/{id}/tags

Apply tags.

GET /transcripts/{conversation_id}

Return transcript DTO or export payload.

Admin/config API

Prefix: /api/v1/admin/

GET /routing-rules
POST /routing-rules
PATCH /routing-rules/{id}
GET /queue-group-mappings
POST /queue-group-mappings
PATCH /queue-group-mappings/{id}
GET /analysts
GET /audit/events
Webhooks
POST /webhooks/roam/chat-message
POST /webhooks/roam/reaction

Roam’s webhook/event behavior matters here because your app must be a participant in the relevant chat/group to receive those events.

9. Event model
   SSE events

Use these event types:

message.created

conversation.updated

typing.started

typing.stopped

conversation.closed

heartbeat

Example:

event: message.created
id: evt_123
data: {"conversation_id":"uuid","message":{"id":"msg_9","actor_type":"analyst","body_plain":"We are investigating now.","created_at":"2026-03-15T14:21:10Z"}}
Idempotency
Customer endpoints

Accept:

Idempotency-Key header on create/send

Roam webhook ingestion

Use:

provider event id if available

otherwise derive deterministic key from payload hash + timestamp bucket + source

10. Routing logic for prototype

Ordered rules:

severity = critical -> incident-response

issue_category = billing -> billing-support

tier = enterprise -> enterprise-soc

default -> soc-triage

Prototype should keep this rules engine simple and table-driven.

11. KPI definitions
    first_response_time_seconds

first analyst message timestamp - opened_at

time_to_assignment_seconds

assigned_at - opened_at

resolution_time_seconds

resolved_at - opened_at

queue_depth

count of open conversations by queue/status

transfer_rate

transferred conversations / total conversations in period

reopen_rate

reopened conversations / closed conversations in period

handled_count

count of conversations with analyst ownership in period

For prototype, compute these from Postgres directly. If volume grows, add rollups/materialized tables later.

12. Mobile-first prototype plan
    Flutter iOS first screens

start chat

active timeline

typing indicator

closed state

reopen/new chat

Mobile integration principles

no Roam concepts in mobile contracts

all mobile state driven by Cyflare API DTOs

optimistic send with retry

reconnect-safe SSE subscription

transcript/history loaded via paginated REST

A Flutter SSE client library is available and documents subscribe/unsubscribe support for SSE streams, which is enough for a first-pass mobile prototype.

13. Operational risks
    Roam alpha risk

Roam’s Chat API is alpha/developer preview, so expect some interface or payload evolution risk. Keep Roam integration behind a narrow adapter layer.

SSE tradeoff

SSE is simpler for prototype, but Django’s docs note that streaming responses have middleware and response-header tradeoffs, so keep the SSE implementation focused and isolated.

Mobile background behavior

SSE is good for foreground prototype behavior. Background delivery will likely need APNs later.

14. Recommended prototype acceptance criteria

Prototype is complete when:

iOS app can open a conversation

first customer message creates a conversation in Django

Django routes to a queue and posts to the mapped Roam group/thread

analyst replies in Roam thread

Django ingests webhook and pushes reply to iOS app live

ops API can claim, assign, transfer, and close

KPI endpoints return queue depth, first response time, and resolution time

duplicate webhook deliveries do not create duplicate messages

15. Claude Code task pack
    Task 1: scaffold the Django service
    Create a Django-based API-first service named cyflare_support_bridge.

Tech requirements:

- Python 3.12
- Django
- Django REST Framework
- drf-spectacular
- PostgreSQL
- Redis
- Celery
- pytest
- Docker Compose
- ASGI-ready configuration
- structured JSON logging
- .env.example

Project structure:

- config/settings/base.py, local.py, prod.py
- Django apps:
  conversations
  messaging
  routing
  queues
  analytics
  integrations_roam
  customer_api
  ops_api
  admin_config
  audit
- common modules for auth, permissions, sse, utils

Implement:

- /health
- /version
- /api/schema/
- /api/docs/
- URL namespaces for:
  /api/v1/customer/
  /api/v1/ops/
  /api/v1/admin/
  /webhooks/roam/

Do not implement business logic yet.
Focus on clean architecture, settings separation, and a project that boots successfully with Docker Compose.
Task 2: implement domain models and migrations
Implement Django models, migrations, and Django admin registration for:

- Queue
- QueueGroupMapping
- Conversation
- Message
- Assignment
- Tag
- ConversationTag
- RoutingRule
- AnalystProfile
- SlaPolicy
- EventLog

Requirements:

- UUID primary keys where appropriate
- created_at and updated_at timestamps
- database indexes for queue/status, conversation timestamps, and event idempotency
- unique constraint on EventLog.idempotency_key
- enums for conversation status, actor type, source channel, message direction
- factories using factory-boy
- pytest model tests

Seed data:

- soc-triage
- incident-response
- billing-support
- enterprise-soc
  Task 3: define API contracts first
  Implement explicit DRF serializers, request/response objects, and drf-spectacular schema annotations for:

Customer API:

- create conversation
- get conversation
- list messages
- send message
- typing
- close
- reopen

Ops API:

- list queues
- queue detail
- queue metrics
- list conversations
- conversation detail
- claim
- assign
- transfer
- resolve
- close
- tag apply

Admin API:

- routing rules CRUD
- queue-group mappings CRUD
- analysts list
- audit event list

Requirements:

- every endpoint has example request/response payloads
- OpenAPI schema is clean and grouped by tag
- use explicit serializers instead of generic ModelSerializer where it improves clarity
  Task 4: build the Roam integration client
  Create a Python client module for the Roam Chat API and related webhook setup workflows.

Implement methods:

- post_message
- get_chat_history
- list_chats
- send_typing
- create_group
- list_group_members
- add_group_members
- list_users
- lookup_user
- token_info
- subscribe_webhook
- unsubscribe_webhook

Requirements:

- bearer token auth
- retries with exponential backoff on 429 and 5xx
- support threadKey when posting messages
- custom exception hierarchy
- pydantic or dataclass-based typed response parsing
- pytest unit tests with mocked HTTP responses

Keep this client isolated so Roam API alpha changes are easy to absorb later.
Task 5: implement conversation creation and routing
Implement the customer conversation creation flow.

Input fields:

- org_id
- user_id
- tier
- issue_category
- severity
- source_channel
- message

Behavior:

- evaluate routing rules in priority order
- pick target queue
- load queue to Roam group mapping
- create Conversation and initial Message atomically
- set roam_thread_key = conversation UUID
- post root message to Roam using threadKey
- persist returned external metadata
- append EventLog entries
- return a clean customer DTO

Also implement:

- send customer message to an existing conversation
- update last_message_at
- transition waiting state
- support Idempotency-Key header on create and send
  Task 6: implement Roam webhook ingestion
  Implement webhook endpoints for:
- /webhooks/roam/chat-message
- /webhooks/roam/reaction

Requirements:

- persist raw webhook payloads into EventLog
- derive or use an idempotency key
- reject duplicates safely
- map inbound Roam replies back to Conversation using queue/group mapping plus thread metadata
- create Message rows for analyst replies
- ignore bot-authored echoes to prevent loops
- set first_response_at when first analyst message arrives
- publish a customer-visible event for SSE delivery
- capture unknown payloads safely without crashing the request

Include integration tests for duplicate delivery and bad payload handling.
Task 7: implement SSE for mobile clients
Implement an ASGI-compatible SSE endpoint for customer conversation updates.

Endpoint:

- GET /api/v1/customer/stream/?conversation_id=<uuid>

Requirements:

- authenticated customer can subscribe only to their own conversation
- stream event types:
  message.created
  conversation.updated
  typing.started
  typing.stopped
  conversation.closed
  heartbeat
- use Redis pub/sub or a similarly simple fanout mechanism
- provide heartbeat every 20 to 30 seconds
- support reconnect behavior using Last-Event-ID if practical
- add tests for successful event delivery and unauthorized access

Keep the implementation simple and isolated behind a small SSE service module.
Task 8: implement ops workflows
Implement ops workflow services and endpoints for:

- claim conversation
- assign conversation
- transfer conversation
- resolve conversation
- close conversation
- apply tags

Rules:

- assignment state is authoritative in our database
- transfer updates queue_id and optionally posts a system handoff note to the new Roam queue thread
- close can send an optional final customer-visible system message
- every workflow appends an EventLog row
- add tests for status transitions and invalid transitions
  Task 9: implement KPI endpoints
  Implement analytics queries and endpoints for:
- queue depth
- open conversations by queue
- median first response time by queue
- median resolution time by queue
- hourly conversation volume
- transfer rate
- reopen rate
- analyst handled count
- SLA breach count

Requirements:

- start with direct Postgres queries
- keep query code in a dedicated analytics service layer
- add seed/demo command to generate realistic data
- add tests for metric correctness on a small deterministic dataset
  Task 10: build operational seed/demo tooling
  Create Django management commands for:
- seed_queues
- seed_routing_rules
- seed_demo_conversations
- simulate_roam_webhook
- replay_demo_conversation
- export_transcript

Requirements:

- README section with exact local setup steps
- example curl commands for core APIs
- example SSE client usage
- sample webhook payload fixtures
  Task 11: create Flutter integration docs
  Create a docs/mobile_integration.md file for the Flutter iOS team.

Include:

- auth assumptions
- endpoint list
- example request/response payloads
- SSE event format
- error format
- retry guidance
- optimistic send guidance
- reconnect guidance
- conversation lifecycle diagram

Do not write Flutter UI code yet.
Focus on a crisp contract the mobile team can implement against.
Task 12: add transcript and audit endpoints
Implement:

- GET /api/v1/ops/transcripts/{conversation_id}
- GET /api/v1/admin/audit/events

Transcript endpoint should return:

- conversation metadata
- queue history
- assignment history
- full message timeline

Audit endpoint should support filters for:

- conversation_id
- source
- event_type
- created_at range

Add serializer tests and example schema payloads. 16. Suggested build order
Week 1

tasks 1 to 5

prove create conversation -> route -> Roam post

Week 2

tasks 6 to 8

prove analyst reply -> webhook -> customer live update

Week 3

tasks 9 to 12

prove ops API, KPIs, transcript/audit completeness

17. Final recommendation

The right shape is:

Django owns the truth

Roam is the analyst console

Flutter iOS is the first customer client

admin capability ships as APIs first

Cloudflare One embedded admin comes later as a consumer of those same APIs

That gives you the fastest prototype path without painting yourself into a corner.
