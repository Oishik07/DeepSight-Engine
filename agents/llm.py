from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel

def get_llm(provider: str, model: str, api_key: str) -> BaseChatModel:
    """
    Returns the appropriate LLM based on provider.
    Supports 'openrouter', 'groq', 'openai', etc.

    NOTE: With openai SDK v2+, api_key alone is sometimes NOT forwarded as the
    Authorization header when a custom base_url is set. We inject it explicitly
    via default_headers to guarantee it is always present.
    """
    if not api_key or not api_key.strip():
        raise ValueError(
            "LLM API key is missing or empty. "
            "Please paste your API key in the Configuration panel."
        )

    api_key = api_key.strip()
    provider = provider.lower()

    # Debug print — visible in the server console
    print(f"[LLM] provider={provider!r}  model={model!r}  key_prefix={api_key[:8]}...")

    if provider == "openrouter":
        if not api_key.startswith("sk-or-v1-"):
            raise ValueError("Invalid OpenRouter API Key. It must start with 'sk-or-v1-'. Did you paste a different provider's key?")
        return ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            default_headers={
                # Required by OpenRouter
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Deep Research Agent",
                # Explicitly set Bearer token — guards against openai SDK v2 quirks
                "Authorization": f"Bearer {api_key}",
            },
        )
    elif provider == "groq":
        if not api_key.startswith("gsk_"):
            raise ValueError("Invalid Groq API Key. It must start with 'gsk_'. Did you paste a different provider's key?")
        
        from langchain_groq import ChatGroq
        return ChatGroq(
            api_key=api_key,
            model=model,
            # Groq on-demand free/low tiers can have a 6000 TPM limit. Keeping
            # reserved output lower prevents prompt+completion requests from
            # being rejected during the final report/editor stages.
            max_tokens=1200,
        )
    elif provider == "openai":
        return ChatOpenAI(
            api_key=api_key,
            model=model,
        )
    else:
        return ChatOpenAI(
            api_key=api_key,
            model=model,
        )
