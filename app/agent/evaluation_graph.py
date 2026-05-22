import os
import json
import operator
from app.agent.baseline_rag import AgentState
from typing import Annotated, List
from datetime import datetime
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.prompts import PromptTemplate
from app.agent.llm_factory import get_llm
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

load_dotenv()

if os.environ.get("LLM_PROVIDER", "groq").lower() != "ollama" and not os.environ.get("GROQ_API_KEY"):
    raise ValueError("🚨 GROQ_API_KEY is missing. Please check your .env file.")

DB_URI = os.environ.get("SUPABASE_DB_URI")
connection_pool = None
if DB_URI:
    try:
        _pool = ConnectionPool(conninfo=DB_URI, max_size=20, open=False)
        _pool.open(wait=True, timeout=5.0)
        connection_pool = _pool
    except Exception as e:
        print(f"Warning: DB unavailable ({e}). Evaluation history will not be persisted.")

class EvaluationScore(BaseModel):
    name: str = Field(description="The exact name of the judge providing this score.")
    score: str = Field(description="Score from 1 to 5.")
    rationale: str = Field(description="Detailed explanation.")

# --- STATE AND REDUCERS ---
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

def write_to_markdown_report(question, answer, scores, report_path=None):
    if report_path is None:
        report_path = os.path.join(os.path.dirname(__file__), "../../data/evaluation_report.md")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    chief_verdict = next((s for s in scores if s["judge_name"] == "CHIEF JUDGE"), None)
    junior_scores = [s for s in scores if s["judge_name"] != "CHIEF JUDGE"]

    if not os.path.exists(report_path) or os.path.getsize(report_path) == 0:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# 🏛️ Mega-City One: AI Evaluation Archives\n")
            f.write(f"*Session Date: {datetime.now().strftime('%Y-%m-%d')}*\n\n---\n")

    with open(report_path, "a", encoding="utf-8") as f:
        f.write(f"\n## Evaluation: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Question:** {question}\n\n")
        f.write(f"**Answer:**\n> {answer.replace(chr(10), chr(10)+'> ')}\n\n")
        f.write("### Council Member Verdicts\n")
        f.write("| Judge | Score | Rationale |\n")
        f.write("| :--- | :---: | :--- |\n")
        for s in junior_scores:
            clean_rationale = s['rationale'].replace('\n', ' ')
            f.write(f"| **{s['judge_name']}** | {s['score']}/5 | {clean_rationale} |\n")
        if chief_verdict:
            f.write("\n### ⚖️ Final Supreme Decree\n")
            f.write(f"**Chief Judge Score:** {chief_verdict['score']}/5\n\n")
            f.write(f"**Ruling:** {chief_verdict['rationale']}\n")
        f.write("\n---\n")

# --- EVALUATION NODE FACTORIES ---
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

def _make_judge(structured_llm, template, judge_name, fields):
    def judge_fn(state: EvalState):
        input_data = {f: state[f] for f in fields}
        prompt_val = template.invoke(input_data)
        return extract_score(structured_llm.invoke(prompt_val), judge_name)
    return judge_fn

# --- FAN-IN AGGREGATOR ---
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
            if connection_pool is None:
                raise RuntimeError("No DB connection")
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

# --- HUMAN IN THE LOOP ROUTING ---
def human_review_node(state: EvalState):
    print("\n[PAUSED] A Judge scored a 3 or lower. Waiting for Human Override...")
    return state

def route_after_aggregation(state: EvalState):
    for score in state['scores']:
        if int(score['score']) <= 3:
            return "human_review"
    return "end"

# --- FACTORY FUNCTION ---
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

    if connection_pool is not None:
        memory = PostgresSaver(connection_pool)
        memory.setup()
    else:
        memory = MemorySaver()

    return workflow.compile(
        checkpointer=memory,
        interrupt_before=["human_review"]
    )


eval_app = create_eval_app()


if __name__ == "__main__":
    import uuid

    dataset_path = os.path.join(os.path.dirname(__file__), "../../data/golden_dataset.json")
    with open(dataset_path, "r") as f:
        dataset = json.load(f)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = os.path.join(os.path.dirname(__file__), f"../../data/reports/evaluation_report_{timestamp}.md")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    print(f"Loaded {len(dataset)} cases from golden_dataset.json. Running evaluation...")

    run_id = uuid.uuid4().hex[:8]
    for index, case in enumerate(dataset, 1):
        print(f"\n--- Case {index}/{len(dataset)}: {case['question'][:60]}...")
        state = {
            "question": case["question"],
            "context": case["ground_truth_context"],
            "answer": case["expected_answer"],
            "scores": [],
        }
        config = {"configurable": {"thread_id": f"golden_{index}_{run_id}"}}
        result = eval_app.invoke(state, config=config)
        write_to_markdown_report(case["question"], case["expected_answer"], result["scores"], report_path)
        print(f"  Case {index} archived.")

    print(f"\n✅ All {len(dataset)} cases evaluated. Report saved to {report_path}")
