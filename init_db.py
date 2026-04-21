import os
import psycopg
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
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

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

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

# We use autocommit=True to avoid the transaction block error!
with psycopg.connect(DB_URI, autocommit=True) as conn:
    memory = PostgresSaver(conn)
    memory.setup()
    
print("✅ Supabase tables created successfully!")