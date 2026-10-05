from abc import ABC, abstractmethod

class AIProvider(ABC):
    name: str
    @abstractmethod
    def analyze(self, payload: dict) -> dict:
        raise NotImplementedError

class OpenAIProvider(AIProvider):
    name = "openai"
    def analyze(self, payload: dict) -> dict:
        raise RuntimeError("OpenAI adapter is intentionally not enabled until API configuration and approved data-minimization rules are supplied.")

class GeminiProvider(AIProvider):
    name = "gemini"
    def analyze(self, payload: dict) -> dict:
        raise RuntimeError("Gemini adapter requires API configuration and the approved payday-analysis schema.")

class GLMProvider(AIProvider):
    name = "glm"
    def analyze(self, payload: dict) -> dict:
        raise RuntimeError("GLM adapter requires API configuration and the approved debt-analysis schema.")
