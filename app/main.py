import json
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.agent.baseline_rag import main_app as rag_agent
from app.agent.evaluation_graph import eval_app as council_of_judges

app = FastAPI(title="JudgeThreadd Telemetry Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # can restrict this to "http://localhost:5173" later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    question: str

@app.post("/evaluate")
async def evaluate_sync(request: QueryRequest):
    print(f"📥 Received query: {request.question}")
    
    rag_state = {"question": request.question, "context": "", "answer": ""}
    rag_result = await rag_agent.ainvoke(rag_state)
    
    if "Street Judge Decree:" in rag_result.get("answer", ""):
        return {"status": "blocked", "message": rag_result["answer"]}

    eval_state = {
        "question": rag_result["question"],
        "context": rag_result["context"],
        "answer": rag_result["answer"],
        "scores": []
    }
    
    import uuid
    config = {"configurable": {"thread_id": f"sync_eval_{uuid.uuid4()}"}}
    
    eval_result = await council_of_judges.ainvoke(eval_state, config=config)
    
    return {"status": "success", "evaluation": eval_result["scores"]}

@app.get("/stream_telemetry")
async def stream_telemetry(question: str, request: Request):
    """
    Expects a GET request like: /stream_telemetry?question=What+is+a+tuple
    Streams the execution trace back to the client.
    """
    
    async def event_generator():
        try:
            yield f"data: {json.dumps({'event': 'info', 'message': '🚓 Street Judge reviewing prompt...'})}\n\n"
            
            rag_state = {"question": question, "context": "", "answer": ""}
            rag_result = await rag_agent.ainvoke(rag_state)
            
            if "Street Judge Decree:" in rag_result.get("answer", ""):
                yield f"data: {json.dumps({'event': 'error', 'message': rag_result['answer']})}\n\n"
                return 

            yield f"data: {json.dumps({'event': 'info', 'message': '📚 Academy Instructor generated answer. Convening Council...'})}\n\n"

            eval_state = {
                "question": rag_result["question"],
                "context": rag_result["context"],
                "answer": rag_result["answer"],
                "scores": []
            }
            import uuid
            config = {"configurable": {"thread_id": f"stream_{uuid.uuid4()}"}}

            async for event in council_of_judges.astream_events(eval_state, config=config, version="v2"):
                if await request.is_disconnected():
                    print("Client disconnected.")
                    break
                
                kind = event["event"]
                node_name = event.get("metadata", {}).get("langgraph_node", "unknown")
                
                if kind == "on_chat_model_start":
                    yield f"data: {json.dumps({'event': 'node_start', 'node': node_name, 'message': f'⏳ {node_name} is deliberating...'})}\n\n"
                
                elif kind == "on_chat_model_end":
                    yield f"data: {json.dumps({'event': 'node_end', 'node': node_name, 'message': f'✅ {node_name} has reached a verdict.'})}\n\n"

            yield f"data: {json.dumps({'event': 'complete', 'message': '⚖️ All verdicts recorded.'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")