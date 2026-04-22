<p align="center">
    <img width="350" height="350" alt="JudgeThreadd" src="https://github.com/user-attachments/assets/dbe1fb0b-d289-430b-9273-f2ee6069a1bc" />
</p>


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

## 🧪 How to Use This to Improve Your Agents

While the Grand Hall UI is excellent for visually debugging a single prompt in real-time, the true power of JudgeThreadd is **Automated Batch Evaluation**. 

Here is the step-by-step workflow to use this repository to test if a new LLM, a new prompt, or a different retrieval strategy makes your RAG system better or worse.

### Step 1: Define Your Dataset
To test an agent, you need a baseline of questions. 
* Open `data/golden_dataset.json` and observe the format of Python related questions.
* Replace the contents with a JSON array of your own historical user queries and the expected ground-truth contexts.

### Step 2: Modify the "Brain" (Your Agent)
This pipeline evaluates whatever logic exists inside `app/agent/baseline_rag.py`. 

To test a change, open that file and modify the variables:
* **Testing a new model:** Locate the LLM initialization and change `model="llama-3.1-8b-instant"` to a different model (e.g., `gemma2-9b-it`).
* **Testing a new prompt:** Update the `prompt_template` string with new instructions to see if the AI adheres to them better.
* **Testing retrieval:** Change the vector database `search_kwargs={"k": 2}` to retrieve more or fewer documents.

### Step 3: Run the Batch Evaluator
Do not type questions one by one into the UI. Instead, run the automated integration test:
```bash
poetry run python app/agent/judge_the_agent.py
