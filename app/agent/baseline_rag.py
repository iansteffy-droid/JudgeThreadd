import os
from typing import TypedDict
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore
from langchain_community.embeddings import FastEmbedEmbeddings
from app.agent.llm_factory import get_llm

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

embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")

_retriever = None

def _get_retriever():
    global _retriever
    if _retriever is None:
        _qdrant_db = QdrantVectorStore.from_existing_collection(
            embedding=embeddings,
            collection_name="portfolio_docs",
            url=os.environ.get("QDRANT_URL"),
            api_key=os.environ.get("QDRANT_API_KEY"),
        )
        _retriever = _qdrant_db.as_retriever(search_kwargs={"k": 4})
    return _retriever

def setup_qdrant_database():
    print("🏗️ Building Sector Database and uploading to Qdrant Cloud...")
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
# 3. NODE BUILDER HELPERS
# ==========================================
def _make_street_judge(intake_llm):
    def street_judge(state: AgentState):
        print("\n🚓 [Street Judge] Inspecting citizen's prompt...")
        prompt_template = PromptTemplate.from_template("""You are a strict prompt quality judge and senior AI engineer.
    The law states: This system only answers questions related to Python programming, coding concepts, or the Think Python manual.

    <citizen_prompt>
    {question}
    </citizen_prompt>

    Evaluate the prompt above. A prompt is LEGAL ('yes') if it meets ALL of these criteria:
    1. It is on-topic — related to Python programming, coding concepts, or the Think Python manual.
    2. It is clear and specific enough for an LLM to understand and answer.
    3. It is not vague, nonsensical, or confusing.

    A prompt is ILLEGAL ('no') if it is off-topic, too vague, or too confusing.

    Issue your structured verdict now.""")

        prompt = prompt_template.invoke({"question": state["question"]})
        verdict = intake_llm.invoke(prompt)

        if verdict.is_legal.lower() != "yes":
            print(f"🚨 INFRACTION DETECTED: {verdict.decree}")
            return {"answer": f"Street Judge Decree: {verdict.decree}. Case dismissed."}
        else:
            print("✅ Legal and clear prompt. Proceed to records.")
            return {"answer": ""}
    return street_judge


def _make_generate_answer(llm):
    def generate_answer(state: AgentState):
        print("🤖 [Academy Instructor] Reading context and drafting tutorial...")

        prompt_template = """
    You are an expert Python programming instructor at the Python Institute.
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

        prompt = PromptTemplate.from_template(prompt_template)
        chain = prompt | llm | StrOutputParser()

        final_answer = chain.invoke({
            "context": state["context"],
            "question": state["question"]
        })

        return {"answer": final_answer}
    return generate_answer


# ==========================================
# 4. SHARED NODE (no LLM dependency)
# ==========================================
def retrieve_docs(state: AgentState):
    print("📚 [Tek Division] Retrieving 'Think Python' documents from Qdrant...")
    docs = _get_retriever().invoke(state["question"])
    context_str = "\n\n".join([doc.page_content for doc in docs])
    return {"context": context_str}


def routing_logic(state: AgentState):
    if state.get("answer"):
        return "end_case"
    return "retrieve_docs"


# ==========================================
# 5. GRAPH FACTORY
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
