import os

from dotenv import load_dotenv

load_dotenv()


class SmartModelRouter:
    def __init__(self) -> None:
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.sentiment_model = os.getenv("OLLAMA_SENTIMENT_MODEL", "qwen3:4b")
        self.advisory_model = os.getenv("OLLAMA_ADVISORY_MODEL", "hermes3:8b")
        self.embedding_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    def route_for_task(self, task: str) -> dict:
        routes = {
            "sentiment": {
                "provider": "ollama",
                "model": self.sentiment_model,
                "url": self.ollama_url,
                "timeout": 20,
            },
            "embedding": {
                "provider": "ollama",
                "model": self.embedding_model,
                "url": self.ollama_url,
                "timeout": 20,
            },
            "advisory": {
                "provider": "ollama",
                "model": self.advisory_model,
                "url": self.ollama_url,
                "timeout": 60,
            },
        }
        if task == "validation":
            if self._configured("ANTHROPIC_API_KEY"):
                return {
                    "provider": "anthropic",
                    "model": os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
                    "url": None,
                    "timeout": 60,
                }
            if self._configured("OPENAI_API_KEY"):
                return {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "url": None,
                    "timeout": 60,
                }
            return routes["advisory"].copy()
        if task == "advisory":
            if self._configured("OPENAI_API_KEY"):
                return {
                    "provider": "openai",
                    "model": os.getenv("OPENAI_ADVISORY_MODEL", "gpt-4o-mini"),
                    "url": None,
                    "timeout": 60,
                }
            if self._configured("ANTHROPIC_API_KEY"):
                return {
                    "provider": "anthropic",
                    "model": os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
                    "url": None,
                    "timeout": 60,
                }
        return routes.get(task, routes["advisory"]).copy()

    @staticmethod
    def _configured(name: str) -> bool:
        value = os.getenv(name, "")
        return bool(value and not value.startswith("your_"))
