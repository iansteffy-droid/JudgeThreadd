import os
import json
import operator
from app.agent.baseline_rag import AgentState
from typing import Annotated, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from app.agent.llm_factory import get_llm

load_dotenv()

if os.environ.get("LLM_PROVIDER", "groq").lower() != "ollama" and not os.environ.get("GROQ_API_KEY"):
    raise ValueError("🚨 GROQ_API_KEY is missing. Please check your .env file.")
if not os.environ.get("SUPABASE_DB_URI"):
    raise ValueError("🚨 SUPABASE_DB_URI is missing. Please check your .env file.")

DB_URI = os.environ.get("SUPABASE_DB_URI")

connection_pool = None
_db_available = False
try:
    import psycopg as _psycopg
    _psycopg.connect(DB_URI, connect_timeout=5).close()
    connection_pool = ConnectionPool(conninfo=DB_URI, max_size=20)
    _db_available = True
except Exception as _e:
    print(f"⚠️  Database unavailable ({_e}). Running without Supabase persistence.")

class EvaluationScore(BaseModel):
    name: str = Field(description="The exact name of the judge providing this score.")
    score: str = Field(description="Score from 1 to 5.")
    rationale: str = Field(description="Detailed explanation.")

class EvalState(AgentState):
    scores: Annotated[List[dict], operator.add]

# --- PROMPT TEMPLATES ---
relevance_template = PromptTemplate.from_template(
    "You are Judge Relevance. Evaluate how well the answer addresses the question based ONLY on the context.\n\n"
    "<question>\n{question}\n</question>\n\n"
    "<context>\n{context}\n</context>\n\n"
    "<answer>\n{answer}\n</answer>\n\n"
    "Output a score from 1-5 where 5 is perfectly relevant."
)

hallucination_template = PromptTemplate.from_template(
    "You are a Judge of agent Hallucinations. \n"
    "You read and understand everything in the context and can always tell if the answer contains details that \n"
    "are not present in the context. \n\n"
    "<question>\n{question}\n</question>\n\n"
    "<context>\n{context}\n</context>\n\n"
    "<answer>\n{answer}\n</answer>\n\n"
    "Score 5 if perfectly grounded (no hallucinations), 1 if completely hallucinated."
)

faithful_template = PromptTemplate.from_template(
    "You are Judge Faithful. Evaluate if the answer is derived ONLY from the provided context.\n"
    "Does the answer contain any information that is not supported by or derived from the context?\n\n"
    "<context>\n{context}\n</context>\n\n"
    "<answer>\n{answer}\n</answer>\n\n"
    "Score 5 if perfectly faithful to the document, 1 if completely unfaithful."
)

psi_division_template = PromptTemplate.from_template(
    "You are Judge Psi Division. Evaluate if the answer correctly addresses the underlying goal or if it missed the point.\n"
    "Identify if the agent should be breaking down a complex question into easier-to-answer chunks and/or discover where and why the agent\n"
    "misunderstood the goal of the question. \n\n"
    "<question_intent>\n{question}\n</question_intent>\n\n"
    "<answer>\n{answer}\n</answer>\n\n"
    "Score 5 if perfectly aligned, 1 if misinterpreted."
)

tek_division_template = PromptTemplate.from_template(
    "You are Judge Tek Division. Analyze the technical accuracy of the answer.\n"
    "Specifically, check if any Python code, algorithms, or technical definitions provided in the Answer are factually correct according to modern software engineering standards.\n\n"
    "<question>\n{question}\n</question>\n\n"
    "<answer>\n{answer}\n</answer>\n\n"
    "Score 5 if technically flawless, 1 if code or logic is flawed."
)

# --- SHARED HELPERS (no LLM dependency) ---
def extract_score(result, judge_name):
    output_dict = result["parsed"].model_dump()
    raw_msg = result["raw"]
    logprobs = raw_msg.response_metadata.get("logprobs") if hasattr(raw_msg, "response_metadata") else None
    return {
        "scores": [{
            "judge_name": judge_name,
            "score": output_dict["score"],
            "rationale": output_dict["rationale"],
            "logprobs": logprobs
        }]
    }

def aggregator_node(state: EvalState):
    print("\n--- FINAL EVALUATION VERDICT ---")

    total_score = 0
    num_judges = len(state['scores'])
    all_logprobs = {}

    for score in state['scores']:
        print(f"[{score['judge_name']}] Score: {score['score']}/5")
        print(f"Rationale: {score['rationale']}\n")
        total_score += int(score['score'])
        if "logprobs" in score and score["logprobs"]:
            all_logprobs[score['judge_name']] = score["logprobs"]

    if num_judges > 0:
        avg_score = total_score / num_judges

        if avg_score >= 3.5:
            rationale = f"Approved. The Academy Instructor meets standards with an average score of {avg_score:.2f}."
            final_score = int(round(avg_score))
        else:
            rationale = f"Denied. The Academy Instructor fell below the 3.5 threshold with an average score of {avg_score:.2f}. Human intervention required."
            final_score = int(round(avg_score))

        chief_judge_verdict = {
            "judge_name": "CHIEF JUDGE",
            "score": final_score,
            "rationale": rationale
        }

        print(f"[CHIEF JUDGE] Score: {avg_score:.2f}/5")
        print(f"Rationale: {rationale}\n")

        try:
            with connection_pool.connection() as conn:
                conn.autocommit = True
                status_text = "APPROVED" if final_score >= 3.5 else "DRIFT DETECTED"
                conn.execute("ALTER TABLE eval_history ADD COLUMN IF NOT EXISTS logprobs JSONB")
                logprobs_json = json.dumps(all_logprobs) if all_logprobs else None
                conn.execute(
                    "INSERT INTO eval_history (question, chief_score, status, logprobs) VALUES (%s, %s, %s, %s)",
                    (state['question'], final_score, status_text, logprobs_json)
                )
        except Exception as e:
            print(f"Failed to log to database: {e}")

        return {"scores": [chief_judge_verdict]}

    return {"scores": []}

def human_review_node(state: EvalState):
    print("\n[PAUSED] A Judge scored a 3 or lower. Waiting for Human Override...")
    return state

def route_after_aggregation(state: EvalState):
    for score in state['scores']:
        if int(score['score']) <= 3:
            return "human_review"
    return "end"


# --- JUDGE NODE BUILDER ---
def _make_judge(structured_llm, template, judge_name, template_keys):
    def judge(state: EvalState):
        kwargs = {k: state[k] for k in template_keys}
        return extract_score(structured_llm.invoke(template.invoke(kwargs)), judge_name)
    return judge


# --- GRAPH FACTORY ---
def create_eval_app(provider: str = None, model: str = None):
    _llm = get_llm(temperature=0.0, for_structured_output=True, provider=provider, model=model)
    _structured_llm = _llm.with_structured_output(EvaluationScore, include_raw=True)

    workflow = StateGraph(EvalState)

    workflow.add_node("relevance",     _make_judge(_structured_llm, relevance_template,     "Judge Relevance",     ["question", "context", "answer"]))
    workflow.add_node("hallucination", _make_judge(_structured_llm, hallucination_template, "Judge Hallucination", ["question", "context", "answer"]))
    workflow.add_node("faithful",      _make_judge(_structured_llm, faithful_template,      "Judge Faithful",      ["context", "answer"]))
    workflow.add_node("psi_division",  _make_judge(_structured_llm, psi_division_template,  "Judge Psi Division",  ["question", "answer"]))
    workflow.add_node("tek_division",  _make_judge(_structured_llm, tek_division_template,  "Judge Tek Division",  ["question", "answer"]))
    workflow.add_node("aggregator",    aggregator_node)
    workflow.add_node("human_review",  human_review_node)

    workflow.add_edge(START, "relevance")
    workflow.add_edge(START, "hallucination")
    workflow.add_edge(START, "faithful")
    workflow.add_edge(START, "psi_division")
    workflow.add_edge(START, "tek_division")

    workflow.add_edge(["relevance", "hallucination", "faithful", "psi_division", "tek_division"], "aggregator")

    workflow.add_conditional_edges(
        "aggregator",
        route_after_aggregation,
        {
            "human_review": "human_review",
            "end": END
        }
    )
    workflow.add_edge("human_review", END)

    if _db_available and connection_pool:
        memory = PostgresSaver(connection_pool)
    else:
        from langgraph.checkpoint.memory import MemorySaver
        memory = MemorySaver()
    return workflow.compile(checkpointer=memory, interrupt_before=["human_review"])


eval_app = create_eval_app()


if __name__ == "__main__":
    test_state = {
        "question": "What is a python tuple?",
        "context": "A tuple is a sequence of values much like a list. The values stored in a tuple can be any type, and they are indexed by integers. The important difference is that tuples are immutable.",
        "answer": "A tuple is a list of values that can be changed at any time. It is exactly the same as a Python dictionary.",
    }
    print("Running parallel evaluation graph...")
    eval_app.invoke(test_state)
