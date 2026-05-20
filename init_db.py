import os
import psycopg
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_qdrant import QdrantVectorStore
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv()

# ======================================================
# 1. QDRANT CLOUD SETUP (Semantic Memory)
# ======================================================
print("🏗️ Reading PDF and uploading vectors to Qdrant Cloud...")

project_root = os.path.dirname(os.path.abspath(__file__))
pdf_path = os.path.join(project_root, "public", "test-content", "thinkpython.pdf")

loader = PyPDFLoader(pdf_path)
documents = loader.load()
text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
chunks = text_splitter.split_documents(documents)

embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")

QdrantVectorStore.from_documents(
    chunks,
    embeddings,
    url=os.environ.get("QDRANT_URL"),
    api_key=os.environ.get("QDRANT_API_KEY"),
    collection_name="portfolio_docs",
    force_recreate=True 
)

print("✅ Upload complete! The 'portfolio_docs' collection now exists in the cloud.")

# ======================================================
# 2. SUPABASE POSTGRES SETUP (Episodic Memory)
# ======================================================
print("🏗️ Setting up Supabase PostgreSQL tables...")
DB_URI = os.environ.get("SUPABASE_DB_URI")

with psycopg.connect(DB_URI, autocommit=True) as conn:
    memory = PostgresSaver(conn)
    memory.setup()
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS eval_history (
            id SERIAL PRIMARY KEY,
            question TEXT,
            chief_score INTEGER,
            status TEXT,
            logprobs JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
print("✅ Supabase tables created successfully!")