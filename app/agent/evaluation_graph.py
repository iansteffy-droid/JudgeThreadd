import os
import operator
from typing import Annotated, List
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from langchain_core.prompts import PromptTemplate

# delete me
load_dotenv()

class EvaluationScore(BaseModel):
    name: str = Field(description="The exact name of the judge providing this score.")
    score: str = Field(description="A score from 1 to 5. Output as a string (e.g., '5').") 
    rationale: str = Field(description="Detailed explanation. CRITICAL: Do not use apostrophes (') or single quotes anywhere in this text to prevent JSON syntax errors.")

# --- STATE AND REDUCERS ---
# Memory of our graph. 
class EvalState(TypedDict):
    question: str
    context: str
    answer: str
    scores: Annotated[List[dict], operator.add] 

# Initialize the Groq LLM and force it to use our structured output format
llm = ChatGroq(
    api_key=os.environ.get("GROQ_API_KEY"), 
    model="llama-3.3-70b-versatile",
    max_retries=15
)
structured_llm = llm.with_structured_output(EvaluationScore)

# TODO: class AgentState(TypedDict) has a similar structure. Could we use this?
STANDARD_INPUTS = """
Question: {question}
Context: {context}
Answer: {answer}
"""

# --- THE COUNCIL JUDGES ---
# TODO: Judge Relevance uses "score": int(output_dict["score"]) with int to make sure the score is an int
# JUDGE_RELEVANCE_ROLE = """You are a Relevance Judge. Evaluate how well the answer addresses the question based ONLY on the context."""
# RELEVANCE_RUBRIC = """Assign a score from 1 to 5 where:
# 5 = Output perfectly addresses the input with all content being relevant.
# 3 = Output partially addresses the input with some irrelevant content.
# 1 = Output does not address the input at all.

# Provide actionable remediation steps if the score is less than 5."""
# relevance_template = f"""
# {JUDGE_RELEVANCE_ROLE}

# {RELEVANCE_RUBRIC}

# {STANDARD_INPUTS}
# """
# relevance_prompt = PromptTemplate.from_template(relevance_template)

# TODO: Question: Would it be more efficient to have every judge have another LLM which is grading the judges and making sure that they are not messing up?

def judge_relevance(state: EvalState):
    prompt = f"""You are Judge Relevance. Evaluate how well the answer addresses the question based ONLY on the context.
    Question: {state['question']}
    Context: {state['context']}
    Answer: {state['answer']}
    Output a score from 1-5 where 5 is perfectly relevant."""
    result = structured_llm.invoke(prompt)
    
    # We manually force the correct judge_name into the state dictionary here
    # to guarantee consistency for the aggregator, regardless of what the LLM named itself.
    output_dict = result.model_dump()
    return {"scores": [{"judge_name": "Judge Relevance", "score": int(output_dict["score"]), "rationale": output_dict["rationale"]}]}

def judge_hallucination(state: EvalState):
    prompt = f"""You are a Judge of agent Hallucinations. 
    You read and understand everything in the context and can always tell if the answer contains details that 
    are not present in the context. 

    Question: {state['question']}
    Context: {state['context']}
    Answer: {state['answer']}
    Score 5 if perfectly grounded (no hallucinations), 1 if completely hallucinated."""
    result = structured_llm.invoke(prompt)
    output_dict = result.model_dump()
    return {"scores": [{"judge_name": "Judge Hallucination", "score": int(output_dict["score"]), "rationale": output_dict["rationale"]}]}

# TODO: Judge Tone is Deprecated. Analyzing tone does not help an agentic workflow be better.
def judge_tone(state: EvalState):
    prompt = f"""You are Judge Tone. Evaluate if the answer is polite, professional, and helpful.
    Answer: {state['answer']}
    Output a score from 1-5 where 5 is highly professional."""
    result = structured_llm.invoke(prompt)
    output_dict = result.model_dump()
    return {"scores": [{"judge_name": "Judge Tone", "score": int(output_dict["score"]), "rationale": output_dict["rationale"]}]}

# Judge Goal
def judge_psi_division(state: EvalState):
    prompt = f"""You are Judge Psi Division. Evaluate if the answer correctly addresses the underlying goal or if it missed the point.
    Identify if the agent should be breaking down a complex question into easier-to-answer chunks and/or discover where and why the agent
    misunderstood the goal of the question. 
    Question Intent: {state['question']}
    Answer: {state['answer']}
    Score 5 if perfectly aligned, 1 if misinterpreted."""
    result = structured_llm.invoke(prompt)
    output_dict = result.model_dump()
    return {"scores": [{"judge_name": "Judge Psi Division", "score": int(output_dict["score"]), "rationale": output_dict["rationale"]}]}

def judge_tek_division(state: EvalState):
    ## TODO: Structural logic and technical accuracy of 'what'? This prompr is vage.
    prompt = f"""You are Judge Tek Division. Analyze the structural logic and technical accuracy.
    Question: {state['question']}
    Answer: {state['answer']}
    Score 5 if logic is flawless, 1 if flawed."""
    result = structured_llm.invoke(prompt)
    output_dict = result.model_dump()
    return {"scores": [{"judge_name": "Judge Tek Division", "score": int(output_dict["score"]), "rationale": output_dict["rationale"]}]}

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
workflow.add_node("psi_division", judge_psi_division)
workflow.add_node("tek_division", judge_tek_division)
workflow.add_node("aggregator", aggregator_node)

# Fan-out: From the START, trigger all three judges at the exact same time
workflow.add_edge(START, "relevance")
workflow.add_edge(START, "hallucination")
workflow.add_edge(START, "tone")
workflow.add_edge(START, "psi_division")
workflow.add_edge(START, "tek_division")

# Fan-in: Wait for all three to finish, then send them to the aggregator
workflow.add_edge(["relevance", "hallucination", "tone", "psi_division", "tek_division"], "aggregator")
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