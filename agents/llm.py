import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from core.config import settings


PROVIDER_API_KEY_ENV_VARS = {
    "openrouter": ("OPENROUTER_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "claude": ("ANTHROPIC_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


def _env_value(name: str) -> str:
    return (getattr(settings, name, None) or os.environ.get(name, "")).strip()


def _resolve_api_key(provider: str, api_key: str | None) -> str:
    api_key = (api_key or "").strip()
    if api_key:
        return api_key

    env_names = PROVIDER_API_KEY_ENV_VARS.get(provider.lower(), ("OPENAI_API_KEY",))
    for env_name in env_names:
        value = _env_value(env_name)
        if value:
            return value

    expected = " or ".join(env_names)
    raise ValueError(
        f"LLM API key is missing. Set {expected} in your environment/.env file "
        "or provide a key in the Configuration panel."
    )


def get_llm(provider: str, model: str, api_key: str | None) -> BaseChatModel:
    """
    Returns the appropriate LLM based on provider.
    Supports 'openrouter', 'groq', 'openai', etc.

    The key can come from the UI or from provider-specific environment variables.
    """
    provider = (provider or "").lower()
    api_key = _resolve_api_key(provider, api_key)

    llm: BaseChatModel = None

    if provider == "openrouter":
        if not api_key.startswith("sk-or-v1-"):
            raise ValueError("Invalid OpenRouter API Key. It must start with 'sk-or-v1-'. Did you paste a different provider's key?")
        llm = ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            default_headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Deep Research Agent",
                "Authorization": f"Bearer {api_key}",
            },
        )
    elif provider == "groq":
        if not api_key.startswith("gsk_"):
            raise ValueError("Invalid Groq API Key. It must start with 'gsk_'. Did you paste a different provider's key?")

        from langchain_groq import ChatGroq

        is_small = "8b" in model.lower() or "instant" in model.lower()
        max_t = 2048 if is_small else 4096

        llm = ChatGroq(
            api_key=api_key,
            model=model,
            max_tokens=max_t,
        )
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model=model,
        )
    elif provider in {"claude", "anthropic"}:
        if not api_key.startswith("sk-ant-"):
            raise ValueError("Invalid Anthropic API Key. It must start with 'sk-ant-'. Did you paste a different provider's key?")
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            api_key=api_key,
            model_name=model,
        )
    elif provider == "openai":
        llm = ChatOpenAI(
            api_key=api_key,
            model=model,
        )
    else:
        llm = ChatOpenAI(
            api_key=api_key,
            model=model,
        )

    original_ainvoke = llm.ainvoke

    async def ainvoke_with_retry(input, *args, **kwargs):
        import asyncio
        import random

        max_retries = 6
        base_delay = 5.0

        for attempt in range(max_retries):
            try:
                return await original_ainvoke(input, *args, **kwargs)
            except Exception as e:
                err_str = str(e)
                is_rate_limit = "429" in err_str or "rate limit" in err_str.lower() or "tpm" in err_str.lower()

                if is_rate_limit and attempt < max_retries - 1:
                    sleep_time = (base_delay * (2 ** attempt)) + (random.random() * 2) + 2.0
                    print(f"[LLM Retry] Rate limit hit. Waiting {sleep_time:.2f}s before retry (attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(sleep_time)
                else:
                    raise e

    object.__setattr__(llm, "ainvoke", ainvoke_with_retry)
    return llm
