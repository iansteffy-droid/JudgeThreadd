# JudgeThreadd — Project Specs

## What this app does

JudgeThreadd is an LLM-as-a-Judge evaluation pipeline for RAG (Retrieval-Augmented Generation) systems.

A developer uploads a PDF as the knowledge base, asks questions against it, and a council of 5 AI judges automatically scores each answer. Results are streamed live to the UI and stored in a database for review.

**Who uses it:** Developers and AI engineers who want to catch silent failures in their RAG systems before production.

---

## Tech Stack

| Layer | Choice |
| --- | --- |
| Backend language | Python 3.10+ |
| Backend framework | FastAPI + Uvicorn |
| AI orchestration | LangGraph 1.1, LangChain 1.2 |
| LLM providers | Groq Cloud (default) or Ollama (local) |
| LLM factory | `app/agent/llm_factory.py` |
| Embeddings | HuggingFace `sentence-transformers/all-MiniLM-L6-v2` |
| Vector DB | Qdrant Cloud — collection: `portfolio_docs` |
| Relational DB | Supabase PostgreSQL — table: `eval_history` |
| Checkpointing | LangGraph `PostgresSaver` (fallback: `MemorySaver`) |
| Frontend framework | Vue 3 + TypeScript |
| Build tool | Vite |
| Styling | Tailwind CSS |
| Dependency management | Poetry (`pyproject.toml`) |

---

## Pages and User Flows

### 1. Single Query Evaluation
- User types a question in the UI
- Backend runs the RAG agent (Street Judge validates → Qdrant retrieves docs → LLM answers)
- Council of 5 judges evaluates the answer in parallel
- Results streamed live to the UI via Server-Sent Events (SSE)
- Chief Judge score + verdict saved to Supabase
- History table refreshes

### 2. Batch Dataset Evaluation
- User uploads a JSON test dataset (or uses `data/golden_dataset.json`)
- Backend loops through every test case
- Each case: RAG generates answer → Council evaluates
- Results streamed live + written to a timestamped markdown report in `data/reports/`

### 3. PDF Ingestion
- User uploads a PDF via the UI
- Backend chunks the PDF, embeds it with HuggingFace, and uploads to Qdrant
- All future RAG queries use the new content
- Default content: `public/test-content/thinkpython.pdf`

### 4. History View
- On page load, the UI fetches the last 20 evaluations from Supabase
- Table shows: ID, question, chief score, status (APPROVED / DRIFT DETECTED), timestamp
- Rows with score < 3 are highlighted red (drift detected)

---

## Data Models

### AgentState (RAG agent state)
```
question: str
context:  str
answer:   str
```

### EvalState (Council of Judges state)
```
question: str
context:  str
answer:   str
scores:   list[EvaluationScore]  # operator.add reducer — parallel aggregation
```

### EvaluationScore (structured LLM output)
```
name:      str   # judge name
score:     int   # 1–5
rationale: str
```

### eval_history (Supabase table)
```
id:          serial primary key
question:    text
chief_score: float
status:      text   # "APPROVED" or "DRIFT DETECTED"
logprobs:    jsonb  # optional
created_at:  timestamptz
```

### golden_dataset.json schema
```json
[
  {
    "question": "...",
    "ground_truth_context": "...",
    "expected_answer": "..."
  }
]
```

---

## Third-Party Services

| Service | Purpose | Key env var |
| --- | --- | --- |
| Groq | Cloud LLM inference | `GROQ_API_KEY` |
| Qdrant Cloud | Vector store for document retrieval | `QDRANT_URL`, `QDRANT_API_KEY` |
| Supabase | PostgreSQL for eval history + checkpoints | `SUPABASE_DB_URI` |
| Ollama | Optional local LLM (no key needed) | `LLM_PROVIDER=ollama`, `LOCAL_MODEL` |

---

## API Endpoints

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/history` | Returns last 20 rows from `eval_history` |
| POST | `/evaluate` | Synchronous single-query evaluation |
| GET | `/stream_telemetry` | SSE: single query RAG + Council, streams events |
| POST | `/upload_dataset` | Accepts JSON test cases, stores in memory |
| POST | `/upload_pdf` | Saves PDF to `public/test-content/`, returns `pdf_key` |
| GET | `/stream_ingest` | Chunks + embeds PDF, uploads to Qdrant |
| GET | `/stream_dataset_evaluation` | SSE: batch evaluation over dataset |

---

## File Structure

```
JudgeThreadd/
├── app/
│   ├── main.py                    # FastAPI server + all endpoints
│   └── agent/
│       ├── baseline_rag.py        # RAG agent (Street Judge + retriever + answer generator)
│       ├── evaluation_graph.py    # Council of Judges (5 parallel judges + aggregator)
│       ├── judge_the_agent.py     # Async batch evaluation runner
│       ├── generate_dataset.py    # Golden dataset generator
│       └── llm_factory.py         # Groq / Ollama provider abstraction
├── frontend/
│   └── src/
│       ├── App.vue                # Root component
│       └── components/
│           ├── QueryInput.vue     # Single query + dataset upload UI
│           ├── TraceConsole.vue   # Live SSE event log
│           ├── HistoryTable.vue   # Evaluation history table
│           ├── ModelSelector.vue  # Provider/model dropdown
│           └── TestContentUploader.vue  # PDF ingestion UI
├── data/
│   ├── golden_dataset.json        # Default test cases (10 Python questions)
│   └── reports/                   # Timestamped batch evaluation reports
├── public/test-content/
│   └── thinkpython.pdf            # Default knowledge base
├── init_db.py                     # One-time DB + Qdrant bootstrap
├── pyproject.toml                 # Python dependencies (Poetry)
├── .env                           # API keys (never commit)
└── .env.example                   # Key names template
```

---

## What "Done" Looks Like

The current working state of the project:

- `init_db.py` bootstraps Qdrant collection + Supabase tables on first run
- Backend serves all 7 endpoints without errors
- Single query flow: question → RAG → 5 judges → score → Supabase → UI
- Batch flow: dataset → per-case RAG + evaluation → markdown report in `data/reports/`
- PDF ingestion replaces the active Qdrant collection
- Frontend streams live telemetry, shows history, supports model/provider switching
- All 5 env vars (`GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `SUPABASE_DB_URI`, `LLM_PROVIDER`) must be set

---

## Running Locally

```bash
# 1. Copy and fill env vars
cp .env.example .env

# 2. Install dependencies
poetry install

# 3. Bootstrap the database (run once)
python init_db.py

# 4. Start backend
uvicorn app.main:app --reload

# 5. Start frontend (separate terminal)
cd frontend && npm install && npm run dev
```
