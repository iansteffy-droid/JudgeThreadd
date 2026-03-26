import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough

load_dotenv()

# Initialize Groq Llama 3
llm = ChatGroq(
    api_key=os.environ.get("GROQ_API_KEY"),
    model="llama-3.1-8b-instant"
)

# Set up the Qdrant retriever
retriever = qdrant_db.as_retriever()

# Create the prompt template
template = """Answer the question based ONLY on the following context:
{context}

Question: {question}
"""
prompt = PromptTemplate.from_template(template)

# Build the baseline RAG agent using LCEL
rag_chain = (
    {"context": retriever, "question": RunnablePassthrough()}

| prompt
| llm
)

# Test it
response = rag_chain.invoke("What is the main topic of the documents?")
print(response.content)