import json
import asyncio
import os
import uuid
import psycopg
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.agent.baseline_rag import create_rag_app
from app.agent.evaluation_graph import create_eval_app

app = FastAPI(title="JudgeThreadd Telemetry Server")

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