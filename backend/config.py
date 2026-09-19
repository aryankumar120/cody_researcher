import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    max_pages_per_run: int = int(os.getenv("MAX_PAGES_PER_RUN", 15))
    max_iterations: int = int(os.getenv("MAX_ITERATIONS", 8))
    max_llm_calls: int = int(os.getenv("MAX_LLM_CALLS", 20))
    max_run_seconds: int = int(os.getenv("MAX_RUN_SECONDS", 600))
    fetch_timeout_seconds: int = int(os.getenv("FETCH_TIMEOUT_SECONDS", 20))
    max_retries: int = int(os.getenv("MAX_RETRIES", 2))
    max_concurrency: int = int(os.getenv("MAX_CONCURRENCY", 5))

    sqlite_path: str = os.getenv("SQLITE_PATH", "data/cody_researcher.db")

    pages_per_batch: int = 4  # how many pages we fetch before re-asking the LLM what to do next


settings = Settings()
