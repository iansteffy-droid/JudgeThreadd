import os
import operator
from typing import Annotated, List
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END

load_dotenv()

# --- STRUCTURED OUTPUT ---
# Define exactly what the LLM judge must return.
class EvaluationScore(BaseModel):
    judge_name: str = Field(description="Name of the judge (Judge Relevance,Judge Hallucination, or Judge Tone)")
    score: int = Field(description="A score from 1 to 5")
    rationale: str = Field(description="Detailed explanation for why this score was given")

# --- STATE AND REDUCERS ---
# Memory of our graph. 
class EvalState(TypedDict):
    question: str
    context: str
    answer: str
    # The Annotated type + operator.add is our REDUCER. 
    # It ensures parallel judges append to this list instead of overwriting it!
    scores: Annotated[List[dict], operator.add] 

# Initialize the Groq LLM and force it to use our structured output format
llm = ChatGroq(api_key=os.environ.get("GROQ_API_KEY"), model="llama-3.1-8b-instant")
structured_llm = llm.with_structured_output(EvaluationScore)

# --- Council of Judges: EVALUATOR NODES ---
def judge_relevance(state: EvalState):
    prompt = f"""You are a Relevance Judge. Evaluate how well the answer addresses the question based ONLY on the context.
    Question: {state['question']}
    Context: {state['context']}
    Answer: {state['answer']}
    Output a score from 1-5 where 5 is perfectly relevant."""
    
    result = structured_llm.invoke(prompt)
    # We return a dictionary matching our State. The reducer will append this to the main list.
    return {"scores": [result.model_dump()]}

def judge_hallucination(state: EvalState):
    prompt = f"""You are a Hallucination Judge. Check if the answer contains details NOT present in the context.
    Question: {state['question']}
    Context: {state['context']}
    Answer: {state['answer']}
    Score 5 if perfectly grounded (no hallucinations), 1 if completely hallucinated."""
    
    result = structured_llm.invoke(prompt)
    return {"scores": [result.model_dump()]}

def judge_tone(state: EvalState):
    prompt = f"""You are a Tone Judge. Evaluate if the answer is polite, professional, and helpful.
    Answer: {state['answer']}
    Output a score from 1-5 where 5 is highly professional."""
    
    result = structured_llm.invoke(prompt)
    return {"scores": [result.model_dump()]}

# --- CONCEPT: FAN-IN AGGREGATOR ---
def aggregator_node(state: EvalState):
    print("\n--- FINAL EVALUATION VERDICT ---")
    for score in state['scores']:
        print(f"[{score['judge_name']}] Score: {score['score']}/5")
        print(f"Rationale: {score['rationale']}\n")
    return state

# --- BUILD THE GRAPH ---
workflow = StateGraph(EvalState)

workflow.add_node("relevance", judge_relevance)
workflow.add_node("hallucination", judge_hallucination)
workflow.add_node("tone", judge_tone)
workflow.add_node("aggregator", aggregator_node)

# Fan-out: From the START, trigger all three judges at the exact same time
workflow.add_edge(START, "relevance")
workflow.add_edge(START, "hallucination")
workflow.add_edge(START, "tone")

# Fan-in: Wait for all three to finish, then send them to the aggregator
workflow.add_edge(["relevance", "hallucination", "tone"], "aggregator")
workflow.add_edge("aggregator", END)

eval_app = workflow.compile()

if __name__ == "__main__":
    # Test the graph with a deliberately BAD answer to see if the judges catch it
    test_state = {
        "question": "What is a python tuple?",
        "context": "A tuple is a sequence of values much like a list. The values stored in a tuple can be any type, and they are indexed by integers. The important difference is that tuples are immutable.",
        "answer": "A tuple is a list of values that can be changed at any time. It is exactly the same as a Python dictionary.",
    }
    print("Running parallel evaluation graph...")
    eval_app.invoke(test_state)