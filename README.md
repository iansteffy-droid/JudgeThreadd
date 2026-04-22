# ⚖️ JudgeThreadd: Agentic Evaluation Pipeline

**An LLM-as-a-Judge Observability Tool to catch unreliable AI before it goes live.**

An untested RAG system deployed to production can lead to "silent failures" where the AI hallucinates incorrect return policies, breaches brand safety, or provides bad financial advice, damaging user trust and incurring significant liability. 

Well, not on JudgeThreadd's watch. 

JudgeThreadd is a continuous integration testing tool built to evaluate LLM agents before they reach production. It utilizes a highly parallelized "Council of Judges" to execute the law, ensuring your generative applications are safe, grounded, and technically accurate.

## 🛠️ The Tech Stack
* **Orchestration:** LangGraph (Parallel DAG execution)
* **Backend:** FastAPI (Python, Server-Sent Events/SSE)
* **Frontend:** Vue.js 3 (Tailwind CSS, Vite, Real-time telemetry)
* **Episodic Memory:** Supabase (PostgreSQL with `PostgresSaver`)
* **Semantic Search:** Qdrant Cloud (Vector Database)
* **LLMs:** Groq (Llama 3 70B for the Judges, Llama 3 8B for the baseline agent)

## 🧠 System Architecture

JudgeThreadd accepts a payload (Question, Retrieved Context, Generated Answer) and simultaneously fans out to specialized AI Judges. It streams real-time execution telemetry to the frontend, aggregates the scores, and forces a Human-in-the-Loop review if the AI drifts below acceptable thresholds.

```mermaid
graph TD;
    START((START)) --> Dispatcher[Street Judge Orchestrator];
    Dispatcher --> R[Judge Relevance];
    Dispatcher --> H[Judge Hallucination];
    Dispatcher --> P[Judge Psi Division];
    Dispatcher --> T[Judge Tek Division];
    
    R --> Agg[Chief Judge Aggregator];
    H --> Agg;
    P --> Agg;
    T --> Agg;
    
    Agg -->|Score >= 3.5| END((END));
    Agg -->|Score < 3.5| HITL[Human-In-The-Loop Review];
    HITL --> END;