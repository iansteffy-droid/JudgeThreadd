import os
from typing import TypedDict
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# LangChain & LangGraph Imports
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END

# Document & Vector Store Imports
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore
from langchain_huggingface import HuggingFaceEmbeddings

# Load environment variables (GROQ_API_KEY, etc.)
load_dotenv()

# ==========================================
# 1. DATABASE SETUP (The Foundation)
# ==========================================
def setup_qdrant_database():
    print("🏗️ Building Sector Database...")
    current_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_path = os.path.join(current_dir, "../../public/test-content/thinkpython.pdf")
    
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.split_documents(documents)
    
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")

    qdrant_db = QdrantVectorStore.from_documents(
        chunks,
        embeddings,
        location=":memory:",
        collection_name="portfolio_docs"
    )
    print(f"✅ Database Online: Processed {len(chunks)} chunks from 'Think Python'.")
    return qdrant_db

# Initialize the database globally so it's ready for incoming queries
db = setup_qdrant_database()
# Set up the retriever to fetch the top 3 most relevant chunks
retriever = db.as_retriever(search_kwargs={"k": 3}) 


# ==========================================
# 2. STATE & LLM CONFIGURATION
# ==========================================
class AgentState(TypedDict):
    question: str
    context: str
    answer: str

class IntakeVerdict(BaseModel):
    is_legal: str = Field(description="Output exactly 'yes' if the question is appropriate, on-topic, and clear. Output 'no' otherwise.")
    decree: str = Field(description="If 'yes', output 'Proceed'. If 'no', explain why the prompt is illegal, off-topic, or too vague.")

# Initialize the Groq LLMs
llm = ChatGroq(
    api_key=os.environ.get("GROQ_API_KEY"), 
    model="llama-3.1-8b-instant",
    max_retries=15
)
intake_llm = llm.with_structured_output(IntakeVerdict)


# ==========================================
# 3. GRAPH NODES
# ==========================================
def street_judge(state: AgentState):
    print("\n🚓 [Street Judge] Inspecting citizen's prompt...")
    prompt = f"""You are a master judging prompts and senior AI engineer who is a master at reviewing prompts and knowing what a good and bad user prompt looks like. 
    You know the small naunces in a prompt that allow it to communicate with an LLM in the most effective way.
    
    Your job is to make sure that the user prompt meets the highest standards of how a well-crafted prompt should look like.
    The law states: This system only answers questions related to Python programming, coding concepts, or the Think Python manual.
    Citizen's prompt: "{state['question']}"
    
    Does this prompt violate good-prompt-protocol by being off-topic, vague, or too confusing for an LLM? 
    Does this prompt make the LLM need to think harder than it normally should because the prompt is inproper? 
    In the scope of 'what is a good user prompt', how easy is it for a human or LLLM to understand and respond to? 
    Evaluate and issue your verdict. If the verdict is below a score of 5, suggest a better way to ask or format the prompt to the user."""
    
    verdict = intake_llm.invoke(prompt)
    
    if verdict.is_legal.lower() != "yes":
        print(f"🚨 INFRACTION DETECTED: {verdict.decree}")
        return {"answer": f"Street Judge Decree: {verdict.decree}. Case dismissed."}
    else:
        print("✅ Legal and clear prompt. Proceed to records.")
        return {"answer": ""}

def retrieve_docs(state: AgentState):
    print("📚 [Tek Division] Retrieving 'Think Python' documents from Qdrant...")
    docs = retriever.invoke(state["question"])
    # Combine the text from the retrieved chunks
    context_str = "\n\n".join([doc.page_content for doc in docs])
    return {"context": context_str}

def generate_answer(state: AgentState):
    print("🤖 [Academy Instructor] Reading context and drafting tutorial...")
    
    prompt_template = """
    You are an expert Python programming instructor at the Python Institute.
    Your goal is to answer the citizen's question accurately, politely, and professionally.
    
    CRITICAL RULES:
    1. You must base your answer ONLY on the provided Context. 
    2. If the Context does not contain the answer, do not make one up. State clearly: "The provided manual does not contain this information."
    3. Include brief code examples if the context supports it.
    
    Context:
    {context}
    
    Citizen's Question:
    {question}
    
    Instructor's Answer:
    """
    
    prompt = PromptTemplate.from_template(prompt_template)
    chain = prompt | llm | StrOutputParser()
    
    final_answer = chain.invoke({
        "context": state["context"],
        "question": state["question"]
    })
    
    return {"answer": final_answer}


# ==========================================
# 4. CONDITIONAL ROUTING & GRAPH WIRING
# ==========================================
def routing_logic(state: AgentState):
    if state.get("answer"): 
        return "end_case"
    return "retrieve_docs"

workflow = StateGraph(AgentState)

workflow.add_node("street_judge", street_judge)
workflow.add_node("retrieve_docs", retrieve_docs)
workflow.add_node("generate_answer", generate_answer)

workflow.add_edge(START, "street_judge")

# The Street Judge decides where we go next
workflow.add_conditional_edges(
    "street_judge",
    routing_logic,
    {
        "end_case": END,
        "retrieve_docs": "retrieve_docs"
    }
)

# If approved, retrieve docs, then generate the answer, then end
workflow.add_edge("retrieve_docs", "generate_answer")
workflow.add_edge("generate_answer", END)

# Compile the final application
main_app = workflow.compile()

# TODO: Replace for production. 
# ==========================================
# 5. EXECUTION & TESTING
# ==========================================
if __name__ == "__main__":
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