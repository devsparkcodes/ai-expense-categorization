# Project Implementation Roadmap
## AI Expense Categorization System (F1 — Expense Categorizer)

---

## 1. Document Information

| Field | Details |
|---|---|
| Document Name | Project Implementation Roadmap |
| Version | 3.0 (Course-Aligned, Supersedes v2.0) |
| Status | Active |
| Author | Technical Project Manager |
| Date | August 4, 2026 |

---

## 2. Important Note

This roadmap is based on the original F1 Expense Categorizer project selected from the institute project catalog. It additionally incorporates RAG and OpenAI Agent SDK as course-required technical implementations while preserving the original business scope and objectives.

---

## 3. Project Overview

The system categorizes financial transactions by identifying the merchant, predicting an expense category, and returning a confidence score. It uses a layered categorization approach: user feedback memory first, then rule-based matching, then AI-based prediction. This roadmap extends that architecture with two course-required technical layers — Retrieval-Augmented Generation (RAG) and the OpenAI Agent SDK — without changing the underlying business problem, scope, or objectives defined in the BRD, SRS, and PCD.

---

## 4. Development Strategy

Development proceeds in the same order the categorization logic depends on: foundation, then transaction data, then each categorization layer in priority order (feedback is architected in after rules and AI exist, since it depends on having something to override), then reporting, then usability features, then the two course-required technical layers, then verification and delivery. RAG and the OpenAI Agent SDK are treated as engineering enhancements to the existing categorization pipeline, not as new business features — they improve *how* the system arrives at a category, not *what* the system promises to the business.

---

## 5. Project Phases

### Phase 1 — Foundation

**Objective**
Establish the technical base the rest of the system is built on.

**Features**
* FastAPI backend
* SQLModel + SQLite database
* Pydantic schemas
* Uvicorn server
* Environment configuration

**Technical Tasks**
* Initialize the FastAPI project with a layered folder structure (routers, services, models, schemas)
* Configure SQLModel with SQLite and automatic table creation
* Set up environment variable handling via `.env` / `.env.example`
* Enable Swagger/OpenAPI documentation
* Initialize Git repository with `.gitignore`

**Deliverables**
* Running FastAPI application skeleton
* Configured SQLite database connection
* Base project structure and Git repository

**Dependencies**
* None

**Completion Criteria**
* Application starts via Uvicorn without errors
* Swagger docs are accessible
* Environment configuration loads correctly

---

### Phase 2 — Core Transaction APIs

**Objective**
Implement transaction data management.

**Features**
* Transaction CRUD
* Create Transaction
* Get All Transactions
* Get Transaction By ID
* Update Transaction Category

**Technical Tasks**
* Define the Transaction SQLModel (description, merchant, category, confidence score, timestamps)
* Implement Create, Get All, Get By ID, and Update Category endpoints
* Define request/response Pydantic schemas
* Implement basic input validation (reject empty/missing description)

**Deliverables**
* Transaction database table
* Working Transaction CRUD API endpoints

**Dependencies**
* Phase 1 — Foundation

**Completion Criteria**
* Transactions can be created, listed, retrieved individually, and have their category updated through the API

---

### Phase 3 — Rule-based Categorization

**Objective**
Implement the first categorization layer using deterministic rules.

**Features**
* Merchant normalization
* Rule-based categorization
* Case-insensitive matching
* Partial matching

**Technical Tasks**
* Build a merchant normalization utility to clean raw transaction text (strip store numbers, city codes, noise)
* Build a rule engine service backed by `merchant_categories.json`
* Implement case-insensitive and partial-match logic against the rule file
* Integrate the rule engine as a categorization step for transactions not yet categorized

**Deliverables**
* Rule engine service
* `merchant_categories.json` reference dataset
* Merchant normalization logic

**Dependencies**
* Phase 2 — Core Transaction APIs

**Completion Criteria**
* Known merchants are correctly categorized by rules alone
* Unmatched merchants fall through to the next categorization step

---

### Phase 4 — AI Categorization

**Objective**
Add AI-based categorization as a fallback when rules do not match.

**Features**
* AI categorization fallback
* Prompt engineering
* Confidence score generation
* Structured output
* Graceful error handling

**Technical Tasks**
* Define an AI categorization agent using the OpenAI Agents SDK with a structured `output_type` (merchant, category, confidence score)
* Write categorization instructions/prompt for the agent
* Integrate the configured AI provider as the model backend
* Implement exception handling and a safe fallback response for provider failures
* Wire the AI step into the flow so it only runs when the rule engine does not produce a match

**Deliverables**
* AI categorization agent with structured output
* Provider-integrated categorization call with error handling

**Dependencies**
* Phase 3 — Rule-based Categorization

**Completion Criteria**
* Transactions unmatched by rules are sent to the AI step and return a structured merchant/category/confidence result
* Provider failures do not crash the request

---

### Phase 5 — Merchant Learning & Feedback

**Objective**
Let the system learn from user corrections and avoid repeat AI calls for known merchants.

**Features**
* Feedback storage
* User corrections
* Feedback-first lookup
* Learning reuse for future transactions

**Technical Tasks**
* Define a CategoryFeedback SQLModel to store corrected merchant-to-category mappings
* Implement an endpoint/flow for submitting a category correction
* Implement a feedback lookup step that runs before the rule engine and AI call
* Update the categorization flow order to: feedback check → rule engine → AI fallback

**Deliverables**
* CategoryFeedback table and storage logic
* Feedback-first categorization flow
* Category correction endpoint

**Dependencies**
* Phase 2 — Core Transaction APIs
* Phase 4 — AI Categorization

**Completion Criteria**
* A corrected merchant is categorized from feedback memory on the next matching transaction
* The AI step is skipped when a feedback match exists

---

### Phase 6 — Analytics

**Objective**
Provide reporting and summary views over categorized transaction data.

**Features**
* Total spending
* Spending by category
* Monthly, weekly, and daily spending
* Top merchants
* Transaction statistics
* Category breakdown
* Spending trends
* Dashboard/summary APIs

**Technical Tasks**
* Build aggregation queries over the Transaction table grouped by category, merchant, and time period
* Implement summary and breakdown API endpoints
* Implement top-merchant ranking logic
* Implement a combined dashboard-style summary endpoint

**Deliverables**
* Analytics API endpoints for totals, category breakdown, top merchants, and time-based trends

**Dependencies**
* Phase 2 — Core Transaction APIs

**Completion Criteria**
* Analytics endpoints return totals and breakdowns that correctly match underlying transaction data

---

### Phase 7 — Batch Classification & Advanced APIs

**Objective**
Support processing multiple transactions at once and improve data retrieval usability.

**Features**
* Batch transaction classification
* Search
* Filtering
* Sorting
* Pagination

**Technical Tasks**
* Implement a batch endpoint that accepts a list of transaction descriptions and runs each through the feedback → rule → AI flow independently
* Ensure a single failed item does not stop the rest of the batch
* Extend the transaction listing endpoint with filter parameters (category, merchant, date range)
* Add search across description and merchant fields, plus sorting and pagination

**Deliverables**
* Batch classification endpoint
* Updated transaction listing endpoint with filtering, search, sorting, and pagination

**Dependencies**
* Phase 3 — Rule-based Categorization
* Phase 4 — AI Categorization
* Phase 5 — Merchant Learning & Feedback

**Completion Criteria**
* A batch of transactions can be submitted and classified in one request with independent per-item results
* Transaction lists can be filtered, searched, sorted, and paginated correctly

---

### Phase 8 — RAG Integration

**Objective**
Add Retrieval-Augmented Generation as a course-required technical layer that grounds AI categorization in reference knowledge.

**Features**
* Vector database for merchant/category reference knowledge
* Embedding generation
* Semantic retrieval
* Retrieval-grounded AI categorization

**Technical Tasks**
* Set up a vector database to store embeddings of merchant and category reference examples
* Generate embeddings for known merchant examples and category descriptions
* Build a retrieval function that performs semantic search over the vector store
* Integrate retrieval into the AI categorization step so retrieved similar examples support the AI prediction, used only when feedback and rule matches are unavailable
* Log retrieval results for review

**Deliverables**
* Populated vector store of merchant/category reference embeddings
* Retrieval function usable by the AI categorization step
* AI categorization step updated to use retrieved context

**Dependencies**
* Phase 4 — AI Categorization
* Phase 5 — Merchant Learning & Feedback

**Completion Criteria**
* The AI categorization step retrieves semantically similar reference examples and uses them to support its prediction
* Retrieval only engages after feedback and rule matches fail, preserving the original categorization priority order

---

### Phase 9 — OpenAI Agent SDK Integration

**Objective**
Formalize categorization as an OpenAI Agents SDK agent with tool calling, as required by the course, replacing ad hoc AI calls with structured agent orchestration.

**Features**
* Agent-based categorization
* Function tools for feedback, rule engine, and RAG retrieval
* Structured agent output
* Tool-calling orchestration

**Technical Tasks**
* Define the categorization Agent using the OpenAI Agents SDK
* Wrap feedback lookup, rule engine lookup, and RAG retrieval as function tools available to the agent
* Define a structured `output_type` for the agent's final response (merchant, category, confidence score, categorization source)
* Update the categorization flow so the agent orchestrates tool calls in the existing priority order (feedback → rules → retrieval-assisted AI)
* Add basic handling for malformed or empty requests at the agent entry point

**Deliverables**
* Agent-based categorization service using the OpenAI Agents SDK
* Function tools for feedback, rule engine, and RAG retrieval
* Structured agent output including categorization source

**Dependencies**
* Phase 5 — Merchant Learning & Feedback
* Phase 8 — RAG Integration

**Completion Criteria**
* A transaction request is handled by the agent, which calls tools in the correct order and returns a structured result
* The categorization source (feedback, rule, or AI/RAG) is visible in the response

---

### Phase 10 — Testing, Documentation & Deployment

**Objective**
Verify system correctness, document the system, and prepare it for real-world use.

**Features**
* Unit tests
* Integration tests
* API tests
* Logging
* Error handling
* Developer documentation
* Deployment configuration

**Technical Tasks**
* Write unit tests for the rule engine, feedback logic, RAG retrieval, and agent tool behavior
* Write integration tests for database interactions
* Write API-level tests for transaction, analytics, batch, RAG, and agent endpoints
* Review and finalize logging and error handling across all services
* Write developer setup documentation
* Prepare basic deployment configuration (environment separation, run instructions)

**Deliverables**
* Unit, integration, and API test suites
* Finalized logging and error handling
* Developer documentation
* Deployment-ready configuration

**Dependencies**
* Phases 1 through 9

**Completion Criteria**
* All core flows are covered by passing tests
* Documentation allows a new developer to set up and run the project
* The system runs correctly in a clean environment

---

## 6. Complete Phase Timeline

| Order | Phase |
|---|---|
| 1 | Foundation |
| 2 | Core Transaction APIs |
| 3 | Rule-based Categorization |
| 4 | AI Categorization |
| 5 | Merchant Learning & Feedback |
| 6 | Analytics |
| 7 | Batch Classification & Advanced APIs |
| 8 | RAG Integration |
| 9 | OpenAI Agent SDK Integration |
| 10 | Testing, Documentation & Deployment |

---

## 7. Dependency Graph

```
Foundation
   ↓
Core Transaction APIs
   ↓
Rule-based Categorization
   ↓
AI Categorization
   ↓
Merchant Learning & Feedback
   ↓
Analytics
   ↓
Batch Classification & Advanced APIs
   ↓
RAG Integration
   ↓
OpenAI Agent SDK Integration
   ↓
Testing, Documentation & Deployment
```

---

## 8. Estimated Overall Project Completion Percentage by Phase

| Phase | Cumulative Completion at End of Phase |
|---|---|
| 1 — Foundation | 10% |
| 2 — Core Transaction APIs | 20% |
| 3 — Rule-based Categorization | 30% |
| 4 — AI Categorization | 40% |
| 5 — Merchant Learning & Feedback | 50% |
| 6 — Analytics | 60% |
| 7 — Batch Classification & Advanced APIs | 70% |
| 8 — RAG Integration | 82% |
| 9 — OpenAI Agent SDK Integration | 92% |
| 10 — Testing, Documentation & Deployment | 100% |
