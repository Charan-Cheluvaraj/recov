from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional
from pydantic import BaseModel
from config import settings

class BaseLLMProvider(ABC):
    """Abstract LLM Provider interface."""
    
    @abstractmethod
    def generate_structured_response(
        self, prompt: str, schema: Type[BaseModel], system_instruction: str = ""
    ) -> BaseModel:
        """Generate structured response matching a Pydantic schema."""
        pass

class GeminiLLMProvider(BaseLLMProvider):
    """Google Gemini LLM Provider implementation."""
    
    def generate_structured_response(
        self, prompt: str, schema: Type[BaseModel], system_instruction: str = ""
    ) -> BaseModel:
        raise NotImplementedError("GeminiLLMProvider execution is deferred in Prompt 1.")

class AnthropicLLMProvider(BaseLLMProvider):
    """Anthropic Claude LLM Provider implementation."""
    
    def generate_structured_response(
        self, prompt: str, schema: Type[BaseModel], system_instruction: str = ""
    ) -> BaseModel:
        raise NotImplementedError("AnthropicLLMProvider execution is deferred in Prompt 1.")

def get_llm_client(provider: Optional[str] = None) -> BaseLLMProvider:
    """Factory function to retrieve configured LLM provider abstraction."""
    selected_provider = (provider or settings.LLM_PROVIDER).lower()
    if selected_provider == "anthropic":
        return AnthropicLLMProvider()
    return GeminiLLMProvider()
