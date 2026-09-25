# vault-api

**Distributed idempotent payment infrastructure with transaction-driven merchant churn prediction.**

> **Status:** Active V1 rebuild. The architecture and implementation plan are finalized; the codebase is being rebuilt cleanly around the new domain model.

`vault-api` explores a simple idea: **payment correctness and analytics quality are connected**.

In a distributed payment system, the same logical operation may arrive multiple times because of retries, duplicate clicks, timeouts, or concurrent requests reaching different API workers. If those requests create duplicate payment records, the problem is larger than double-processing: the downstream transaction history is also corrupted.

`vault-api` is designed so that many HTTP requests can still resolve to **one logical payment**, producing a clean merchant ledger that can later be used to model merchant behavior and predict future inactivity.

---

## What the project builds

The project has two connected layers.

### 1. Idempotent distributed payment infrastructure

The backend is designed around:

* **Nginx** distributing requests across multiple stateless FastAPI workers;
* **Redis** coordinating concurrent processing with distributed locks;
* **PostgreSQL** enforcing the durable correctness invariant through transactions and uniqueness constraints;
* **merchant-scoped idempotency keys** to identify legitimate retries;
* **request fingerprinting** to reject reuse of the same idempotency key for a different payment;
* concurrency and crash tests that deliberately exercise race conditions.

The V1 guarantee is intentionally precise:

> **For duplicate or concurrent requests using the same merchant-scoped idempotency key, vault-api is designed to commit one logical payment within its PostgreSQL persistence boundary.**

Redis is a coordination layer. PostgreSQL remains the final authority for durable correctness.

### 2. Merchant churn intelligence

The clean logical payment ledger becomes the data source for a behavioral churn model.

Instead of predicting churn from a static customer profile, the ML pipeline asks:

> **Given a merchant's recent transaction behavior at time `t`, will that currently active merchant make zero payment attempts during the following 60 days?**

Historical payments are converted into weekly merchant snapshots using a 90-day observation window. XGBoost then learns from behavioral features derived from the ledger, while SHAP is used to explain individual predictions.

---

## Why these two parts belong together

A retry is not a new business event.

```text
20 duplicate HTTP requests
            │
            ▼
   idempotency handling
            │
            ▼
     1 logical payment
            │
            ▼
  1 event visible to ML
```

Without that separation, network behavior can silently inflate transaction frequency and distort the data used for analytics.

The project therefore treats **idempotency as both a payment-safety mechanism and a data-integrity mechanism**.

---

## Target architecture

```text
                                  ┌─────────────────────┐
                                  │       Client        │
                                  └──────────┬──────────┘
                                             │
                                             ▼
                                  ┌─────────────────────┐
                                  │        Nginx        │
                                  │    Load Balancer    │
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
                     ▼                                               ▼
             ┌────────────────┐                             ┌─────────────────┐
             │     Redis      │                             │   PostgreSQL    │
             │ coordination   │                             │ durable ledger  │
             │ + lock leases  │                             │ + constraints   │
             └────────────────┘                             └────────┬────────┘
                                                                    │
                                                                    ▼
                                                        ┌──────────────────────┐
                                                        │ Feature Generation   │
                                                        │ merchant × snapshot  │
                                                        └──────────┬───────────┘
                                                                   │
                                                                   ▼
                                                        ┌──────────────────────┐
                                                        │ XGBoost Classifier   │
                                                        └──────────┬───────────┘
                                                                   │
                                                   ┌───────────────┴───────────────┐
                                                   ▼                               ▼
                                          ┌────────────────┐             ┌────────────────┐
                                          │ SHAP analysis  │             │ Churn-risk API │
                                          └────────────────┘             └────────────────┘
```

---

## Core data model

The transactional schema intentionally stores **facts**, not ML features.

### `Merchant`

Represents a merchant account.

Core fields include:

* `merchant_id`
* `joined_at`
* `industry`
* `created_at`

### `Payment`

Represents **one logical payment attempt**, not one HTTP request.

Core fields include:

* `payment_id`
* `merchant_id`
* `amount_minor`
* `currency`
* `status` — `PENDING`, `SUCCESS`, or `FAILED`
* `failure_code`
* timestamps

Amounts are stored in the smallest currency unit rather than floating point.

### `IdempotencyRecord`

Maps a merchant-scoped idempotency key and canonical request fingerprint to one stored operation outcome.

The database enforces a unique constraint on:

```text
(merchant_id, idempotency_key)
```

This table is deliberately separate from `payments` so transport/retry state does not pollute the behavioral ledger used by ML.

---

## Idempotent request semantics

The planned payment flow is:

```text
POST /payments
      │
      ▼
validate payload + Idempotency-Key
      │
      ▼
compute canonical request fingerprint
      │
      ▼
check PostgreSQL for completed operation
      │
      ├── same key + same payload ──► replay stored result
      │
      ├── same key + different payload ──► 409 Conflict
      │
      └── not completed
               │
               ▼
          acquire Redis lock
               │
               ▼
          recheck database
               │
               ▼
       atomic PostgreSQL transaction
               │
               ├── create logical payment
               └── store idempotency result
               │
               ▼
             commit
```

Redis reduces duplicate concurrent work, while PostgreSQL transactions and uniqueness constraints remain the final protection against duplicate committed outcomes.

---

## Merchant churn formulation

The ML portion is deliberately **forward-looking**.

### Unit of prediction

```text
merchant × snapshot_time
```

The same merchant can therefore have different risk estimates at different points in its lifecycle.

### V1 temporal definition

* **Snapshot cadence:** every 7 days
* **Observation window:** previous 90 days
* **Prediction horizon:** next 60 days
* **Positive label:** no logical payment attempts during the next 60 days
* both successful and failed attempts count as activity

A merchant with repeated failed payments is still using the platform; the failures may be predictive of later disengagement, but they do not themselves mean the merchant has already churned.

---

## V1 ML features

Features are derived from merchant and payment history rather than stored directly in the core transaction tables.

### Recency

* `recency_days`

### Frequency

* `tx_count_30d`
* `tx_count_prev_30d`
* `tx_count_90d`
* `frequency_change`

### Monetary behavior

* `avg_success_amount_30d`
* `avg_success_amount_prev_30d`
* `monetary_change`

### Payment reliability

* `failure_rate_30d`
* `failure_rate_prev_30d`
* `failure_rate_change`

### Merchant context

* `tenure_days`

`industry` is retained as merchant metadata but is intentionally excluded from the first model so that a synthetic industry assignment does not become an artificial shortcut to churn.

---

## Modeling and evaluation

The first modeling pipeline uses:

* **XGBoost** for binary classification;
* `scale_pos_weight` as the initial class-imbalance strategy;
* chronological train/validation/test splits instead of random shuffling;
* **PR-AUC and F1** as headline metrics;
* precision, recall, ROC-AUC, and confusion matrix as supporting metrics;
* **SHAP** for global and per-merchant interpretation.

The model is not judged by whether it beats an arbitrary benchmark score. It must first beat simpler explanations of the data.

### Required baselines

1. dummy/majority classifier;
2. recency-only baseline;
3. RFM-style XGBoost;
4. RFM + payment-failure XGBoost.

The key experiment is whether transaction trends and payment reliability improve prediction beyond simple inactivity/recency.

---

## Synthetic data

The first ML dataset is generated synthetically because the project requires merchant-level transaction histories rather than a static churn table.

The generator is designed to create:

* merchants with different join dates;
* heterogeneous transaction rates and payment amounts;
* realistic SUCCESS/FAILED outcomes;
* minority churn rather than a 50/50 balanced dataset;
* noisy disengagement trajectories;
* temporary declines and recoveries among non-churning merchants;
* churners that do not all follow one deterministic pattern.

The goal is **learnable but non-trivial behavior**. Near-perfect scores are treated as a potential sign of leakage or an oversimplified generator.

---

## API surface

### Merchant API

```http
POST /merchants
GET  /merchants/{merchant_id}
```

### Payment API

```http
POST /payments
GET  /payments/{payment_id}
```

`POST /payments` uses:

```http
Idempotency-Key: <client-generated-key>
```

### System

```http
GET /health
```

### Analytics — added after model integration

```http
GET /merchants/{merchant_id}/churn-risk
```

The churn endpoint derives features from the server-owned payment ledger. Clients do not submit RFM values manually.

---

## Tech stack

### Backend and infrastructure

* Python 3.12+
* FastAPI
* Uvicorn
* SQLAlchemy 2.x
* Pydantic v2
* PostgreSQL
* asyncpg
* Alembic
* Redis
* Nginx
* Docker / Docker Compose

### Testing

* pytest
* pytest-asyncio
* httpx
* asyncio-based concurrency tests

### Data and ML

* NumPy
* pandas
* PyArrow / Parquet
* scikit-learn
* XGBoost
* SHAP

---

## Planned repository structure

```text
vault-api/
├── app/
│   ├── api/routes/
│   ├── core/
│   ├── db/models/
│   ├── schemas/
│   ├── services/
│   └── main.py
│
├── ml/
│   ├── synthetic/
│   ├── features/
│   ├── baselines/
│   ├── train.py
│   ├── evaluate.py
│   ├── explain.py
│   └── inference.py
│
├── data/
├── artifacts/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── concurrency/
│
├── nginx/
├── alembic/
├── scripts/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── PROJECT_SPEC.md
└── README.md
```

The implementation keeps API routing, business logic, persistence models, validation schemas, and offline ML concerns separate.

---

## Development roadmap

The repository is currently being rebuilt from the foundation rather than incrementally patching the earlier prototype.

* [ ] **Milestone 0 — Clean rewrite foundation**
  Project structure, configuration, async DB session, Alembic, `/health`.

* [ ] **Milestone 1 — Canonical domain schema**
  Merchant, Payment, IdempotencyRecord, constraints, indexes, migrations.

* [ ] **Milestone 2 — Basic single-worker API**
  New Pydantic contracts and merchant/payment endpoints.

* [ ] **Milestone 3 — Synthetic transaction history**
  Reproducible merchant and payment generation.

* [ ] **Milestone 4 — Temporal feature pipeline**
  Leakage-safe weekly snapshots, RFM/reliability features, 60-day labels.

* [ ] **Milestone 5 — ML feasibility baseline**
  Dummy, recency, RFM XGBoost, and RFM+failure comparisons.

* [ ] **Milestone 6 — Distributed race demonstration**
  Nginx, three FastAPI replicas, concurrent stress test.

* [ ] **Milestone 7 — PostgreSQL idempotency semantics**
  Request fingerprints, unique invariant, atomic response replay.

* [ ] **Milestone 8 — Redis coordination**
  Distributed lock ownership, TTL, safe release, concurrent processing behavior.

* [ ] **Milestone 9 — Resilience hardening**
  Rollbacks, integrity recovery, lock-expiry and interruption tests.

* [ ] **Milestone 10 — Final XGBoost + SHAP pipeline**
  Parameter search, threshold selection, frozen evaluation, model artifacts.

* [ ] **Milestone 11 — Churn-risk API**
  Shared feature logic, model loading, top explanatory factors.

* [ ] **Milestone 12 — End-to-end finalization**
  Full tests, documentation, results, limitations, and demonstration.

---

## Current development status

The earlier prototype successfully established basic FastAPI/PostgreSQL/Docker connectivity, but its payment schema and API contracts predated the finalized merchant-churn formulation.

V1 is therefore being implemented as a clean rebuild so that the domain model is correct before Redis, Nginx, or ML code is layered on top.

**The next implementation target is the clean foundation and canonical schema, not model training or distributed locking.**

Local installation and execution commands will be added here as those foundation milestones land, rather than documenting commands for code that does not yet exist in the rebuilt tree.

---

## Design constraints

Several ideas are deliberately deferred from V1:

* Kubernetes
* Kafka
* Celery / Airflow
* feature stores
* external payment-processor integration
* neural networks
* survival analysis
* SMOTEENN
* genetic-algorithm hyperparameter tuning
* online model retraining

They are future experiments, not prerequisites for proving the current architecture.

---

## Detailed implementation specification

The README is intentionally the public-facing overview.

For exact schema fields, constraints, lock semantics, feature definitions, leakage rules, milestone definitions of done, and closed architectural decisions, see:

**[`PROJECT_SPEC.md`](./PROJECT_SPEC.md)**

---

## Project north star

> **vault-api is a distributed, idempotent payment ledger whose clean logical transaction history is transformed into leakage-safe temporal merchant features for explainable XGBoost prediction of future merchant inactivity.**

