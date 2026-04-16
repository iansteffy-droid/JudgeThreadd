import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore

load_dotenv()

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