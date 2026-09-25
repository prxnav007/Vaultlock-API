# vault-api — Authoritative Implementation Specification & Roadmap

**Document status:** V1 implementation authority  
**Last finalized:** 2026-08-14  
**Purpose:** This file is the main project context document for building `vault-api` from a clean implementation. It is deliberately more detailed than a GitHub README. Use it to decide what the project is, why architectural choices were made, what each schema means, which ML features are allowed to depend on which data, what milestone comes next, and what is explicitly deferred.

> **Rule for using this document:** do not reopen a finalized V1 decision merely because another approach also exists. Revisit a decision only when implementation results, tests, or ML experiments produce evidence that the current decision is inadequate.

---

# 1. Project Definition

`vault-api` is a distributed payment API with two tightly connected parts:

1. **Idempotent distributed payment infrastructure**
   - Multiple stateless FastAPI workers accept payment requests.
   - Duplicate/retried/concurrent HTTP requests must not create duplicate logical payments.
   - Redis coordinates concurrent workers.
   - PostgreSQL is the authoritative durable correctness boundary.
   - Nginx load-balances traffic across FastAPI replicas.
   - Concurrency and crash behavior are tested explicitly.

2. **Merchant churn intelligence**
   - The logical payment ledger becomes the source of merchant behavioral data.
   - Historical payment behavior is transformed into time-aware merchant snapshots.
   - XGBoost predicts whether a currently active merchant will become inactive during a future 60-day horizon.
   - RFM-style behavior, payment failure behavior, and merchant tenure are used as model features.
   - SHAP explains individual churn-risk predictions.
   - A FastAPI endpoint exposes churn risk using features derived by the server from the payment ledger.

The central connection between the two parts is **data integrity**:

> Idempotency does not only prevent duplicate payment effects. It also prevents transport-level retries from corrupting the transaction-frequency data later used by the ML system.

A browser retrying the same logical payment twenty times must produce:

```text
20 HTTP requests
        ↓
1 logical payment
        ↓
1 behavioral event visible to ML
```

It must **not** produce twenty rows that falsely make the merchant appear more active.

---

# 2. Precise Project Claim

Avoid the vague claim that the system provides universal "exactly-once execution."

The V1 claim is:

> **vault-api provides exactly-once logical payment creation within its PostgreSQL persistence boundary for duplicate and concurrent requests sharing the same merchant-scoped idempotency key.**

This deliberately does **not** claim that:
- the network delivers a request exactly once;
- Redis by itself guarantees exactly-once execution;
- an arbitrary external payment processor can never duplicate a charge;
- distributed systems in general provide magical exactly-once delivery.

In this project, PostgreSQL constraints and atomic transactions protect the durable invariant. Redis reduces duplicate concurrent work and coordinates stateless API workers.

---

# 3. What Is Being Rebuilt

The previous implementation proved that FastAPI, PostgreSQL, Docker, and basic endpoints could be brought up, but the domain model changed significantly once the ML problem became clearer.

The new implementation should therefore be treated as a **clean V1 rebuild**, not as a patching exercise.

The following earlier concepts should **not** be copied forward blindly:

- old SQLAlchemy transaction schema;
- old Pydantic payment request/response models;
- the old `/payments` implementation;
- the dummy CPU forecasting function;
- the placeholder ML endpoint;
- any feature columns previously added directly to transaction/payment rows;
- any static `is_churned` idea;
- the idea that Redis is the final source of truth.

Useful prior learning is retained, but the code structure should be rebuilt around the architecture in this document.

---

# 4. Architectural Principles

These principles should guide implementation decisions that are not explicitly covered elsewhere.

## 4.1 Persist facts; derive analytics

Core database tables record durable domain facts:

```text
merchant joined
payment attempted
payment amount
payment outcome
request was processed under an idempotency key
```

ML features such as:

```text
recency_days
frequency_change
failure_rate_30d
monetary_change
churn_next_60d
```

are **derived analytical data**, not columns on the core payment ledger.

Changing the XGBoost feature set later must not require redesigning the payment schema.

## 4.2 Distinguish three different schemas

### A. SQLAlchemy/database schema

Defines durable facts stored in PostgreSQL.

Examples:
- Merchant
- Payment
- IdempotencyRecord

### B. Pydantic/API schema

Defines what HTTP clients may send and what the API returns.

Examples:
- MerchantCreate
- MerchantResponse
- PaymentCreate
- PaymentResponse
- ChurnRiskResponse

A Pydantic model is **not** automatically a one-to-one copy of a database model.

### C. ML feature schema

Defines one training/inference row representing:

```text
merchant × snapshot_time
```

Examples:
- recency_days
- tx_count_30d
- failure_rate_30d
- churn_next_60d

The ML feature schema is allowed to evolve independently of the API request schema and core tables.

## 4.3 PostgreSQL is authoritative; Redis coordinates

Use this mental model:

```text
Redis lock
    │
    └── prevents/reduces concurrent duplicate work

PostgreSQL unique constraint + transaction
    │
    └── guarantees the durable invariant
```

A Redis lock has a TTL and can expire. A process can stall. Two workers can temporarily believe they may proceed if a lease expires at an unfortunate time.

Therefore correctness must not depend solely on the lock.

## 4.4 ML must see logical payments, not HTTP attempts

The ML pipeline reads the `payments` table.

It must never count:
- retries;
- repeated HTTP requests;
- failed lock acquisitions;
- replayed idempotent responses

as separate merchant transactions.

## 4.5 ML prediction must be forward-looking

"Merchant has had no transactions for 60 days" is a churn **state definition**, not a useful predictive model.

The model should instead answer:

> Given only information available at snapshot time `t`, will this currently active merchant make zero payment attempts during the next 60 days?

That is an actual future prediction task.

---

# 5. High-Level Architecture

```text
                                  ┌─────────────────────┐
                                  │       Client        │
                                  └──────────┬──────────┘
                                             │
                                             │ HTTP
                                             ▼
                                  ┌─────────────────────┐
                                  │        Nginx        │
                                  │   load balancer     │
                                  └──────────┬──────────┘
                                             │
                         ┌───────────────────┼───────────────────┐
                         ▼                   ▼                   ▼
                  ┌────────────┐      ┌────────────┐      ┌────────────┐
                  │ FastAPI #1 │      │ FastAPI #2 │      │ FastAPI #3 │
                  │ stateless  │      │ stateless  │      │ stateless  │
                  └──────┬─────┘      └──────┬─────┘      └──────┬─────┘
                         └───────────────────┼───────────────────┘
                                             │
                     ┌───────────────────────┴───────────────────────┐
                     │                                               │
                     ▼                                               ▼
             ┌────────────────┐                             ┌─────────────────┐
             │     Redis      │                             │   PostgreSQL    │
             │ distributed    │                             │ durable ledger  │
             │ coordination   │                             │ + constraints   │
             └────────────────┘                             └────────┬────────┘
                                                                    │
                                                                    │ historical facts
                                                                    ▼
                                                        ┌──────────────────────┐
                                                        │ Feature Generation   │
                                                        │ merchant × snapshot  │
                                                        └──────────┬───────────┘
                                                                   │
                                                                   ▼
                                                        ┌──────────────────────┐
                                                        │ XGBoost Classifier   │
                                                        │ + threshold          │
                                                        └──────────┬───────────┘
                                                                   │
                                                   ┌───────────────┴───────────────┐
                                                   ▼                               ▼
                                          ┌────────────────┐             ┌────────────────┐
                                          │ SHAP analysis  │             │ FastAPI churn  │
                                          │ offline + top  │             │ risk inference │
                                          │ factors        │             │ endpoint       │
                                          └────────────────┘             └────────────────┘
```

---

# 6. Technology Stack — V1

## Backend

- Python 3.12+
- FastAPI
- Uvicorn
- SQLAlchemy 2.x
- Pydantic v2
- PostgreSQL
- `asyncpg` for async PostgreSQL access
- Alembic for database migrations
- Redis using the async `redis-py` client
- Nginx
- Docker
- Docker Compose

## Testing

- `pytest`
- `pytest-asyncio`
- `httpx`
- `asyncio.gather` for concurrency/race tests

## ML/data

- NumPy
- pandas
- PyArrow/Parquet for processed feature datasets
- scikit-learn for metrics and baseline utilities
- XGBoost
- SHAP
- joblib only where convenient for supporting Python objects; prefer XGBoost's native model save format for the classifier itself

## Not required for V1

Do not add these merely because they are common in larger systems:

- Kubernetes
- Kafka
- Celery
- Airflow
- Spark
- feature stores
- microservice decomposition
- cloud deployment-specific infrastructure
- neural networks
- survival modeling
- SMOTEENN
- genetic-algorithm hyperparameter tuning

They may become extensions only if the completed V1 gives a concrete reason to add them.

---

# 7. Recommended Repository Structure

```text
vault-api/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py
│   │       ├── merchants.py
│   │       ├── payments.py
│   │       └── analytics.py          # added only when inference is ready
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── session.py
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── merchant.py
│   │       ├── payment.py
│   │       └── idempotency.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── merchant.py
│   │   ├── payment.py
│   │   └── analytics.py
│   │
│   └── services/
│       ├── __init__.py
│       ├── merchant_service.py
│       ├── payment_service.py
│       ├── idempotency_service.py
│       └── churn_service.py          # added only when inference is ready
│
├── ml/
│   ├── __init__.py
│   ├── config.py
│   │
│   ├── synthetic/
│   │   ├── __init__.py
│   │   └── generate.py
│   │
│   ├── features/
│   │   ├── __init__.py
│   │   └── build_snapshots.py
│   │
│   ├── baselines/
│   │   ├── __init__.py
│   │   └── recency.py
│   │
│   ├── train.py
│   ├── evaluate.py
│   ├── explain.py
│   └── inference.py
│
├── data/
│   ├── generated/                    # normally gitignored
│   └── processed/                    # normally gitignored
│
├── artifacts/
│   ├── xgboost_model.json
│   ├── model_metadata.json
│   └── metrics.json
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── concurrency/
│
├── nginx/
│   └── nginx.conf
│
├── alembic/
├── alembic.ini
│
├── scripts/
│   └── stress_test.py
│
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── PROJECT_SPEC.md                   # this document
└── README.md                         # written separately for GitHub
```

`main.py` should mainly construct the app, configure lifespan resources, and include routers. Business logic belongs in services. Database tables belong in `db/models`. HTTP validation belongs in `schemas`. ML training belongs outside the request path.

---

# 8. Core Domain Schema

The final V1 core domain consists of three tables:

```text
Merchant
Payment
IdempotencyRecord
```

Relationship:

```text
Merchant 1 ──────────────── * Payment

Merchant 1 ──────────────── * IdempotencyRecord

IdempotencyRecord 0/1 ───── 1 Payment
```

The ML system is downstream of these tables. No ML feature column is required in the core schema.

---

# 9. SQLAlchemy Model Decision: Merchant

## Purpose

One row represents one merchant account whose payment activity may later be analyzed.

## Table: `merchants`

| Column | Type | Null? | Meaning |
|---|---|---:|---|
| `merchant_id` | UUID | No | Primary key |
| `joined_at` | TIMESTAMPTZ | No | Time merchant joined the platform |
| `industry` | VARCHAR | Yes | Merchant segment/business category |
| `created_at` | TIMESTAMPTZ | No | Database record creation time |

## Decisions

### `merchant_id`

- UUID primary key.
- Server-generated for normal API-created merchants.
- Synthetic seeding may generate UUIDs itself.

### `joined_at`

- Required for ML.
- It lets the feature pipeline calculate `tenure_days`.
- It prevents confusing a newly joined merchant with a long-standing merchant that has gone inactive.
- Normal API calls do not need to supply a historical `joined_at`; the service may use current time.
- Synthetic generation may insert historical join times directly.

### `industry`

- Stored because it is plausible merchant metadata and may support later segmentation.
- **Not used as a V1 model feature.**
- Synthetic data will itself assign industry, so using it immediately could create an artificial shortcut if the generator also makes industry determine churn.

## Columns deliberately NOT stored

Do not add:

```text
is_churned
last_transaction_at
frequency
monetary
failure_rate
churn_score
```

Reasons:
- `is_churned` changes relative to time.
- `last_transaction_at` is derivable from payments and can be cached later only if performance requires it.
- RFM values belong to feature generation.
- churn score is model output and may change with model version/snapshot time.

---

# 10. SQLAlchemy Model Decision: Payment

## Purpose

One row represents **one logical payment attempt** by a merchant.

It does not represent one HTTP request.

A repeated request with the same valid idempotency key must resolve to the same logical payment rather than create another payment row.

## Table: `payments`

| Column | Type | Null? | Meaning |
|---|---|---:|---|
| `payment_id` | UUID | No | Primary key |
| `merchant_id` | UUID FK | No | Merchant that owns the payment |
| `amount_minor` | BIGINT | No | Money in the smallest currency unit |
| `currency` | VARCHAR(3) | No | Three-character currency code |
| `status` | PaymentStatus | No | `PENDING`, `SUCCESS`, or `FAILED` |
| `failure_code` | VARCHAR | Yes | Reason code when final status is failed |
| `created_at` | TIMESTAMPTZ | No | Logical payment creation time |
| `processed_at` | TIMESTAMPTZ | Yes | Time a final outcome was determined |
| `updated_at` | TIMESTAMPTZ | No | Last state update |

## Money representation

Do not store payment amounts as floating-point values.

Use the smallest currency unit:

```text
₹529.50 → 52950
$10.99  → 1099
```

## Payment statuses

### `PENDING`
The logical payment exists but a terminal result is not yet available.

### `SUCCESS`
The attempt completed successfully.

### `FAILED`
The merchant attempted to pay but the attempt reached a failed terminal result.

For ML:
- SUCCESS and FAILED both count as **merchant activity**.
- PENDING rows should not normally remain in the historical synthetic dataset.
- failure-rate features use FAILED terminal attempts.
- churn is based on absence of **attempts**, not absence of successful payments.

A merchant with repeated payment failures is experiencing friction but is not inactive.

---

# 11. Payment Indexes and Constraints

Recommended constraints:

- primary key on `payment_id`;
- foreign key `merchant_id → merchants.merchant_id`;
- check `amount_minor > 0`;
- currency length exactly 3;
- allowed payment status values only.

Recommended index:

```text
(merchant_id, created_at)
```

This supports the dominant analytical query pattern: retrieve a merchant's logical payments inside a time range.

A separate status index is not mandatory in the first migration unless profiling later demonstrates the need.

---

# 12. SQLAlchemy Model Decision: IdempotencyRecord

## Purpose

An idempotency record represents:

```text
merchant + idempotency key + request payload
                    ↓
             one stored outcome
```

Keep request-deduplication state separate from the `payments` table so the payment ledger remains clean and transport semantics stay away from ML.

## Table: `idempotency_records`

| Column | Type | Null? | Meaning |
|---|---|---:|---|
| `id` | UUID | No | Internal primary key |
| `merchant_id` | UUID FK | No | Merchant scope of the idempotency key |
| `idempotency_key` | VARCHAR(128) | No | Client-supplied retry key |
| `request_fingerprint` | CHAR(64) | No | SHA-256 hash of canonical request semantics |
| `state` | IdempotencyState | No | `PROCESSING` or `COMPLETED` |
| `payment_id` | UUID FK | Yes | Resulting logical payment |
| `response_status_code` | INTEGER | Yes | Original HTTP status to replay |
| `response_body` | JSONB | Yes | Original response payload to replay |
| `created_at` | TIMESTAMPTZ | No | Record creation time |
| `updated_at` | TIMESTAMPTZ | No | Last update |

## Unique invariant

Create:

```text
UNIQUE (merchant_id, idempotency_key)
```

Idempotency keys are merchant-scoped.

## Request fingerprint

The idempotency key alone is insufficient.

Example:

```text
Idempotency-Key: 550e8400-...

request A:
amount_minor = 10000
currency = INR

request B:
amount_minor = 500000
currency = INR
```

Request B must not silently replay the first result or create another payment under the same key.

Create a deterministic SHA-256 fingerprint from canonical semantic fields including at least:

```text
merchant_id
amount_minor
currency
```

If an existing key is found:

- same fingerprint → legitimate retry/replay;
- different fingerprint → reject as key reuse with different semantics.

## Record retention

For V1, keep PostgreSQL idempotency records indefinitely.

Do not add a database cleanup/expiration subsystem yet.

Redis **locks** still require a short TTL. Database idempotency-record retention is a different concern.

---

# 13. Redis Lock Design

## Key shape

```text
idem:{merchant_id}:{idempotency_key}
```

## Lock value

Use a unique owner token, e.g. a random UUID per acquisition.

## Acquisition

Conceptually:

```text
SET key owner_token NX EX <lock_ttl>
```

The TTL must be configurable.

A V1 default around tens of seconds is reasonable, but the exact number should be based on simulated payment-processing duration rather than treated as a correctness guarantee.

## Release

A worker must delete the lock **only if it still owns it**.

Do not blindly `DEL key` after work finishes.

If worker A's lease expires, worker B acquires the same key, and worker A later resumes, A must not delete B's lock.

Use an atomic compare-owner-and-delete operation, typically a Redis Lua script.

## What the lock does not guarantee

The lock is a coordination mechanism.

Even if a lease expires at the wrong moment, PostgreSQL's uniqueness constraint remains the final barrier to duplicate committed outcomes.

---

# 14. Payment Request Processing Flow

```text
POST /payments
     │
     ▼
Validate body and Idempotency-Key
     │
     ▼
Compute request fingerprint
     │
     ▼
Check PostgreSQL for existing merchant/key
     │
     ├── existing + same fingerprint + completed
     │        └── replay stored response
     │
     ├── existing + different fingerprint
     │        └── reject key reuse
     │
     └── no completed record
              │
              ▼
        Try Redis lock
              │
       ┌──────┴──────┐
       │             │
   lock failed   lock acquired
       │             │
       ▼             ▼
 recheck DB      recheck DB
       │             │
 completed?          │
 replay it           │
 otherwise 409       │
                     ▼
              begin DB transaction
                     │
                     ▼
              verify merchant exists
                     │
                     ▼
              create logical payment
                     │
                     ▼
              determine payment outcome
                     │
                     ▼
              store idempotency result
              + response atomically
                     │
                     ▼
                   COMMIT
                     │
                     ▼
              release owned Redis lock
                     │
                     ▼
                 return response
```

## Why check PostgreSQL before Redis?

Completed retries should be cheap replays. They do not need a new Redis serialization cycle just to read a stored result.

## Why check again after acquiring the lock?

Another worker may have completed the request between the initial database check and this worker acquiring the lock.

## PostgreSQL fallback

If a rare race reaches the database despite Redis coordination, the unique `(merchant_id, idempotency_key)` invariant is the final guard.

Code must catch the integrity conflict, roll back, fetch the winning stored result, and resolve safely rather than returning an accidental unhandled 500.

---

# 15. External Payment Provider Boundary

V1 does **not** integrate a real card/payment provider.

Therefore the protected "payment effect" is the logical payment effect inside this project's persistence boundary.

A real provider would create another distributed boundary:

```text
vault-api → external payment processor
```

If that is implemented later, vault-api would also need provider-side idempotency or an equivalent mechanism.

Do not claim V1 solves failure modes across an unimplemented third-party payment network.

---

# 16. API Contract — Merchant Endpoints

## `POST /merchants`

### `MerchantCreate`

```text
industry: str | None
```

Do not expose ML labels or historical `joined_at` backdating through the normal public create API.

Normal `joined_at` is server-generated. Synthetic seeding is separate and may insert historical timestamps.

### `MerchantResponse`

```text
merchant_id: UUID
joined_at: datetime
industry: str | None
created_at: datetime
```

### Status

```text
201 Created
```

## `GET /merchants/{merchant_id}`

Returns merchant metadata.

Failure:

```text
404 Merchant Not Found
```

---

# 17. API Contract — Payment Endpoint

## `POST /payments`

### Header

Use one canonical name:

```text
Idempotency-Key: <client-generated UUID/string>
```

Do not keep multiple equivalent custom header names unless compatibility later requires it.

### `PaymentCreate`

```text
merchant_id: UUID
amount_minor: int > 0
currency: str, exactly 3 characters, normalized uppercase
```

The client does **not** send:
- payment status;
- created time;
- churn features;
- failure rate;
- idempotency database state.

### `PaymentResponse`

```text
payment_id: UUID
merchant_id: UUID
amount_minor: int
currency: str
status: PENDING | SUCCESS | FAILED
failure_code: str | None
created_at: datetime
processed_at: datetime | None
```

### Expected response behavior

First successful processing:

```text
201 Created
```

Legitimate replay:
- return the stored body;
- return the original stored status code;
- optionally expose `Idempotent-Replayed: true` for observability.

Concurrent request while the winner is still processing:

```text
409 Conflict
```

Same merchant/key but different fingerprint:

```text
409 Conflict
```

Unknown merchant:

```text
404 Not Found
```

Invalid body:

```text
422 Unprocessable Entity
```

---

# 18. Useful Read Endpoint

Implement:

```text
GET /payments/{payment_id}
```

This is useful for tests and debugging because it verifies the final logical payment state through the API.

A merchant payment-list endpoint is optional and is not required to prove V1 idempotency or train the offline ML pipeline.

---

# 19. Health Endpoint

Use:

```text
GET /health
```

Its first purpose is container/load-balancer health checking.

Do not turn it into a large observability subsystem.

---

# 20. Database Transactions

The core payment/idempotency write must be atomic.

Invariant:

> A committed logical payment and the completed idempotency result identifying it must agree.

Do not do:

```text
insert payment
COMMIT

insert idempotency record
COMMIT
```

because a crash between those commits creates an unsafe state.

Use SQLAlchemy transaction scopes such as:

```text
async with session.begin():
    ...
```

or an equivalent explicit transaction pattern.

---

# 21. Pydantic Models Are API Models, Not ORM Mirrors

Recommended V1 models:

```text
MerchantCreate
MerchantResponse

PaymentCreate
PaymentResponse

RiskFactor                 # added with inference
ChurnRiskResponse          # added with inference
```

Do not create dozens of Pydantic models just to mirror every SQLAlchemy object or intermediate service step.

---

# 22. ML Problem Definition — Final V1

## Unit of prediction

One example is:

```text
merchant × snapshot_time
```

Example:

```text
merchant_A | 2026-01-07
merchant_A | 2026-01-14
merchant_A | 2026-01-21
merchant_B | 2026-01-07
...
```

The same merchant's risk may change across time.

---

# 23. Snapshot Cadence — Final V1

Use:

```text
7 days
```

Weekly historical snapshots provide multiple lifecycle observations without creating a nearly duplicate row every day.

This is a training/feature-generation cadence, not a restriction that production inference can only happen weekly.

---

# 24. Historical Observation Window — Final V1

Use up to:

```text
90 days of history before snapshot t
```

Feature values must use only information available at or before the snapshot.

No future payment may influence a feature.

---

# 25. Future Churn Horizon — Final V1

Use:

```text
60 days
```

For eligible snapshot time `t`:

```text
churn_next_60d = 1
```

if the merchant makes **zero logical payment attempts** in:

```text
(t, t + 60 days]
```

Otherwise:

```text
churn_next_60d = 0
```

Both SUCCESS and FAILED attempts count as activity.

A merchant with repeated failed payments is still engaging with the platform. Failure may predict future departure, but failure itself is not inactivity.

---

# 26. Eligible Snapshot Rule

A snapshot is eligible only if:

1. the merchant has at least **90 days of tenure** by snapshot time;
2. the dataset contains at least **60 future days** after the snapshot so the label can be observed;
3. the merchant has at least one logical payment attempt in the prior 60 days.

Condition 3 keeps the prediction population focused on merchants that have not already obviously churned.

---

# 27. Final V1 Feature Schema

The first XGBoost feature set should remain compact and interpretable.

## Recency

### `recency_days`

```text
snapshot_time - latest payment attempt at/before snapshot
```

## Frequency

### `tx_count_30d`

Attempts in:

```text
(t - 30d, t]
```

### `tx_count_prev_30d`

Attempts in:

```text
(t - 60d, t - 30d]
```

### `tx_count_90d`

Attempts in:

```text
(t - 90d, t]
```

### `frequency_change`

Use a transparent numeric difference:

```text
tx_count_30d - tx_count_prev_30d
```

Negative means recent frequency has fallen.

Do not initially reduce frequency to a boolean like `is_frequency_declining`, because that discards magnitude.

## Monetary behavior

Use SUCCESS payments for value features so failed attempts do not pretend to be completed payment volume.

### `avg_success_amount_30d`

Average `amount_minor` among SUCCESS payments in:

```text
(t - 30d, t]
```

### `avg_success_amount_prev_30d`

Average among SUCCESS payments in:

```text
(t - 60d, t - 30d]
```

### `monetary_change`

```text
avg_success_amount_30d - avg_success_amount_prev_30d
```

If a comparison period has no successful payments, preserve a missing value rather than inventing an artificial average.

## Payment reliability

### `failure_rate_30d`

```text
FAILED terminal attempts in last 30d
------------------------------------
SUCCESS + FAILED terminal attempts in last 30d
```

### `failure_rate_prev_30d`

Same calculation for the previous 30-day period.

### `failure_rate_change`

```text
failure_rate_30d - failure_rate_prev_30d
```

If a period has no terminal attempts, keep the value missing rather than dividing by zero.

## Merchant tenure

### `tenure_days`

```text
snapshot_time - merchant.joined_at
```

---

# 28. V1 Features Explicitly Excluded

Do not add these before the baseline has been evaluated:

- industry one-hot encoding;
- time-of-day patterns;
- day-of-week entropy;
- geography;
- merchant name;
- merchant ID;
- raw idempotency keys;
- Redis lock metrics;
- HTTP retry counts;
- static `is_churned`;
- any future information;
- synthetic generator latent churn parameters.

Particularly important:

> Never feed synthetic generator latent variables directly into XGBoost. They exist only to generate the world. The model must infer risk from observable merchant/payment behavior.

---

# 29. Why the Feature Schema Does Not Change the Payment Schema

Every V1 feature can be calculated from:

## `merchants`

```text
merchant_id
joined_at
```

and:

## `payments`

```text
merchant_id
amount_minor
status
created_at
```

That is intentional.

Later rolling statistics do not require new database columns unless they depend on a genuinely new real-world fact the platform was never recording.

---

# 30. Processed ML Dataset

Initially write snapshots to:

```text
data/processed/merchant_snapshots.parquet
```

Recommended columns:

```text
merchant_id
snapshot_at

recency_days

tx_count_30d
tx_count_prev_30d
tx_count_90d
frequency_change

avg_success_amount_30d
avg_success_amount_prev_30d
monetary_change

failure_rate_30d
failure_rate_prev_30d
failure_rate_change

tenure_days

churn_next_60d
```

`merchant_id` and `snapshot_at` are metadata/indexing fields.

Do **not** include `merchant_id` as an XGBoost feature.

---

# 31. Synthetic Data Strategy

The synthetic generator is one of the most important ML components because an unrealistically easy generator can make meaningless models look excellent.

## Initial scale

A useful V1 target is approximately:

```text
2,000–5,000 merchants
roughly 18–24 months of platform history
different join dates
irregular merchant activity
heterogeneous payment volumes
unbalanced churn
```

Exact row count is not a research contribution. Start small enough to iterate quickly and increase after the pipeline is correct.

## Reproducibility

Use a configurable fixed random seed.

The same seed and generator configuration should regenerate the same synthetic history.

---

# 32. Synthetic Merchant Latent Profiles

Generate behavior from hidden merchant characteristics rather than directly generating desired feature values.

Example latent variables:

```text
baseline transaction rate
typical payment amount distribution
baseline failure probability
activity variability
weekly/seasonal variation
long-term churn propensity
possible disengagement start time
disengagement speed
```

These latent variables:
- do not belong in the production `merchants` table;
- must not become XGBoost input features;
- exist only inside synthetic-data generation.

---

# 33. Avoid a Trivial Synthetic Churn Problem

Do not generate all churners using deterministic rules such as:

```python
if churner:
    frequency *= 0.5
    amount *= 0.5
    failure_rate *= 3
```

while every non-churner remains perfectly stable.

Include overlap and noise:

- churners with gradual frequency decline;
- churners that stop abruptly;
- churners whose monetary value does not decline;
- churners whose failure rate stays normal;
- active merchants with temporary transaction dips;
- active merchants with elevated failure periods;
- active merchants that recover;
- high-volume and low-volume merchants;
- different merchant ages and join dates.

The goal is learnable signal, not perfect separability.

---

# 34. Churn Prevalence

Do not generate a 50/50 world.

A reasonable initial merchant-level target is around:

```text
10–20%
```

with roughly 15% as a sensible first generator setting.

The final **snapshot-label positive rate** may differ because one merchant can produce many snapshots.

Measure and report the actual label balance after feature generation. Do not force the snapshot dataset to exactly 15% positives.

---

# 35. Synthetic Payment Failures

Failure events should contain signal but must not perfectly reveal churn.

For example:
- baseline failure probability differs by merchant;
- for some merchants approaching churn, friction probability may rise;
- some merchants churn for reasons unrelated to payment failures;
- some healthy merchants have temporary high failure periods and recover.

This is necessary if the project is going to test whether reliability behavior adds value beyond recency/frequency.

---

# 36. Training/Test Leakage Rules

These rules are mandatory.

## Rule 1: no future information in features

At snapshot `t`, features may use only:

```text
created_at <= t
```

## Rule 2: labels use future data, features do not

The label intentionally reads `(t, t + 60d]`, but those events must never enter features for the same row.

## Rule 3: do not use random shuffle splitting

Do not use a random shuffled train/test split on time snapshots.

## Rule 4: split chronologically

Use:

```text
early snapshots  → training
middle snapshots → validation
latest snapshots → test
```

## Rule 5: purge label overlap

Because labels look 60 days into the future, keep a purge/gap near split boundaries so training labels do not depend on the same future period being treated as an earlier validation/test decision point.

Exact date boundaries should be printed by the feature/training pipeline and recorded in model metadata.

---

# 37. Model Choice — Final V1

Use:

```text
XGBoost binary classifier
```

Do not switch to a neural network, LSTM, transformer, SVM, or survival model before establishing this baseline.

The final table is tabular, nonlinear interactions matter, missing values may occur naturally, and SHAP is well suited to explaining this model family.

The main methodological change from the base paper is the temporal behavioral problem formulation, not abandoning XGBoost.

---

# 38. Class Imbalance — Final V1

Start with:

```text
scale_pos_weight = negative training rows / positive training rows
```

Compute it from the **training split only**.

Do not add SMOTEENN in the first implementation.

A later experiment may compare resampling techniques only after the baseline is trusted.

---

# 39. Hyperparameter Tuning — Final V1

Do not use a genetic algorithm initially.

Use a small understandable search around:

```text
max_depth
learning_rate
n_estimators
min_child_weight
subsample
colsample_bytree
reg_alpha
reg_lambda
```

Evaluate candidate configurations on the chronological validation set.

Do not spend significant time optimizing tiny score gains before validating feature correctness, leakage safety, baselines, and synthetic-data realism.

Genetic-algorithm tuning remains a possible later comparison because of the base paper, not a core architecture requirement.

---

# 40. Mandatory Baselines and Ablation

Evaluate at least:

## Baseline A — majority/dummy classifier

Shows the class-imbalance floor.

## Baseline B — recency-only baseline

Choose a simple recency threshold on validation data or fit an intentionally simple one-feature baseline.

This tests whether `recency_days` almost completely solves the synthetic problem by itself.

## Model C — RFM-style XGBoost without failure features

Use:
- recency;
- frequency;
- monetary behavior;
- tenure.

## Model D — RFM + failure/reliability XGBoost

Add failure-rate features.

The strongest empirical project question becomes:

> Do transaction trajectory and payment reliability features improve future-churn prediction beyond a simple recency signal?

---

# 41. Evaluation Metrics — Final V1

Report:

- PR-AUC / Average Precision;
- F1;
- precision;
- recall;
- ROC-AUC;
- confusion matrix.

## Headline metrics

Prioritize:

```text
PR-AUC
F1
```

because churn is intentionally imbalanced.

ROC-AUC remains useful but should not be the only headline metric.

## No arbitrary score target

Do not define success as "must beat 90% F1" or "must beat the paper's AUC." The data and prediction problem differ.

Success means:
- no leakage;
- nontrivial synthetic data;
- temporal generalization;
- meaningful comparison with simple baselines;
- interpretable behavior.

Suspiciously perfect metrics should trigger leakage/generator inspection.

---

# 42. Classification Threshold

Do not assume 0.5 is automatically the final operating threshold.

Procedure:

1. train on training data;
2. generate validation scores;
3. evaluate candidate thresholds;
4. choose a threshold according to the V1 objective, initially F1;
5. freeze it;
6. evaluate the frozen model + threshold once on test data.

Never tune the threshold on the test set.

---

# 43. SHAP — Final V1

Use SHAP after a satisfactory classifier exists.

## Global interpretation

Understand overall drivers such as recency, recent frequency, trend, and failure behavior.

## Local interpretation

For one merchant prediction, identify the strongest features pushing risk upward or downward.

The API should eventually expose a small number of understandable top factors rather than the entire raw SHAP vector.

SHAP explains how features affected the model prediction. It does **not** prove those features causally made a merchant churn.

---

# 44. Model Artifact Contract

Persist at least:

```text
artifacts/xgboost_model.json
artifacts/model_metadata.json
artifacts/metrics.json
```

`model_metadata.json` should include:

```text
model_version
feature_names
observation_window_days = 90
prediction_horizon_days = 60
snapshot_cadence_days = 7
classification_threshold
training_data_time_range
validation_data_time_range
test_data_time_range
scale_pos_weight
selected_hyperparameters
```

This prevents training and inference from silently using different feature contracts.

---

# 45. ML Inference Endpoint

Add this route only after the offline ML pipeline works:

```text
GET /merchants/{merchant_id}/churn-risk
```

## Client must not send features

Bad design:

```json
{
  "recency_days": 20,
  "frequency_change": -7
}
```

The service owns the ledger and should derive the merchant's current features itself.

## Example response

```json
{
  "merchant_id": "uuid",
  "snapshot_at": "timestamp",
  "churn_score": 0.81,
  "risk_band": "HIGH",
  "predicted_churn": true,
  "top_factors": [
    {
      "feature": "frequency_change",
      "direction": "increases_risk"
    },
    {
      "feature": "failure_rate_change",
      "direction": "increases_risk"
    }
  ],
  "model_version": "xgb-v1"
}
```

Use `churn_score` rather than claiming a calibrated real-world probability unless calibration is explicitly evaluated later.

---

# 46. Training Must Stay Outside the Request Path

Offline:

```text
generate synthetic data
        ↓
build snapshots
        ↓
train
        ↓
evaluate
        ↓
save artifacts
```

Online:

```text
load saved model during app lifespan
        ↓
query merchant/payment history
        ↓
build latest feature vector
        ↓
predict
        ↓
explain top factors
        ↓
return response
```

The old dummy CPU forecast function must not survive the rebuild.

---

# 47. FastAPI Lifespan Responsibilities

The application lifespan may eventually initialize:

- database resources;
- Redis client;
- trained model + metadata after ML inference exists.

Do not train the model during startup.

At shutdown, close database and Redis resources cleanly.

---

# 48. Configuration

Use environment-driven centralized settings.

Examples:

```text
DATABASE_URL
REDIS_URL
REDIS_LOCK_TTL_SECONDS
APP_ENV
MODEL_PATH
MODEL_METADATA_PATH
```

Use `.env.example` for expected keys.

Do not commit real secrets.

---

# 49. Alembic Is Part of the V1 Foundation

Do not rely on scattered `create_all()` calls as the long-term schema mechanism.

Use Alembic migrations.

Possible initial progression:

```text
0001_create_merchants
0002_create_payments
0003_create_idempotency_records
```

Combining these into one initial migration during the clean rebuild is acceptable. From that point onward, schema changes should be migration-driven.

---

# 50. Docker Compose Target Architecture

Final V1 Compose contains at least:

```text
nginx
api-1
api-2
api-3
postgres
redis
```

All API replicas share:
- PostgreSQL;
- Redis;
- no Python process memory.

That is what makes in-process locks insufficient.

Early milestones may temporarily run one API worker until schema/API behavior is correct.

---

# 51. Nginx Purpose

Nginx provides:
- one client-facing entry point;
- load distribution across API containers;
- a way for duplicate/concurrent requests to reach different workers.

The project does not need advanced Nginx features beyond the distributed-system demonstration.

---

# 52. Concurrency Test Goal

The stress test sends many requests with:

```text
same merchant
same body
same idempotency key
```

close together using `httpx` and `asyncio.gather`.

Verify:

```text
number of HTTP calls > 1
number of committed logical payments = 1
number of authoritative idempotency records = 1
```

Depending on timing:
- one request may create the payment;
- some may receive 409 while processing;
- later retries should replay the stored result.

The database invariant matters more than every client receiving identical timing behavior.

---

# 53. Failure-State Demonstration

The project may intentionally demonstrate what happens without idempotency in a controlled milestone/test.

Possible sequence:

```text
naive /payments
      ↓
3 workers + stress test
      ↓
observe duplicate payment rows
      ↓
enable PostgreSQL idempotency invariant
      ↓
add Redis coordination
      ↓
rerun same tes






↓
one logical payment
```

The final codebase should remain safe by default.

Do not keep a dangerous production-like toggle unless clearly isolated for testing/demonstration.

---

# 54. Crash/Resilience Tests

## Case A: crash before transaction commit

Expected:
- transaction rolls back;
- no completed payment/idempotency pair is committed;
- later retry may process safely.

## Case B: duplicate arrives after commit

Expected:
- stored response is replayed;
- no second payment row.

## Case C: Redis lock expires unusually early

Expected:
- another worker may attempt work;
- PostgreSQL uniqueness remains the final duplicate barrier.

## Case D: key reused with different body

Expected:
- conflict;
- original payment unchanged.

## Case E: losing request receives 409 and retries later

Expected:
- once the winner commits, the retry replays the winner's stored result.

---

# 55. Recommended Implementation Order

There are two major tracks after the common foundation:

```text
                     COMMON FOUNDATION
                           │
                  schema + basic API
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       ML uncertainty track      distributed-systems track
              │                         │
              └────────────┬────────────┘
                           ▼
                     final integration
```

Because the ML formulation contains more experimental uncertainty than Nginx/Redis engineering, validate the ML framing relatively early.

---

# 56. Milestone 0 — Clean Rewrite Setup

## Goal

Create a clean codebase without dragging old schema/API assumptions forward.

## Implement

- clean project structure;
- remove old SQLAlchemy domain models;
- remove old Pydantic payment schemas;
- remove old payment endpoint implementation;
- remove dummy forecast code;
- remove placeholder ML endpoint;
- central configuration;
- SQLAlchemy async session infrastructure;
- Alembic;
- keep Docker/Postgres pieces only if they cleanly fit the new structure.

## Definition of done

- app imports cleanly;
- `/health` works;
- PostgreSQL connection works;
- no old domain schema is accidentally imported.

## Do not implement yet

- Redis locking;
- Nginx scaling;
- XGBoost;
- SHAP.

---

# 57. Milestone 1 — Canonical Domain Schema

## Goal

Make the database representation stable enough for both infrastructure and ML.

## Implement

SQLAlchemy models:
- Merchant;
- Payment;
- IdempotencyRecord.

Enums:
- PaymentStatus;
- IdempotencyState.

Constraints:
- foreign keys;
- amount positivity;
- idempotency uniqueness.

Index:
- `(merchant_id, created_at)` on payments.

Alembic migration(s).

## Tests

- migration applies to an empty DB;
- merchant inserts correctly;
- payment FK requires valid merchant;
- nonpositive amount is rejected;
- duplicate `(merchant_id, idempotency_key)` cannot commit.

## Definition of done

The schema in Sections 9–13 exists and no ML feature is stored in the core tables.

---

# 58. Milestone 2 — Basic Single-Worker API

## Goal

Rebuild HTTP contracts cleanly before distributed concurrency.

## Implement

Pydantic:
- MerchantCreate;
- MerchantResponse;
- PaymentCreate;
- PaymentResponse.

Routes:
- `POST /merchants`;
- `GET /merchants/{merchant_id}`;
- `POST /payments`;
- `GET /payments/{payment_id}`;
- `GET /health`.

At this milestone, payment processing may still be simplified while Redis behavior is deferred.

## Definition of done

- API validation is correct;
- all data uses the new schema;
- no dummy ML endpoint;
- no derived RFM fields in request models.

---

# 59. Milestone 3 — Synthetic Data Generator

## Why this comes early

The biggest research uncertainty is whether the churn formulation produces a useful, nontrivial prediction problem.

Discovering a flaw here early is cheaper than finishing all Nginx/Redis polish first.

## Implement

`ml/synthetic/generate.py`

Generate:
- merchants with varied join dates;
- heterogeneous activity rates;
- heterogeneous payment amounts;
- SUCCESS/FAILED outcomes;
- noisy disengagement trajectories;
- minority long-term inactivity.

Use the same canonical `merchants` and `payments` schema, or generate data that loads directly into it.

Do not create ML-only columns on core tables.

## Definition of done

- generation is reproducible;
- merchants have different behavior patterns;
- active and future-churning behavior both exist;
- churn is not perfectly deterministic;
- history is long enough for 90d features + 60d labels.

---

# 60. Milestone 4 — Feature and Label Pipeline

## Implement

`ml/features/build_snapshots.py`

Produce weekly eligible merchant snapshots using the exact V1 feature definitions.

## Tests must prove

- payment after snapshot cannot change features;
- future-60d payment changes label, not features;
- FAILED attempts count as activity;
- frequency windows use correct boundaries;
- missing monetary windows do not divide by zero;
- tenure/future-horizon/current-active eligibility is enforced.

## Output

```text
data/processed/merchant_snapshots.parquet
```

## Definition of done

Feature generation is deterministic and leakage-safe.

Do not train XGBoost before trusting this milestone.

---

# 61. Milestone 5 — ML Feasibility Baseline

## Goal

Answer whether the project framing is sound before tuning heavily.

## Evaluate

1. dummy/majority baseline;
2. recency-only baseline;
3. RFM XGBoost;
4. RFM + failure XGBoost.

Use chronological train/validation/test logic.

Use `scale_pos_weight` from training labels.

Report:
- label balance;
- PR-AUC;
- F1;
- precision;
- recall;
- ROC-AUC;
- confusion matrix.

## Decision gate

Continue if:
- behavior is nontrivial;
- no leakage is found;
- XGBoost gives meaningful improvement over simple baselines or gives useful evidence about which features matter.

If results are near-perfect, inspect the generator first.

If RFM+failure adds no value over recency, investigate the generator/feature definitions before adding algorithms.

## Definition of done

There is evidence that the ML problem is sound enough to continue.

---

# 62. Milestone 6 — Scale the API and Demonstrate the Race

## Implement

- Nginx;
- three FastAPI replicas;
- stress test script.

If useful, briefly run a deliberately naive payment path in a controlled test to show the failure state.

## Demonstrate

```text
same logical operation
        ↓
different stateless workers
        ↓
duplicate work/payment rows without protection
```

## Definition of done

The race condition can be reproduced and measured.

---

# 63. Milestone 7 — PostgreSQL Idempotency Semantics

## Goal

Make the durable invariant safe before treating Redis as coordination.

## Implement

- merchant-scoped idempotency records;
- request fingerprint;
- stored response replay;
- unique conflict handling;
- atomic payment + idempotency outcome;
- mismatch rejection.

## Tests

- same key/same payload returns same logical payment;
- same key/different payload conflicts;
- simultaneous conflicting DB inserts cannot create two committed logical payments.

## Definition of done

PostgreSQL protects the durable invariant.

---

# 64. Milestone 8 — Redis Distributed Coordination

## Implement

- Redis lifecycle;
- lock key convention;
- owner tokens;
- `SET NX EX`;
- safe owner-checked release;
- configurable TTL;
- double-check DB around acquisition;
- 409 behavior for unresolved concurrent processing.

## Tests

Fire requests through Nginx and verify:
- one logical payment;
- one idempotency outcome;
- completed retries replay;
- lock contention does not corrupt state.

## Definition of done

The three-worker system behaves correctly under duplicate stress and Redis is not the sole correctness mechanism.

---

# 65. Milestone 9 — Resilience Hardening

## Implement/test

- rollback paths;
- integrity-error recovery;
- simulated interruption where practical;
- lock expiry behavior;
- database failure handling;
- structured errors;
- safe Redis ownership cleanup.

## Definition of done

Expected failure modes have tests or documented behavior rather than being accidental.

---

# 66. Milestone 10 — Full XGBoost Training and SHAP

## Implement

- small hyperparameter search;
- validation threshold selection;
- frozen test evaluation;
- SHAP global analysis;
- SHAP local examples;
- model artifact saving;
- metadata saving;
- metrics saving.

## Definition of done

A reproducible script/command can regenerate processed data, train, evaluate, and save artifacts.

---

# 67. Milestone 11 — Churn Risk API Integration

## Implement

- load model + metadata at app startup;
- derive current merchant features using the same definitions;
- `GET /merchants/{merchant_id}/churn-risk`;
- top local factors;
- model version in response.

## Guardrails

- merchant must exist;
- enough history must exist for inference;
- inference feature order must match metadata;
- missing model artifact must fail explicitly instead of inventing a score.

## Definition of done

A merchant in PostgreSQL can receive a risk result without the client manually supplying ML features.

---

# 68. Milestone 12 — End-to-End Finalization

Validate the complete narrative:

1. merchants produce logical payments;
2. retries/concurrency do not duplicate them;
3. the clean ledger becomes behavioral history;
4. feature generation creates merchant snapshots;
5. XGBoost predicts future inactivity;
6. SHAP explains risk;
7. FastAPI exposes the result.

## Final tests

- normal merchant/payment flow;
- idempotent retry;
- concurrent duplicate storm;
- different-payload key misuse;
- synthetic generation;
- feature leakage tests;
- model evaluation;
- inference route.

## Final outputs

- polished README;
- architecture diagram;
- test instructions;
- ML results;
- limitations;
- future work.

---

# 69. Definition of V1 Complete

## Infrastructure

- Nginx routes to three stateless FastAPI workers;
- PostgreSQL stores merchant/payment/idempotency state;
- Redis coordinates concurrent duplicate operations;
- PostgreSQL uniqueness/transactions protect final correctness;
- stress test cannot create duplicate logical payment for one merchant/key;
- replays are deterministic;
- payload mismatch is rejected;
- lock expiry does not allow duplicate committed outcomes.

## Data/ML

- synthetic history is reproducible;
- feature snapshots are leakage-safe;
- churn is future 60-day inactivity;
- chronological evaluation is used;
- recency baseline exists;
- XGBoost baseline exists;
- RFM vs RFM+failure comparison exists;
- `scale_pos_weight` is the first imbalance method;
- test metrics are reported;
- SHAP explanations exist.

## Integration

- churn-risk endpoint derives data internally;
- model version/metadata is explicit;
- duplicate HTTP retries never become duplicate ML payment events.

---

# 70. V1 Decisions That Are Now CLOSED

| Question | V1 decision |
|---|---|
| Reuse old domain code? | No; clean rebuild |
| Core database tables | Merchant, Payment, IdempotencyRecord |
| Payment/transaction table name | `payments` |
| ML features stored in payment rows? | No |
| Static `is_churned` column? | No |
| Cached `last_transaction_at` in V1? | No |
| Money storage | integer minor units |
| Payment statuses | PENDING / SUCCESS / FAILED |
| Idempotency key scope | merchant-scoped |
| Same key + different payload | reject |
| Durable correctness authority | PostgreSQL |
| Redis role | distributed coordination |
| DB idempotency record expiry | no V1 expiry/cleanup |
| Snapshot unit | merchant × time |
| Snapshot cadence | 7 days |
| Observation history | 90 days |
| Future churn horizon | 60 days |
| Current prediction population | merchants active within prior 60d |
| Minimum tenure for snapshot | 90 days |
| Churn activity definition | any logical payment attempt, SUCCESS or FAILED |
| Frequency representation | numeric levels + change |
| Monetary feature | successful payment amounts |
| Failure features | recent + previous + change |
| Tenure | yes |
| Industry | store, do not train on initially |
| Primary model | XGBoost classifier |
| First imbalance method | `scale_pos_weight` |
| SMOTEENN | deferred experiment |
| Genetic algorithm tuning | deferred experiment |
| Random train/test split | forbidden |
| Split style | chronological + purge awareness |
| Required baseline | recency-only |
| Primary evaluation emphasis | PR-AUC + F1 |
| SHAP | yes |
| ML training in FastAPI request | never |
| Inference client supplies RFM? | no; server derives features |
| Model output name | churn score unless calibration is validated |

---

# 71. Explicitly Deferred Decisions / Future Experiments

## ML

- compare 30/60/90-day churn horizons;
- rolling temporal backtesting;
- SMOTE/SMOTEENN;
- genetic-algorithm hyperparameter tuning;
- survival/time-to-churn modeling;
- probability calibration;
- industry-based models;
- seasonal/day-of-week features;
- merchant segmentation;
- additional classifiers;
- real-world dataset replacement;
- online retraining.

## Infrastructure

- real external payment processor;
- provider-side idempotency;
- database idempotency retention/cleanup;
- Kafka/event streaming;
- background queues;
- Kubernetes;
- horizontal PostgreSQL architecture;
- Redis cluster;
- distributed tracing;
- production cloud deployment;
- advanced observability.

Future features should be added because they answer measured problems, not because they sound impressive.

---

# 72. Things That Should Trigger a Design Revisit

## Schema revisit

A genuinely important new observable fact is required for ML or payments but is not represented in the ledger.

Do **not** alter schema simply because another rolling feature is invented.

## Feature revisit

The recency baseline performs almost as well as the full model.

## Synthetic generator revisit

Metrics are implausibly perfect or SHAP merely mirrors hard-coded generator rules.

## Churn-window revisit

The generated business behavior makes 60 days obviously unsuitable or an explicit horizon experiment is undertaken.

## Redis revisit

Observed processing behavior shows the chosen lease strategy is inadequate.

## Algorithm revisit

XGBoost fails on a carefully validated problem and another formulation has a concrete reason to be superior.

---

# 73. Important Conceptual Boundaries

```text
HTTP retry ≠ payment
```

```text
FAILED payment = activity with friction
no payment attempts in future 60d = churn label
```

```text
Merchant row = durable entity
merchant × snapshot = ML observation
```

```text
Redis = coordination
PostgreSQL = durable invariant
```

```text
classifier score ≠ automatically calibrated real-world probability
```

```text
SHAP feature contribution ≠ proof of causality
```

---

# 74. Suggested Development Workflow

Before starting a milestone:

1. read the milestone goal;
2. read the schema/architecture sections it depends on;
3. implement only what is required for its definition of done;
4. write tests for the new invariant;
5. update this file only if a decision actually changes;
6. commit the milestone result;
7. move to the next milestone.

Avoid redesigning future milestones repeatedly while the current milestone is incomplete unless implementation evidence makes the planned design impossible.

---

# 75. Suggested Commit/Milestone Style

Examples:

```text
feat: initialize clean vault-api structure
feat: add canonical merchant and payment models
feat: add idempotency record schema and constraints
feat: add merchant and payment API contracts
feat: generate reproducible merchant payment history
feat: build temporal churn feature snapshots
ml: add recency and xgboost churn baselines
infra: add nginx and three api replicas
feat: enforce postgres idempotency invariant
feat: add redis distributed payment lock
test: add duplicate payment race suite
ml: add shap explanations and saved model artifacts
feat: expose merchant churn-risk endpoint
```

The repository history should explain the architecture's evolution.

---

# 76. Final Project Story for Presentation/Documentation

### Problem 1: distributed retries corrupt payment correctness

A request may be retried or handled concurrently by different stateless workers.

### Engineering solution

Nginx distributes traffic, Redis coordinates ownership, and PostgreSQL transactions plus unique constraints ensure one idempotency operation maps to one durable logical payment.

### Consequence

The ledger contains clean logical behavioral events rather than network retry noise.

### Problem 2: merchants may disengage over time

Instead of predicting churn from a static demographic snapshot, derive behavior from the transaction history itself.

### ML solution

At weekly historical snapshots, summarize the previous 90 days using:
- recency;
- frequency levels/trends;
- monetary behavior;
- failure behavior;
- tenure.

Predict whether the currently active merchant will make zero payment attempts during the following 60 days.

### Evaluation

Compare:
- dummy baseline;
- recency-only baseline;
- RFM XGBoost;
- RFM + failure XGBoost.

Validate chronologically, address imbalance with `scale_pos_weight`, and explain the final model with SHAP.

### Final integration

Expose merchant churn risk through the same API whose clean payment ledger generated the model's behavioral evidence.

That is the coherent identity of `vault-api`.

---

# 77. Immediate Next Action

After this specification is accepted, the next coding task is **not** XGBoost, Redis, or Nginx.

Start with:

```text
Milestone 0
    ↓
project structure + config + DB session + Alembic

Milestone 1
    ↓
Merchant + Payment + IdempotencyRecord SQLAlchemy models

Milestone 2
    ↓
new Pydantic contracts + basic FastAPI routes
```

After those are stable, proceed to the early ML-validation milestones before returning to the distributed-concurrency track.

---

# 78. One-Sentence North Star

> **vault-api is a distributed, idempotent payment ledger whose clean logical transaction history is transformed into leakage-safe temporal merchant features for explainable XGBoost prediction of future merchant inactivity.**
