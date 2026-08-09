# AI Expense Categorization System

An AI-powered backend that automatically categorizes financial transactions
into merchant categories. It uses a deterministic knowledge base and RAG
retrieval as fast, cheap stages, then an LLM (via OpenRouter) as a fallback,
so nearly every transaction gets a category even when nothing is known.

Built with FastAPI, SQLModel, ChromaDB, and the OpenAI Agents SDK.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Main Features](#main-features)
3. [Architecture / Categorization Flow](#architecture--categorization-flow)
4. [Technology Stack](#technology-stack)
5. [Project Structure](#project-structure)
6. [Prerequisites](#prerequisites)
7. [Virtual Environment Setup](#virtual-environment-setup)
8. [Installing Runtime Dependencies](#installing-runtime-dependencies)
9. [Installing Development/Test Dependencies](#installing-developmenttest-dependencies)
10. [Environment Variables (.env)](#environment-variables-env)
11. [RAG Configuration Variables](#rag-configuration-variables)
12. [Database Setup](#database-setup)
13. [Building the Vector Index](#building-the-vector-index)
14. [Running the Application](#running-the-application)
15. [Health Check Endpoint](#health-check-endpoint)
16. [API Endpoint Overview](#api-endpoint-overview)
17. [Testing](#testing)
18. [OpenAI Agents SDK Integration and Fallback](#openai-agents-sdk-integration-and-fallback)
19. [RAG Behavior and Similarity Threshold](#rag-behavior-and-similarity-threshold)
20. [Logging Configuration (LOG_LEVEL)](#logging-configuration-log_level)
21. [Deployment / Running](#deployment--running)
22. [Notes on data/vector_store](#important-notes-about-datavector_store)

---

## Project Overview

This is a transaction categorization API. Each transaction reaching
`POST /transactions/` (or the batch endpoint) is categorized by a staged
pipeline:

1. **Feedback** – manual category corrections stored in the database.
2. **Rule engine** – an embedded merchant knowledge base.
3. **RAG** – similarity retrieval against a Chroma vector store.
4. **AI / Agent** – an LLM capable of categorizing unknown merchants.

The system records a confidence score, a prediction source, and a
`requires_review` flag for every transaction so ambiguous results can be
surfaced for manual confirmation. Manual corrections feed back into the
pipeline via the `CategoryFeedback` table and the vector index.

---

## Main Features

- **Create, list, update, delete, and batch transactions** via REST API.
- **Manual category correction** per transaction (`PATCH .../category`),
  which records `CategoryFeedback` and marks the transaction verified.
- **Deterministic categorization** from feedback and a JSON knowledge base.
- **RAG fallback** using a local sentence-transformers embedding model and a
  local Chroma vector store — no external embedding service required.
- **LLM fallback** through OpenRouter (OpenAI-compatible chat completions).
- **Agentic orchestration** with the OpenAI Agents SDK (structured output,
  tool calling, deterministic priority reconciliation).
- **Analytics** endpoints: summaries, category breakdowns, top merchants, and
  daily/weekly/monthly spending trends.
- **Health check** endpoint and centralized logging.

## Architecture / Categorization Flow

```
                        ┌──────────────────────────────┐
                        │  POST /transactions          │
                        │  create_transaction()        │
                        └──────────────┬───────────────┘
                                       │
                        ┌──────────────▼───────────────┐
                        │  run_categorization()        │  agents/
                        │  (OpenAI Agents SDK)         │
                        └──────────────┬───────────────┘
                                       │ fallback if agent fails
                        ┌──────────────▼───────────────┐
                        │  _categorize_sync()           │  services/transaction.py
                        └──────────────┬───────────────┘
                                       │
     1) Feedback ──► 2) Rule Engine ──► 3) RAG ──► 4) AI/Agent
```

Strict priority order, first stage that produces a category wins:

1. **Feedback** — `lookup_feedback_category(merchant, db)` looks for a manual
   correction in `CategoryFeedback` (exact normalized-name match).
2. **Rule engine** — `lookup_rule_category(merchant)` matches against
   `app/data/merchant_categories.json` (substring match after normalization).
3. **RAG** — `rag_categorize(merchant, db)` retrieves similar merchants.
   A strong match (similarity >= threshold) is used directly; a weak match is
   passed as reference context to the final AI/agent stage.
4. **AI / Agent** — the LLM categorizes the merchant, optionally using the
   weak RAG context as reference only.

Every outcome is normalized to a `CategorizeOutcome`
(`app/schemas/agent.py`):

| Field               | Meaning                                                            |
| ------------------- | ------------------------------------------------------------------ |
| `category`          | One of: Food, Fuel, Transport, Entertainment, Shopping, Healthcare, Education, Bills, Office, Maintenance, Other, Utilities, Uncategorized |
| `confidence`        | `1.0` (rule), RAG cosine similarity (strong rag), `0.5` (ai)       |
| `prediction_source` | `rule_engine` \| `rag` \| `ai` \| `uncategorized`                   |
| `requires_review`   | `False` for rule/rag; `True` for ai and uncategorized               |

The deterministic chain also exists as the synchronous fallback
`_categorize_sync()` in `app/services/transaction.py`, used whenever the
agent layer raises or returns unusable output.

## Technology Stack

- **Python 3.10+** (the codebase uses `X | None` union syntax and PEP 585 generics)
- **FastAPI 0.141.1** & **uvicorn 0.52.0** — HTTP framework/app server
- **SQLModel 0.0.39** / **SQLAlchemy** & **Pydantic 2.13.4** — ORM + schemas
- **SQLite** — local database file (`./expense.db`), created automatically at startup
- **chromadb 1.5.9** — persistent vector store (Chroma)
- **sentence-transformers 5.7.0** — local embedding model
- **openai 2.52.0** — OpenAI-compatible client for OpenRouter
- **openai-agents 0.19.1** — OpenAI Agents SDK orchestration
- **numpy 2.5.1** — cosine-similarity computations
- **python-dotenv 1.2.2** — `.env` loading

## Project Structure

```
.
├── app/
│   ├── main.py                    # FastAPI app, lifespan, /health, production entry (python -m app.main)
│   ├── core/
│   │   └── logging.py             # centralized logging configuration
│   ├── api/
│   │   ├── transaction.py         # /transactions router
│   │   └── analytics.py           # /analytics router
│   ├── agents/
│   │   └── categorization_agent.py # OpenAI Agents SDK orchestration
│   ├── services/
│   │   ├── transaction.py         # create/get/list/update/delete/batch + fallback chain
│   │   ├── categorizer.py         # feedback + rule engine lookups
│   │   ├── rag_service.py         # RAG categorize orchestration
│   │   ├── ai_categorizer.py      # plain OpenRouter chat-completions AI
│   │   └── analytics.py           # analytics aggregates
│   ├── schemas/
│   │   ├── transaction.py         # TransactionCreate, TransactionBatchResult
│   │   ├── rag.py                 # RetrievalResult, RAGContextItem, RAGCategorizeResult
│   │   ├── analytics.py           # AnalyticsSummaryResponse, CategoryBreakdownItem, ...
│   │   └── agent.py               # CategorizeOutcome
│   ├── models/
│   │   ├── transaction.py         # Transaction table
│   │   └── category_feedback.py   # CategoryFeedback table
│   ├── vector_db/
│   │   ├── database.py            # Chroma client + collection handle
│   │   ├── embedder.py            # sentence-transformers wrapper
│   │   ├── indexer.py             # build/refresh index (idempotent upserts)
│   │   └── retriever.py           # similarity retrieval
│   ├── data/
│   │   └── merchant_categories.json  # rule-engine knowledge base
│   ├── prompts/
│   │   └── expense_categorization.txt # LLM system prompt
│   └── database/
│       └── database.py            # SQLite engine + session dependency
├── scripts/
│   └── build_vector_index.py      # CLI to (re)build the Chroma index
├── tests/
│   ├── conftest.py                # in-memory DB fixtures
│   ├── test_api.py                # TestClient API tests
│   ├── test_transaction_agent.py
│   ├── test_unit_agent.py
│   ├── test_unit_analytics.py
│   ├── test_unit_categorizer.py
│   └── test_unit_rag.py
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── .gitignore
```

> The local **vector store** and **SQLite database** are generated at runtime
> and are **not committed** (see [Notes on data/vector_store](#important-notes-on-datavector_store)).

## Prerequisites

- Python 3.10 or newer (tested on Python 3.14).
- `pip` available.
- A virtual environment, e.g. `python -m venv .venv` (see below).
- Internet access on first run so pip/downloads of the embedding model
  (`sentence-transformers/all-MiniLM-L6-v2`) and packages succeed.
- An **OpenRouter API key** for LLM/agent categorization. Without it, the
  deterministic stages, RAG, and a `"Uncategorized"` result still work, but
  no LLM calls are made.

## Virtual Environment Setup

Create and activate a virtual environment from the project root:

```bash
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

## Installing Runtime Dependencies

```bash
pip install -r requirements.txt
```

The first import of the embedder downloads the sentence-transformers model
from the Hugging Face Hub and caches it locally.

## Installing Development/Test Dependencies

```bash
pip install -r requirements-dev.txt
```

`requirements-dev.txt` installs `pytest`, `pytest-asyncio`, and `httpx`
(used by the FastAPI `TestClient`).

## Environment Variable (.env)

Copy the template and edit values:

```bash
# Windows
copy .env.example .env

# Unix
cp .env.example .env
```

`.env` is loaded automatically by `python-dotenv` at import time in
`app/database/database.py`, `app/vector_db/embedder.py`,
`app/vector_db/database.py`, `app/agents/categorization_agent.py`, and
`app/services/ai_categorizer.py`.

The loaded variables (with the shipped defaults in `.env.example`) are:

| Variable | Example | Purpose |
| -------- | ------- | ------- |
| `OPENROUTER_API_KEY` | `your_openrouter_api_key_here` | API key for OpenRouter chat completions and the agent model. Leave empty (or absent) to disable LLM calls. |
| `OPENROUTER_MODEL` | `qwen/qwen3.7-flash` | Chat model used for AI categorization and the agent. |
| `RAG_COLLECTION_NAME` | `merchant_knowledge` | Chroma collection holding merchant knowledge documents. |
| `VECTOR_STORE_DIR` | `./data/vector_store` | Directory where Chroma persists data. Defaults to `./data/vector_store`. |
| `RAG_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Dimensional embedding model. |
| `RAG_TOP_K` | `3` | Number of similar merchants retrieved per query. |
| `RAG_SIMILARITY_THRESHOLD` | `0.70` | Cosine similarity at/above which a match is treated as a strong RAG match. |
| `LOG_LEVEL` | `INFO` | Root log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). Applied by `app/core/logging.py`. |

> **Security:** never commit your real `OPENROUTER_API_KEY`. `.env` is
> listed in `.gitignore`; only `.env.example` (with placeholders) is
> committed.

## RAG Configuration Variables

The RAG pipeline is fully local and driven by four variables:

- **`RAG_EMBEDDING_MODEL`** — the sentence-transformers model loaded once and
  cached by `app/vector_db/embedder.py`. Changing it changes the embedding
  space, so the index should be rebuilt afterward.
- **`RAG_TOP_K`** — how many nearest documents `retrieve_similar_merchants`
  returns (default `3`). All retrieved items are included as context for the
  AI stage; only the best is evaluated against the threshold.
- **`RAG_SIMILARITY_THRESHOLD`** — cosine similarity threshold (default
  `0.70`) in `app/services/rag_service.py`. A retrieved merchant reaches or
  exceeds this -> its category is used directly (`source="rag"`, strong).
  A best match below the threshold yields `source="rag_context"` (weak)
  and the retrieved items are passed to the LLM as reference context so the
  final category still comes from the model. If nothing is retrieved, no RAG
  result is produced and the pipeline skips to the AI stage.
- **`RAG_COLLECTION_NAME`** / **`VECTOR_STORE_DIR`** — where the team
  knowledge collection lives on disk (see [Notes on data/vector_store](#important-notes-on-datavector_store)).

## Database Setup

The application uses a SQLite database file. The engine and session are in
`app/database/database.py`:

- URL: `sqlite:///./expense.db` (a file named `expense.db` in the project root).
- Tables are created automatically when the app **starts up** (lifespan
  handler calls `create_db_and_tables()`), so you usually don't need to do
  anything by hand.

If a fresh database is needed:

```bash
del expense.db   # Windows
rm expense.db    # Unix
```

Then start the app again and it will recreate the file. Note that the
`CategoryFeedback` and `Transaction` tables are recreated empty; the vector
index is independent and must be rebuilt (see next section).

## Building the Vector Index

The Chroma collection is populated/rebuilt by
`app/vector_db/indexer.py` (`build_vector_index(db)`), which is idempotent:
every document is upserted under a stable source-derived id (re-running
updates in place, does not duplicate).

Stored-document data sources:

1. `app/data/merchant_categories.json` (the same knowledge base used by the
   rule engine).
2. `CategoryFeedback` rows.
3. Transactions with `is_verified = True`.

To build or refresh the index from the project root:

```bash
python scripts/build_vector_index.py
```

The script:

- loads the project environment (`.env`),
- opens a database session (`sqlmodel.Session(engine)`),
- calls `build_vector_index(db)`,
- closes the session safely (`with`),
- prints a success message with the collection document count, or an error
  and exits non-zero on failure.

Always run it **from the project root** so relative paths resolve, and so
the embedding model can be downloaded (first run only).

Example output:

```
Vector index built successfully. Collection contains 25 documents.
```

## Running the Application

For development, from the project root:

```bash
uvicorn app.main:app --reload
```

For development with auto-reload on a specific host/port:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API is then at http://127.0.0.1:8000.
Interactive docs: http://127.0.0.1:8000/docs (FastAPI's OpenAPI UI).

## Production Run

Use the production entry point, which binds to `0.0.0.0` and honors the
`PORT` environment variable (default `8000`):

```bash
python -m app.main
```

To run on a custom port:

```bash
# Unix
PORT=8080 python -m app.main

# Windows (PowerShell)
$env:PORT = "8080"; python -m app.main
```

Equivalent plain Uvicorn invocation (also binds `0.0.0.0`, expects workers /
reverse proxy configuration appropriate to your host):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Health Check

```bash
curl http://127.0.0.1:8000/health
```

Returns `200`:

```json
{"status": "healthy"}
```

Use this to verify a deployed instance is up after starting it.

## API Endpoint Overview

Base URL: `http://127.0.0.1:8000`. Prefixes are `/transactions` and
`/analytics`.

### Transactions

| Method | Path | Description | Notes |
| ------ | ---- | ----------- | ----- |
| `GET` | `/transactions/` | List transactions with filters, sorting, pagination | Query params: `category`, `merchant`, `search`, `start_date`, `end_date`, `sort_by` (`transaction_date`/`amount`/`merchant_name`), `order` (`asc`/`desc`), `page` (>=1), `limit` (>0). Default sort `transaction_date desc`, `page=1`, `limit=10`. |
| `GET` | `/transactions/{transaction_id}` | Get a single transaction | `404` if not found. |
| `POST` | `/transactions/` | Create a transaction (`201`); auto-categorizes | Body: `TransactionCreate`. |
| `POST` | `/transactions/batch` | Create many; returns per-item `TransactionBatchResult` | Per-item `success`/`error`. |
| `PUT` | `/transactions/{transaction_id}` | Full update (does **not** re-categorize) | Body: `TransactionCreate`. |
| `PATCH` | `/transactions/{transaction_id}/category` | Manual category override | Body `{"category": "..."}` — saves `CategoryFeedback`, sets `is_verified=True`, `prediction_source="manual"`. |
| `DELETE` | `/transactions/{transaction_id}` | Delete a transaction | |

`TransactionCreate`:

```json
{
  "merchant_name": "Uber",
  "amount": 250.0,
  "currency": "PKR",
  "description": "ride home",
  "transaction_date": "2024-01-15T18:45:00"
}
```

`Transaction` (response/DB row) carries `category` engine fields:
`predicted_category`, `confidence`, `prediction_source`,
`requires_review`, `is_verified`.

### Analytics

No query params; all aggregate over all transactions.

| Method | Path | Response shape |
| ------ | ---- | -------------- |
| `GET` | `/analytics/summary` | `{total_transactions, total_spending, average_transaction, highest_transaction}` |
| `GET` | `/analytics/category-breakdown` | `[{category, total_spending, transaction_count}]` (sorted by spend) |
| `GET` | `/analytics/top-merchants` | `[{merchant, total_spending, transaction_count}]` (top 10 by spend) |
| `GET` | `/analytics/daily-spending` | `[{period: "YYYY-MM-DD", total_spending}]` |
| `GET` | `/analytics/weekly-spending` | `[{period: "YYYY-Www" (ISO week from SQLite `%G-W%V`), total_spending}]` |
| `GET` | `/analytics/monthly-spending` | `[{period: "YYYY-MM", total_spending}]` |

> There are **no** `/rag` and no `/agents` routers; only the two routers above.

## Testing

Run the full suite from the project root:

```bash
pytest -q
```

Tests:

- `test_api.py` — API behavior via FastAPI `TestClient` (transaction CRUD /
  batch / category, analytics endpoints). All tests use an in-memory SQLite
  database; the real `expense.db` is never touched.
- `test_transaction_agent.py` — end-to-end agent + fallback behavior.
- `test_unit_categorizer.py` — `normalize_merchant_name`, feedback & rule lookups.
- `test_unit_rag.py` — embedder, retriever, `rag_categorize` outcomes (fake
  collection; no Chroma store, no LLM calls).
- `test_unit_analytics.py` — `app/services/analytics.py` aggregates.
- `test_unit_agent.py` — agent priority order & fallback, all with mocked
  runner/LLM.

Fixtures in `tests/conftest.py` create a session-scoped in-memory SQLite
engine (`StaticPool`) and a function-scoped `db` session — tests are isolated
from the local database and never call external services.

## Getting Started

```bash
# 1. set up venv
python -m venv .venv
.venv\Scripts\activate        # or: source .venv/bin/activate

# 2. install deps
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. configure env
copy .env.example .env        # then set OPENROUTER_API_KEY
# Unix: cp .env.example .env

# 4. create DB + vector index
uvicorn app.main:app --reload   # creates tables on startup
python scripts/build_vector_index.py   # build Chroma index

# 5. run tests
pytest -q
```

## OpenAI Agents SDK Integration and Fallback

`app/agents/categorization_agent.py` wraps the same four-stage
classification with the **OpenAI Agents SDK** (`openai-agents`), using:

- `Runner.run_sync(starting_agent=agent, input=...)` to drive a single-turn
  classification,
- `output_type=CategorizeOutcome` for **structured output** (guaranteed JSON
  shape),
- `function_tool` tools surfaced to the model: `lookup_feedback`,
  `lookup_rule_engine`, `rag_retrieval`, and `ai_categorize`,
- `ModelSettings(temperature=0, max_tokens=100)` for deterministic, short
  outputs,
- a base prompt from `app/prompts/expense_categorization.txt` plus the
  priority instructions enforcing the Feedback → Rule → RAG → AI order.

**Fallback behavior** (from `run_categorization`):

- Empty/whitespace merchant → `Uncategorized` (`requires_review=True`), no
  agent built.
- Missing `OPENROUTER_API_KEY` → `_build_agent` raises; caught and the
  `_categorize_sync()` **synchronous pipeline** (feedback→rule→RAG→AI) is
  used instead.
- Agent **raises** during `Runner.run_sync` → same synchronous fallback.
- Agent returns non-`CategorizeOutcome` output, or a category-less outcome →
  falls back to the legacy pipeline.
- **Deterministic reconcile** (`_reconcile_priority`): after the agent returns,
  the cheap deterministic stages (feedback, rule, strong RAG) are re-checked
  and override any lower-priority agent result — so a rule match never gets
  trumped by AI.

This means the system works end-to-end **without a key**, degrading gracefully
to deterministic + local-RAG + (when configured) direct OpenRouter chat.

## RAG Behavior and Similarity Threshold

`app/services/rag_service.py` implements:

- Retrieve top-K nearest documents (`RAG_TOP_K`, default 3) for the merchant
  query via Chroma.
- Compute **cosine similarity** between the query embedding and each
  candidate (independent of Chroma's internal space).
- **Strong match** (`source="rag"`): best similarity ≥
  `RAG_SIMILARITY_THRESHOLD` (default `0.70`). Uses the retrieved
  category directly, `requires_review=False`.
- **Weak match** (`source="rag_context"`): best similarity < threshold. Returns
  all retrieved items as context, and the pipeline passes them to the AI/agent
  stage as reference only; the category still comes from the model.
  `requires_review=True`.
- **No results / retrieval failure**: `rag_categorize` returns `None`, and
  the pipeline proceeds straight to the AI stage.

The exact threshold is tunable per deployment via `RAG_SIMILARITY_THRESHOLD`;
lower it for more lenient strong matches, and raise for stricter ones. The
index must exist for retrieval to return results — build it with
`python scripts/build_vector_index.py`.

## Logging Configuration (`LOG_LEVEL`)

- Centralized config lives in `app/core/logging.py`.
- `setup_logging()` is called in the FastAPI **lifespan** startup:
  `LOG_LEVEL` (default `INFO`) sets root level; the log **format** is:

  ```
  %(asctime)s | %(levelname)-8s | %(name)s | %(message)s
  ```

- Handlers are added once (idempotent), safe under uvicorn reloads and
  multiple startups.
- Services log through module loggers (`app.services.rag_service`,
  `app.agents.categorization_agent`, `app.services.transaction`,
  `app.services.ai_categorizer`). No secrets, API keys, or sensitive
  transaction body data are ever logged. RAG/AI mismatch events and agent
  failures are logged with `logger.info/warning/exception`.

Example:

```bash
LOG_LEVEL=DEBUG uvicorn app.main:app --reload
```

## Deployment / Running

The current project supports **running as a FastAPI/uvicorn server with a
production entry point** (no Docker/CI setup exists yet):

- Development: `uvicorn app.main:app --reload`
- Production: `python -m app.main` — binds `0.0.0.0`, honors `PORT`
  (default `8000`). Equivalent: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

Deploy an instance:

1. Install runtime deps: `pip install -r requirements.txt`.
2. Set a real `OPENROUTER_API_KEY`/`OPENROUTER_MODEL` in your `.env`.
3. Build the vector index once: `python scripts/build_vector_index.py`.
4. Ensure `VECTOR_STORE_DIR` points to a persistent volume (e.g. a mounted
   disk/bind mount); the data under it is generated and not versioned.
5. Ensure `expense.db` is writable/backed up (SQLite single-file database).
6. Start the server: `python -m app.main` (or set `PORT` first).
7. Verify it is up: `curl http://<host>:<port>/health` → `{"status": "healthy"}`.

## Important Notes about data/vector_store

- `data/vector_store/` is the Chroma persistent storage directory,
  auto-created by `app/vector_db/database.py` when the collection is first
  accessed. It is **strictly generated at runtime**.
- It is **git-ignored** (`.gitignore` → `data/vector_store/`) and
  **not committed** — the repo ships no binary vector data.
- Rebuild it any time the knowledge sources change (edited JSON KB, new
  `CategoryFeedback`, newly verified transactions) with:
  ```bash
  python scripts/build_vector_index.py
  ```
- Deleting it is safe (it can be rebuilt); do that to reset the RAG
  knowledge store.

## License / Status

Project in early development; API surface may change. For local development,
a working test suite is included (119 tests across six files).