# Vaultlock-API
🚀 The Problem

In a distributed system, things fail in weird ways. A user might click "Pay" twice, a network packet might be retried automatically by a browser, or a server might crash mid-transaction. Without Idempotency, you risk charging a user multiple times for a single order.

This project simulates a high-traffic payment environment where Exactly-Once execution is the law.
🏗️ System Architecture

To make this realistic, we don't just run one script. We run a distributed cluster managed by Docker Compose:

    Load Balancer (Nginx): Distributes incoming traffic across multiple API workers.

    API Workers (3x FastAPI): Stateless instances processing logic. They do not share memory.

    Global Lock Manager (Redis): The "Source of Truth" for temporary state and distributed locking.

    The Ledger (PostgreSQL): The final, ACID-compliant resting place for transaction records.

🛠️ Tech Stack

    Framework: FastAPI (Python 3.12+)

    Concurrency: asyncio / uvicorn

    Database: PostgreSQL (SQLModel / SQLAlchemy)

    Cache/Lock: Redis

    Orchestration: Docker & Docker Compose

    Testing: Python httpx + asyncio.gather (to simulate race conditions)
    📋 Key Concepts\
    Concept,Description
Idempotency Key: A unique UUID sent in the header (X-Idempotency-Key). Re-sending this key should never result in a second charge.
Distributed Lock: "Ensuring only one FastAPI worker can ""own"" a specific transaction_id at a time."
Atomic Commits: Using Postgres transactions to ensure money isn't lost if the database crashes mid-update.
TTL (Time To Live): "Setting expiration on Redis locks so ""Zombie"" processes don't block the system forever."
🛣️ Implementation Roadmap
Phase 1: The Foundation

    [ ] Set up docker-compose.yml with FastAPI and Postgres.

    [ ] Implement basic /payments POST endpoint.

    [ ] Create a transactions table with status: PENDING, SUCCESS, FAILED.

Phase 2: Scaling & Breaking

    [ ] Add Nginx to load balance across 3 FastAPI replicas.

    [ ] Write a stress_test.py script to fire 20 identical requests in 100ms.

    [ ] Challenge: Observe the duplicate entries in Postgres (The Failure State).

Phase 3: The Distributed Fix

    [ ] Integrate Redis for distributed locking.

    [ ] Implement the logic: Acquire Lock -> Check DB -> Process -> Release Lock.

    [ ] Handle 409 Conflict returns for concurrent requests.

Phase 4: Resilience

    [ ] Implement PostgreSQL BEGIN/COMMIT blocks for atomicity.

    [ ] Add Lock Timeouts to handle container crashes.
    🚦 Getting Started

    Clone the repo

    Spin up the environment:
    docker-compose up --build
    Run the Race Condition Test:
    python scripts/stress_test.py
    🧪 Testing the "Race Condition"

The core success metric of this project is passing the Collision Test:

    Send 5 requests with the same Idempotency-Key at the exact same millisecond.

    Result: 1 Success (201 Created), 4 Conflicts (409 Conflict) or "Already Processed" (200 OK).

    Database: Only 1 record must exist.
