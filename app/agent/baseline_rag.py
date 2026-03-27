import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore
from langchain_huggingface import HuggingFaceEmbeddings

def setup_qdrant_database():
    # 1. Dynamically build the absolute path to the PDF
    # This gets the directory where ingestion.py lives (app/agent)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # This goes up two levels to the root, then into the data folder
    pdf_path = os.path.join(current_dir, "../../public/test-content/thinkpython.pdf")
    
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()

    # 2. Break the text into manageable chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.split_documents(documents)

    # 3. Initialize the free-tier embedding model
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")

    # 4. Save the chunks into a local, in-memory Qdrant vector database
    qdrant_db = QdrantVectorStore.from_documents(
        chunks,
        embeddings,
        location=":memory:",
        collection_name="portfolio_docs"
    )
    
    print(f"Successfully processed and stored {len(chunks)} chunks in Qdrant!")
    return qdrant_db

if __name__ == "__main__":
    # Run this to test if ingestion works
    db = setup_qdrant_database()