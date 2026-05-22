import os
import re
import json
import operator
from app.agent.baseline_rag import AgentState
from typing import Annotated, List
from pydantic import BaseModel, Field, field_validator
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
    score: int = Field(description="Score from 1 to 5.")
    rationale: str = Field(description="Detailed explanation of the score.")
    citation: str = Field(description="A direct verbatim quote from the context or answer that most supports your verdict. Must be an exact excerpt, not a paraphrase.")

    @field_validator("score", mode="before")
    @classmethod
    def coerce_score(cls, v):
        if isinstance(v, int):
            return v
        match = re.search(r"\d", str(v))
        return int(match.group()) if match else 3

class EvalState(AgentState):
    scores: Annotated[List[dict], operator.add]

# --- PROMPT TEMPLATES ---
relevance_template = PromptTemplate.from_template(
    "You are Judge Relevance. Your job is to determine how well the answer actually addresses the question, "
    "using the context as the authoritative source of truth. Be critical — partial answers should not receive high scores.\n\n"
    "<question>\n{question}\n</question>\n\n"
    "<context>\n{context}\n</context>\n\n"
    "<answer>\n{answer}\n</answer>\n\n"
    "Scoring rubric:\n"
    "5 — Answer directly and completely addresses every aspect of the question\n"
    "4 — Addresses the main question but misses minor details asked for\n"
    "3 — Partially addresses the question with notable gaps or omissions\n"
    "2 — Tangentially related to the question but mostly misses the point\n"
    "1 — Does not address the question at all\n\n"
    "Provide your score, a rationale explaining the score, and a direct verbatim citation from the context or answer that most supports your verdict."
)

hallucination_template = PromptTemplate.from_template(
    "You are Judge Hallucination. Your job is to detect whether the answer introduces facts, claims, or details "
    "that are NOT explicitly present in the context. Assume the answer is hallucinated until proven otherwise — "
    "every claim must be traceable to specific text in the context.\n\n"
    "<question>\n{question}\n</question>\n\n"
    "<context>\n{context}\n</context>\n\n"
    "<answer>\n{answer}\n</answer>\n\n"
    "Scoring rubric:\n"
    "5 — Every factual claim in the answer is explicitly present in the context\n"
    "4 — Nearly all claims are grounded; at most one detail is implied but not stated verbatim\n"
    "3 — Most claims are grounded, but 1–2 claims noticeably exceed or are absent from the context\n"
    "2 — Many claims go beyond or directly contradict the context\n"
    "1 — The answer contains numerous invented facts not present in the context\n\n"
    "Provide your score, a rationale explaining the score, and a direct verbatim citation of the specific claim "
    "in the answer that most clearly demonstrates your verdict (quote the hallucinated or grounded text)."
)

faithful_template = PromptTemplate.from_template(
    "You are Judge Faithful. Your job is to determine whether the answer is derived ONLY from the provided context, "
    "with no injection of outside knowledge. Any claim in the answer that cannot be traced to the context is a faithfulness violation.\n\n"
    "<context>\n{context}\n</context>\n\n"
    "<answer>\n{answer}\n</answer>\n\n"
    "Scoring rubric:\n"
    "5 — Entirely grounded in the context; no outside knowledge introduced\n"
    "4 — Predominantly grounded; minor inferences tightly derived from the text\n"
    "3 — Mix of grounded and ungrounded statements — some outside knowledge crept in\n"
    "2 — Mostly reliant on outside knowledge rather than the provided context\n"
    "1 — Completely ignores or contradicts the provided context\n\n"
    "Provide your score, a rationale explaining the score, and a direct verbatim citation from the context or answer "
    "that most clearly demonstrates whether the answer stayed faithful or strayed."
)

psi_division_template = PromptTemplate.from_template(
    "You are Judge Psi Division. Your job is to evaluate whether the answer correctly addresses the underlying intent "
    "of the question — not just the surface wording. Identify if the agent misunderstood the goal, answered a different "
    "question, or failed to decompose a complex question into the correct sub-problems.\n\n"
    "<question_intent>\n{question}\n</question_intent>\n\n"
    "<answer>\n{answer}\n</answer>\n\n"
    "Scoring rubric:\n"
    "5 — Perfectly addresses the user's underlying intent; no misalignment\n"
    "4 — Mostly on-target; minor misalignment with the true intent\n"
    "3 — Understands part of the goal but misses key aspects of what was actually being asked\n"
    "2 — Misunderstands the primary goal; answer is tangentially related at best\n"
    "1 — Completely misinterprets the intent; answers a different question entirely\n\n"
    "Provide your score, a rationale explaining the score, and a direct verbatim citation from the answer "
    "that best illustrates whether the intent was understood or missed."
)

tek_division_template = PromptTemplate.from_template(
    "You are Judge Tek Division. Your job is to verify the technical accuracy of every factual claim, "
    "code snippet, algorithm, or definition in the answer. A single incorrect technical claim is enough to lower the score. "
    "Do not give benefit of the doubt — check each technical assertion carefully.\n\n"
    "<question>\n{question}\n</question>\n\n"
    "<answer>\n{answer}\n</answer>\n\n"
    "Scoring rubric:\n"
    "5 — All code, algorithms, and definitions are technically correct per modern standards\n"
    "4 — Mostly correct; minor imprecision that would not cause bugs or mislead\n"
    "3 — At least one technical inaccuracy that could mislead a learner\n"
    "2 — Multiple technical errors; code or logic would behave incorrectly\n"
    "1 — Technically flawed throughout; code would fail or produce wrong results\n\n"
    "Provide your score, a rationale explaining the score, and a direct verbatim citation of the specific technical "
    "claim or code in the answer that most clearly supports your verdict."
)

# --- SHARED HELPERS (no LLM dependency) ---
def extract_score(result, judge_name):
    parsed = result.get("parsed")
    if parsed is None:
        output_dict = {"score": 3, "rationale": "Structured output parsing failed."}
    else:
        output_dict = parsed.model_dump()
    raw_msg = result["raw"]
    logprobs = raw_msg.response_metadata.get("logprobs") if hasattr(raw_msg, "response_metadata") else None
    return {
        "scores": [{
            "judge_name": judge_name,
            "score": output_dict["score"],
            "rationale": output_dict["rationale"],
            "citation": output_dict.get("citation", ""),
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
        total_score += score['score']
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
        if score['score'] <= 3:
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
    eval_app.invoke(test_state, config={"configurable": {"thread_id": "test_failure_case"}})
