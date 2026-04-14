import os
import operator
from baseline_rag import AgentState
from typing import Annotated, List
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END

load_dotenv()

class EvaluationScore(BaseModel):
    name: str = Field(description="The exact name of the judge providing this score.")
    score: int = Field(description="A score from 1 to 5.", ge=1, le=5) 
    rationale: str = Field(description="Detailed explanation. CRITICAL: Do not use apostrophes (') or single quotes anywhere in this text to prevent JSON syntax errors.")

# --- STATE AND REDUCERS ---
class EvalState(AgentState):
    scores: Annotated[List[dict], operator.add] 

# Initialize the Groq LLM and force it to use our structured output format
llm = ChatGroq(
    api_key=os.environ.get("GROQ_API_KEY"), 
    model="llama-3.3-70b-versatile",
    max_retries=15
)
structured_llm = llm.with_structured_output(EvaluationScore)

# --- PROMPT TEMPLATES ---
relevance_template = PromptTemplate.from_template(
    "You are Judge Relevance. Evaluate how well the answer addresses the question based ONLY on the context.\n"
    "Question: {question}\n"
    "Context: {context}\n"
    "Answer: {answer}\n"
    "Output a score from 1-5 where 5 is perfectly relevant."
)

hallucination_template = PromptTemplate.from_template(
    "You are a Judge of agent Hallucinations. \n"
    "You read and understand everything in the context and can always tell if the answer contains details that \n"
    "are not present in the context. \n\n"
    "Question: {question}\n"
    "Context: {context}\n"
    "Answer: {answer}\n"
    "Score 5 if perfectly grounded (no hallucinations), 1 if completely hallucinated."
)

psi_division_template = PromptTemplate.from_template(
    "You are Judge Psi Division. Evaluate if the answer correctly addresses the underlying goal or if it missed the point.\n"
    "Identify if the agent should be breaking down a complex question into easier-to-answer chunks and/or discover where and why the agent\n"
    "misunderstood the goal of the question. \n"
    "Question Intent: {question}\n"
    "Answer: {answer}\n"
    "Score 5 if perfectly aligned, 1 if misinterpreted."
)

tek_division_template = PromptTemplate.from_template(
    "You are Judge Tek Division. Analyze the technical accuracy of the answer.\n"
    "Specifically, check if any Python code, algorithms, or technical definitions provided in the Answer are factually correct according to modern software engineering standards.\n"
    "Question: {question}\n"
    "Answer: {answer}\n"
    "Score 5 if technically flawless, 1 if code or logic is flawed."
)

# --- EVALUATION NODES ---
def judge_relevance(state: EvalState):
    prompt_val = relevance_template.invoke({
        "question": state['question'], 
        "context": state['context'], 
        "answer": state['answer']
    })
    result = structured_llm.invoke(prompt_val)
    output_dict = result.model_dump()
    return {"scores": [{"judge_name": "Judge Relevance", "score": output_dict["score"], "rationale": output_dict["rationale"]}]}

def judge_hallucination(state: EvalState):
    prompt_val = hallucination_template.invoke({
        "question": state['question'], 
        "context": state['context'], 
        "answer": state['answer']
    })
    result = structured_llm.invoke(prompt_val)
    output_dict = result.model_dump()
    return {"scores": [{"judge_name": "Judge Hallucination", "score": output_dict["score"], "rationale": output_dict["rationale"]}]}

def judge_psi_division(state: EvalState):
    prompt_val = psi_division_template.invoke({
        "question": state['question'], 
        "answer": state['answer']
    })
    result = structured_llm.invoke(prompt_val)
    output_dict = result.model_dump()
    return {"scores": [{"judge_name": "Judge Psi Division", "score": output_dict["score"], "rationale": output_dict["rationale"]}]}

def judge_tek_division(state: EvalState):
    prompt_val = tek_division_template.invoke({
        "question": state['question'], 
        "answer": state['answer']
    })
    result = structured_llm.invoke(prompt_val)
    output_dict = result.model_dump()
    return {"scores": [{"judge_name": "Judge Tek Division", "score": output_dict["score"], "rationale": output_dict["rationale"]}]}
# --- CONCEPT: FAN-IN AGGREGATOR ---
def aggregator_node(state: EvalState):
    print("\n--- FINAL EVALUATION VERDICT ---")
    for score in state['scores']:
        print(f"[{score['judge_name']}] Score: {score['score']}/5")
        print(f"Rationale: {score['rationale']}\n")
    return state

# --- HUMAN IN THE LOOP ROUTING ---
def human_review_node(state: EvalState):
    print("\n[PAUSED] A Judge scored a 3 or lower. Waiting for Human Override...")
    # The graph freezes here until the human intervenes
    return state

def route_after_aggregation(state: EvalState):
    # Check if any judge gave a failing score
    for score in state['scores']:
        if int(score['score']) <= 3:
            return "human_review"
    return "end"

# --- BUILD THE GRAPH ---
workflow = StateGraph(EvalState)

workflow.add_node("relevance", judge_relevance)
workflow.add_node("hallucination", judge_hallucination)
workflow.add_node("psi_division", judge_psi_division)
workflow.add_node("tek_division", judge_tek_division)
workflow.add_node("aggregator", aggregator_node)

# Fan-out: From the START, trigger all three judges at the exact same time
workflow.add_edge(START, "relevance")
workflow.add_edge(START, "hallucination")
workflow.add_edge(START, "tone")
workflow.add_edge(START, "psi_division")
workflow.add_edge(START, "tek_division")

workflow.add_node("human_review", human_review_node)

# Fan-in: Wait for all judges to finish, then send them to the aggregator
workflow.add_edge(["relevance", "hallucination", "psi_division", "tek_division"], "aggregator")

workflow.add_conditional_edges(
    "aggregator", 
    route_after_aggregation, 
    {
        "human_review": "human_review", 
        "end": END
    }
)

workflow.add_edge("human_review", END)

memory = MemorySaver()

eval_app = workflow.compile(
    checkpointer=memory, 
    interrupt_before=["human_review"]
)

if __name__ == "__main__":
    # Test the graph with a deliberately BAD answer to see if the judges catch it
    test_state = {
        "question": "What is a python tuple?",
        "context": "A tuple is a sequence of values much like a list. The values stored in a tuple can be any type, and they are indexed by integers. The important difference is that tuples are immutable.",
        "answer": "A tuple is a list of values that can be changed at any time. It is exactly the same as a Python dictionary.",
    }
    print("Running parallel evaluation graph...")
    eval_app.invoke(test_state)