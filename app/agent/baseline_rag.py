import os
from typing import TypedDict
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from app.agent.llm_factory import get_llm
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

if os.environ.get("LLM_PROVIDER", "groq").lower() != "ollama" and not os.environ.get("GROQ_API_KEY"):
    raise ValueError("🚨 GROQ_API_KEY is missing. Please check your .env file.")
if not os.environ.get("QDRANT_URL"):
    raise ValueError("🚨 QDRANT_URL is missing. Please check your .env file.")
if not os.environ.get("QDRANT_API_KEY"):
    raise ValueError("🚨 QDRANT_API_KEY is missing. Please check your .env file.")

# ==========================================
# 1. DATABASE SETUP (The Foundation)
# ==========================================

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

qdrant_db = QdrantVectorStore.from_existing_collection(
    embedding=embeddings,
    collection_name="portfolio_docs",
    url=os.environ.get("QDRANT_URL"),
    api_key=os.environ.get("QDRANT_API_KEY"),
)

retriever = qdrant_db.as_retriever(search_kwargs={"k": 4})

def setup_qdrant_database(pdf_path: str = None):
    print("🏗️ Building Sector Database and uploading to Qdrant Cloud...")
    if pdf_path is None:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        pdf_path = os.path.join(project_root, "public", "test-content", "thinkpython.pdf")

    loader = PyPDFLoader(pdf_path)
    documents = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    chunks = text_splitter.split_documents(documents)

    QdrantVectorStore.from_documents(
        chunks,
        embeddings,
        url=os.environ.get("QDRANT_URL"),
        api_key=os.environ.get("QDRANT_API_KEY"),
        collection_name="portfolio_docs",
        force_recreate=True
    )
    print("Upload complete!")

# ==========================================
# 2. STATE & SCHEMA
# ==========================================
class AgentState(TypedDict):
    question: str
    context: str
    answer: str

class IntakeVerdict(BaseModel):
    is_legal: str = Field(description="Output exactly 'yes' if the question is appropriate, on-topic, and clear. Output 'no' otherwise.")
    decree: str = Field(description="If 'yes', output 'Proceed'. If 'no', explain why the prompt is illegal, off-topic, or too vague.")

# ==========================================
# 3. GRAPH NODE FACTORIES
# ==========================================
_STREET_JUDGE_PROMPT = PromptTemplate.from_template(
    """You are a master judging prompts and senior AI engineer who is a master at reviewing prompts and knowing what a good and bad user prompt looks like.
    You know the small nuances in a prompt that allow it to communicate with an LLM in the most effective way.

    Your job is to make sure that the user prompt meets the highest standards of how a well-crafted prompt should look like.
    The law states: This system only answers questions related to Python programming, coding concepts, or the Think Python manual.

    <citizen_prompt>
    {question}
    </citizen_prompt>

    Does this prompt violate good-prompt-protocol by being off-topic, vague, or too confusing for an LLM?
    Does this prompt make the LLM need to think harder than it normally should because the prompt is improper?
    In the scope of 'what is a good user prompt', how easy is it for a human or LLM to understand and respond to?
    Evaluate and issue your verdict. If the verdict is below a score of 5, suggest a better way to ask or format the prompt to the user."""
)

_GENERATE_ANSWER_PROMPT = PromptTemplate.from_template(
    """You are an expert Python programming instructor at the Python Institute.
    Your goal is to answer the citizen's question accurately, politely, and professionally.

    CRITICAL RULES:
    1. You must base your answer ONLY on the provided Context.
    2. If the Context does not contain the answer, do not make one up. State clearly: "The provided manual does not contain this information."
    3. Include brief code examples if the context supports it.

    <context>
    {context}
    </context>

    <citizen_question>
    {question}
    </citizen_question>

    Instructor's Answer:
    """
)

def _make_street_judge(intake_llm):
    def street_judge(state: AgentState):
        print("\n🚓 [Street Judge] Inspecting citizen's prompt...")
        prompt = _STREET_JUDGE_PROMPT.invoke({"question": state["question"]})
        verdict = intake_llm.invoke(prompt)
        if verdict.is_legal.lower() != "yes":
            print(f"🚨 INFRACTION DETECTED: {verdict.decree}")
            return {"answer": f"Street Judge Decree: {verdict.decree}. Case dismissed."}
        else:
            print("✅ Legal and clear prompt. Proceed to records.")
            return {"answer": ""}
    return street_judge

def retrieve_docs(state: AgentState):
    print("📚 [Tek Division] Retrieving 'Think Python' documents from Qdrant...")
    docs = retriever.invoke(state["question"])
    context_str = "\n\n".join([doc.page_content for doc in docs])
    return {"context": context_str}

def _make_generate_answer(llm):
    def generate_answer(state: AgentState):
        print("🤖 [Academy Instructor] Reading context and drafting tutorial...")
        chain = _GENERATE_ANSWER_PROMPT | llm | StrOutputParser()
        final_answer = chain.invoke({
            "context": state["context"],
            "question": state["question"]
        })
        return {"answer": final_answer}
    return generate_answer

# ==========================================
# 4. CONDITIONAL ROUTING
# ==========================================
def routing_logic(state: AgentState):
    if state.get("answer"):
        return "end_case"
    return "retrieve_docs"

# ==========================================
# 5. FACTORY FUNCTION
# ==========================================
def create_rag_app(provider: str = None, model: str = None):
    _llm = get_llm(temperature=0.0, provider=provider, model=model)
    _intake_llm = _llm.with_structured_output(IntakeVerdict)

    workflow = StateGraph(AgentState)
    workflow.add_node("street_judge", _make_street_judge(_intake_llm))
    workflow.add_node("retrieve_docs", retrieve_docs)
    workflow.add_node("generate_answer", _make_generate_answer(_llm))

    workflow.add_edge(START, "street_judge")
    workflow.add_conditional_edges(
        "street_judge",
        routing_logic,
        {
            "end_case": END,
            "retrieve_docs": "retrieve_docs"
        }
    )
    workflow.add_edge("retrieve_docs", "generate_answer")
    workflow.add_edge("generate_answer", END)

    return workflow.compile()


main_app = create_rag_app()


# ==========================================
# 6. EXECUTION & TESTING
# ==========================================
if __name__ == "__main__":
    setup_qdrant_database()
    print("\n" + "="*50)
    print("TEST CASE 1: A Good, Legal Prompt")
    print("="*50)
    legal_state = {"question": "What is a python tuple and are they immutable?", "context": "", "answer": ""}
    final_state_1 = main_app.invoke(legal_state)
    print(f"\nFINAL OUTPUT:\n{final_state_1['answer']}\n")

    print("\n" + "="*50)
    print("TEST CASE 2: An Off-Topic Prompt")
    print("="*50)
    illegal_state = {"question": "Write me a recipe for chocolate chip cookies.", "context": "", "answer": ""}
    final_state_2 = main_app.invoke(illegal_state)
    print(f"\nFINAL OUTPUT:\n{final_state_2['answer']}\n")

    print("\n" + "="*50)
    print("TEST CASE 3: A Vague/Poor Prompt")
    print("="*50)
    vague_state = {"question": "python thing broke help", "context": "", "answer": ""}
    final_state_3 = main_app.invoke(vague_state)
    print(f"\nFINAL OUTPUT:\n{final_state_3['answer']}\n")
