import os
import json
import random
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

# Load API keys from the.env file
load_dotenv()

def create_golden_dataset():
    print("1. Loading the Think Python manual...")
    # Load the PDF from your data folder
    pdf_path = "public/test-content/thinkpython.pdf"
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()

    print("2. Sampling text to send to Gemini...")
    # Pick 10 random pages from the book to base our questions on
    sampled_docs = random.sample(documents, 10)
    combined_text = "\n\n".join([doc.page_content for doc in sampled_docs])

    print("3. Initializing Gemini 2.5 Flash...")
    # Set up the LLM. We use temperature=0.1 to make it highly deterministic and focused.
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        api_key=os.environ.get("GOOGLE_API_KEY"),
        temperature=0.1 
    )

    print("4. Prompting Gemini to generate 20 test cases...")
    # We explicitly ask for a JSON array of question-answer-context triplets
    prompt = PromptTemplate.from_template("""
    You are an expert AI evaluator. Read the following context from a Python programming manual.
    Generate exactly 20 complex test cases based on this context.
    
    Output your response STRICTLY as a valid JSON array of objects. Do not include markdown formatting like ```json.
    Each object must have these exact three keys:
    - "question": A realistic user question based on the text.
    - "ground_truth_context": The exact sentence or paragraph from the text that contains the answer.
    - "expected_answer": The ideal, correct answer to the question.

    Context:
    {context}
    """)

    # Combine the prompt and the LLM into a LangChain execution chain
    chain = prompt | llm
    response = chain.invoke({"context": combined_text})

    print("5. Saving dataset to your data folder...")
    try:
        # Clean up the output in case Gemini wraps it in markdown code blocks
        clean_json = response.content.replace("```json", "").replace("```", "").strip()
        dataset = json.loads(clean_json)

        # Save the resulting JSON array into your data folder
        output_path = "data/golden_dataset.json"
        with open(output_path, "w") as f:
            json.dump(dataset, f, indent=4)

        print(f"Success! Saved {len(dataset)} questions to {output_path}")
        
    except json.JSONDecodeError:
        print("Error: Failed to parse JSON. Gemini might have formatted it wrong.")
        print(f"Raw output from Gemini:\n{response.content}")

if __name__ == "__main__":
    create_golden_dataset()