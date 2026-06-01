
---

# VaultAPI: Idempotent Payment Infrastructure with Predictive Merchant Analytics

## 🚀 The Problem

In a distributed system, things fail in weird ways. A user might click "Pay" twice, a network packet might be retried automatically by a browser, or a server might crash mid-transaction. Without **Idempotency**, you risk charging a user multiple times for a single order.

Furthermore, high-volume merchants don't just need safe transactions; they need to make sense of their transactional data to forecast revenue, manage cash flow, and predict market trends.

This project simulates a high-traffic payment environment where **Exactly-Once** execution is the law, backed by a data-driven forecasting engine for merchant insights.

---

## 🏗️ System Architecture

To make this realistic, we run a distributed cluster managed by Docker Compose:

* **Load Balancer (Nginx):** Distributes incoming traffic across multiple API workers.
* **API Workers (3x FastAPI):** Stateless instances processing payment logic concurrently without sharing memory.
* **Global Lock Manager (Redis):** The "Source of Truth" for temporary state and distributed locking.
* **The Ledger (PostgreSQL):** The final, ACID-compliant resting place for transaction records and historical analytical data.
* **Predictive Analytics Engine:** An isolated forecasting module running scikit-learn models to process historical ledger trends and output future revenue predictions.

---

## 🛠️ Tech Stack

* **Framework:** FastAPI (Python 3.12+)
* **Concurrency:** `asyncio` / `uvicorn`
* **Database:** PostgreSQL (SQLModel / SQLAlchemy)
* **Cache/Lock:** Redis
* **Data & ML:** Scikit-learn, Pandas, Joblib (for model persistence)
* **Orchestration:** Docker & Docker Compose
* **Testing:** Python `httpx` + `asyncio.gather` (to simulate race conditions)

---

## 📋 Key Concepts

* **Idempotency Key:** A unique UUID sent in the header (`X-Idempotency-Key`). Re-sending this key never results in a second charge.
* **Distributed Lock:** Ensuring only one FastAPI worker can "own" a specific `transaction_id` at a time.
* **Atomic Commits:** Using Postgres transactions to ensure money isn't lost if the database crashes mid-update.
* **TTL (Time To Live):** Setting expiration on Redis locks so "Zombie" processes don't block the system forever.
* **Time-Series Revenue Forecasting:** A regression model trained on historical ledger data to predict a merchant's financial metrics for the upcoming week.

---

## 🛣️ Implementation Roadmap

### Phase 1: The Foundation

* [x] Set up basic FastAPI project structure.
* [ ] Set up `docker-compose.yml` with FastAPI and Postgres.
* [ ] Implement basic `/payments` POST endpoint.
* [ ] Create a transactions table with status: `PENDING`, `SUCCESS`, `FAILED`.

### Phase 2: Scaling & Breaking

* [ ] Add Nginx to load balance across 3 FastAPI replicas.
* [ ] Write a `stress_test.py` script to fire 20 identical requests in 100ms.
* [ ] Challenge: Observe the duplicate entries in Postgres (The Failure State).

### Phase 3: The Distributed Fix

* [ ] Integrate Redis for distributed locking.
* [ ] Implement the logic: Acquire Lock -> Check DB -> Process -> Release Lock.
* [ ] Handle `409 Conflict` returns for concurrent requests.

### Phase 4: Resilience

* [ ] Implement PostgreSQL `BEGIN/COMMIT` blocks for atomicity.
* [ ] Add Lock Timeouts to handle container crashes.

### Phase 5: Data Analytics & Predictive Modeling (College Requirement)

* [ ] Write a database seeding script to populate PostgreSQL with 1,000+ historical rows spanning 6 months.
* [ ] Build a standalone ML pipeline using Pandas and Scikit-learn to train a revenue forecasting model.
* [ ] Export the trained model (`sales_model.pkl`) using Joblib.
* [ ] Expose a new endpoint: `GET /api/v1/merchants/{id}/analytics` that calls the model and returns future revenue forecasts alongside historical metrics.

---

## 🚦 Getting Started

1. **Clone the repo**
2. **Spin up the environment:**
```bash
docker-compose up --build

```


3. **Run the Race Condition Test:**
```bash
python scripts/stress_test.py

```



---

## 🧪 Testing the "Race Condition"

The core success metric of this project is passing the Collision Test:

1. Send 5 requests with the same `Idempotency-Key` at the exact same millisecond.
2. **Result:** 1 Success (`201 Created`), 4 Conflicts (`409 Conflict`) or "Already Processed" (`200 OK`).
3. **Database:** Only 1 record must exist in the PostgreSQL ledger.

---


