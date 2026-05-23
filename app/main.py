import json
import asyncio
import os
import uuid
import psycopg
from datetime import datetime
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.agent.baseline_rag import create_rag_app
from app.agent.evaluation_graph import create_eval_app, write_to_markdown_report

app = FastAPI(title="JudgeThreadd Telemetry Server")

uploaded_datasets: dict[str, list] = {}

PROVIDER_LABELS = {
    "groq":   "Groq (Cloud)",
    "ollama": "Ollama (Local)",
}
MODEL_LABELS = {
    "llama-3.3-70b-versatile": "Llama 3.3 · 70B (Versatile)",
    "llama-3.1-8b-instant":    "Llama 3.1 · 8B (Instant)",
    "qwen2.5:3b":              "Qwen 2.5 · 3B",
    "llama3.2:3b":             "Llama 3.2 · 3B",
    "phi3.5":                  "Phi-3.5 Mini · 3.8B",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    question: str

@app.get("/history")
async def get_run_history():
    """Fetches the latest evaluations from Supabase to populate the UI table."""
    try:
        DB_URI = os.environ.get("SUPABASE_DB_URI")
        
        def fetch_db():
            with psycopg.connect(DB_URI, row_factory=dict_row) as conn:
                runs = conn.execute("SELECT * FROM eval_history ORDER BY created_at DESC LIMIT 20").fetchall()
                for run in runs:
                    if run.get('created_at'):
                        run['created_at'] = run['created_at'].strftime("%Y-%m-%d %H:%M:%S")
                return runs
                
        return await asyncio.to_thread(fetch_db)
    except Exception as e:
        return {"error": str(e)}

@app.post("/evaluate")
async def evaluate_sync(request: QueryRequest):
    rag_agent = create_rag_app()
    council_of_judges = create_eval_app()

    rag_state = {"question": request.question, "context": "", "answer": ""}
    rag_result = await asyncio.to_thread(rag_agent.invoke, rag_state)

    if "Street Judge Decree:" in rag_result.get("answer", ""):
        return {"status": "blocked", "message": rag_result["answer"]}

    eval_state = {
        "question": rag_result["question"],
        "context": rag_result["context"],
        "answer": rag_result["answer"],
        "scores": []
    }

    config = {"configurable": {"thread_id": f"sync_eval_{uuid.uuid4()}"}}
    eval_result = await asyncio.to_thread(council_of_judges.invoke, eval_state, config)

    return {"status": "success", "evaluation": eval_result["scores"]}


@app.get("/stream_telemetry")
async def stream_telemetry(question: str, provider: str = "groq", model: str = None, request: Request = None):
    """
    Expects a GET request. Streams the execution trace back to the client.
    """
    rag_agent = create_rag_app(provider=provider, model=model)
    council_of_judges = create_eval_app(provider=provider, model=model)

    async def event_generator():
        try:
            payload = {"event": "info", "message": "🔌 Uplink established. Dispatching Street Judge..."}
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.1) 
            
            # 1. STREAM THE BASELINE RAG AGENT 
            rag_state = {"question": question, "context": "", "answer": ""}
            
            async for chunk in rag_agent.astream(rag_state, stream_mode="updates"):
                if await request.is_disconnected(): break
                
                for node_name, state_update in chunk.items():
                    rag_state.update(state_update) 
                    
                    if node_name == "street_judge":
                        if "Street Judge Decree:" in rag_state.get("answer", ""):
                            payload = {"event": "error", "message": rag_state["answer"]}
                            yield f"data: {json.dumps(payload)}\n\n"
                            return 
                        
                        payload = {"event": "node_end", "message": "✅ Prompt approved. Routing to Tek Division..."}
                        yield f"data: {json.dumps(payload)}\n\n"
                        
                    elif node_name == "retrieve_docs":
                        payload = {"event": "node_end", "message": "📚 Tek Division retrieved context from Qdrant Cloud."}
                        yield f"data: {json.dumps(payload)}\n\n"
                        
                    elif node_name == "generate_answer":
                        payload = {"event": "info", "message": "🤖 Academy Instructor generated answer. Convening Council..."}
                        yield f"data: {json.dumps(payload)}\n\n"

            # 2. EVALUATE THE COUNCIL OF JUDGES
            eval_state = {
                "question": rag_state["question"],
                "context": rag_state.get("context", ""),
                "answer": rag_state["answer"],
                "scores": []
            }
            config = {"configurable": {"thread_id": f"stream_{uuid.uuid4()}"}}

            payload = {"event": "node_start", "message": "⏳ Judges are reviewing the context and answer... (This takes a few seconds)"}
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.1)

            eval_result = await asyncio.to_thread(council_of_judges.invoke, eval_state, config)
            
# --- NEW: WRITE TO MARKDOWN REPORT ---
            try:
                report_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/evaluation_report.md"))
                os.makedirs(os.path.dirname(report_path), exist_ok=True)
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                with open(report_path, "a", encoding="utf-8") as f:
                    f.write(f"\n## Manual UI Execution: {timestamp}\n")
                    f.write(f"**Citizen Question:** {eval_state['question']}\n\n")
                    
                    # Format agent answer beautifully as a markdown blockquote
                    agent_ans = eval_state['answer'].replace('\n', '\n> ')
                    f.write(f"**Agent Answer:**\n> {agent_ans}\n\n")
                    
                    f.write("### Council Member Verdicts\n")
                    f.write("| Judge | Score | Rationale |\n")
                    f.write("| :--- | :---: | :--- |\n")
                    
                    chief_verdict = None
                    for score in eval_result["scores"]:
                        if score["judge_name"] != "CHIEF JUDGE":
                            # Strip newlines from rationale so it doesn't break the markdown table structure
                            safe_rationale = score['rationale'].replace('\n', ' ')
                            f.write(f"| **{score['judge_name']}** | {score['score']}/5 | {safe_rationale} |\n")
                        else:
                            chief_verdict = score
                            
                    if chief_verdict:
                        f.write(f"\n**Chief Judge Score:** {chief_verdict['score']}/5\n")
                        f.write(f"**Overall Rationale:** {chief_verdict['rationale']}\n")
                    f.write("---\n")
            except Exception as e:
                print(f"Failed to write to markdown report: {e}")
            # --------------------------------------

            for score in eval_result["scores"]:
                if score["judge_name"] != "CHIEF JUDGE":
                    judge_name = score["judge_name"]
                    judge_score = score["score"]
                    msg = f"✅ {judge_name} reached a verdict: {judge_score}/5"
                    
                    payload = {"event": "node_end", "message": msg}
                    yield f"data: {json.dumps(payload)}\n\n"
                    await asyncio.sleep(0.2)

            payload = {"event": "info", "message": "⚖️ Chief Judge has aggregated the final scores."}
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.2)
            
            # --- NEW: UI NOTIFICATION FOR THE REPORT ---
            payload = {"event": "info", "message": "📄 A detailed Markdown report has been appended to data/evaluation_report.md"}
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.2)
            
            payload = {"event": "complete", "message": "✅ All verdicts recorded and archived in data/evaluation_report.md."}
            yield f"data: {json.dumps(payload)}\n\n"

        except asyncio.CancelledError:
            print("🚨 Client stream forcefully disconnected due to browser timeout.")
        except Exception as e:
            payload = {"event": "error", "message": f"Server Error: {str(e)}"}
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/upload_dataset")
async def upload_dataset(file: UploadFile = File(...)):
    content = await file.read()
    try:
        dataset = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    if not isinstance(dataset, list):
        raise HTTPException(status_code=400, detail="Dataset must be a JSON array")
    required_keys = {"question", "ground_truth_context", "expected_answer"}
    for i, case in enumerate(dataset):
        if not required_keys.issubset(case.keys()):
            raise HTTPException(
                status_code=400,
                detail=f"Item {i} is missing required fields: {required_keys - case.keys()}"
            )
    dataset_id = uuid.uuid4().hex[:12]
    uploaded_datasets[dataset_id] = dataset
    return {"dataset_id": dataset_id, "case_count": len(dataset)}


@app.get("/stream_dataset_evaluation")
async def stream_dataset_evaluation(request: Request, use_default: bool = True, dataset_id: str = None, provider: str = "groq", model: str = None):
    council_of_judges = create_eval_app(provider=provider, model=model)

    async def event_generator():
        try:
            if not dataset_id or use_default:
                dataset_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/golden_dataset.json"))
                with open(dataset_path, "r") as f:
                    dataset = json.load(f)
                source_name = "golden_dataset.json"
            else:
                if dataset_id not in uploaded_datasets:
                    yield f"data: {json.dumps({'event': 'error', 'message': 'Uploaded dataset not found. Please re-upload.'})}\n\n"
                    return
                dataset = uploaded_datasets[dataset_id]
                source_name = "uploaded dataset"

            total = len(dataset)
            run_id = uuid.uuid4().hex[:8]

            # Initialise a timestamped report file (mirrors evaluation_graph.py main block)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), f"../data/reports/evaluation_report_{timestamp}.md")
            )
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            effective_provider = (provider or os.environ.get("LLM_PROVIDER", "groq")).lower()
            effective_model = model or (
                os.environ.get("LOCAL_MODEL", "qwen2.5:3b")
                if effective_provider == "ollama"
                else os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
            )
            provider_label = PROVIDER_LABELS.get(effective_provider, effective_provider.title())
            model_label = MODEL_LABELS.get(effective_model, effective_model)

            with open(report_path, "w", encoding="utf-8") as f:
                f.write("# 🏛️ Mega-City One: AI Evaluation Archives\n")
                f.write(f"*Session Date: {datetime.now().strftime('%Y-%m-%d')}*\n")
                f.write(f"*Provider: {provider_label}  |  Model: {model_label}*\n\n---\n")
            yield f"data: {json.dumps({'event': 'info', 'message': f'🤖 Provider: {provider_label}  |  Model: {model_label}'})}\n\n"
            await asyncio.sleep(0.05)

            yield f"data: {json.dumps({'event': 'info', 'message': f'⚖️ Council is now in session. Processing {total} cases from {source_name}...'})}\n\n"
            await asyncio.sleep(0.1)

            for index, case in enumerate(dataset, 1):
                if await request.is_disconnected():
                    break

                question = case["question"]
                yield f"data: {json.dumps({'event': 'node_start', 'message': f'📁 Case {index}/{total}: {question}'})}\n\n"
                await asyncio.sleep(0.05)

                # Use ground_truth_context and expected_answer directly — no RAG agent
                eval_state = {
                    "question": question,
                    "context": case["ground_truth_context"],
                    "answer": case["expected_answer"],
                    "scores": []
                }
                config = {"configurable": {"thread_id": f"dataset_{index}_{run_id}"}}

                try:
                    council_result = await asyncio.to_thread(council_of_judges.invoke, eval_state, config)
                    scores = council_result["scores"]

                    for score in scores:
                        if score["judge_name"] != "CHIEF JUDGE":
                            rationale = score["rationale"].replace("\n", " ")
                            msg = f"✅ [{score['judge_name']}] {score['score']}/5 — {rationale}"
                            yield f"data: {json.dumps({'event': 'node_end', 'message': msg})}\n\n"
                            await asyncio.sleep(0.1)

                    chief = next((s for s in scores if s["judge_name"] == "CHIEF JUDGE"), None)
                    if chief:
                        msg = f"⚖️ Chief Judge: {chief['score']}/5 — {chief['rationale']}"
                        yield f"data: {json.dumps({'event': 'info', 'message': msg})}\n\n"

                    await asyncio.to_thread(write_to_markdown_report, question, case["expected_answer"], scores, report_path)

                except Exception as e:
                    yield f"data: {json.dumps({'event': 'error', 'message': f'Case {index} evaluation failed: {str(e)}'})}\n\n"

            report_rel = f"data/reports/evaluation_report_{timestamp}.md"
            yield f"data: {json.dumps({'event': 'complete', 'message': f'✅ All {total} cases evaluated. Report saved to {report_rel}.'})}\n\n"

        except asyncio.CancelledError:
            print("🚨 Dataset stream client disconnected.")
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': f'Server Error: {str(e)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")