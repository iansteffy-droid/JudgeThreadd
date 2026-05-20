import os


def get_llm(temperature: float = 0.0, for_structured_output: bool = False, provider: str = None, model: str = None):
    provider = (provider or os.environ.get("LLM_PROVIDER", "groq")).lower()

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        model = model or os.environ.get("LOCAL_MODEL", "qwen2.5:3b")
        return ChatOllama(
            model=model,
            temperature=temperature,
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    else:
        from langchain_groq import ChatGroq
        model = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        kwargs = {"model_kwargs": {"seed": 42}} if for_structured_output else {}
        return ChatGroq(
            api_key=os.environ.get("GROQ_API_KEY"),
            model=model,
            temperature=temperature,
            max_retries=15,
            **kwargs,
        )
