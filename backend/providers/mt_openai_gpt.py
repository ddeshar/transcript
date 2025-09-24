from __future__ import annotations

import asyncio
from typing import Optional

from openai import AsyncOpenAI

from .mt_base import MTProvider, MTResult
from ..utils import to_thread


class OpenAIGPTProvider(MTProvider):
    """OpenAI GPT-based translation provider for high-quality Thai translation."""
    
    name = "openai_gpt"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.3
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self._client: Optional[AsyncOpenAI] = None

    async def setup(self) -> None:
        """Initialize the OpenAI client"""
        try:
            key = self.api_key
            if key is None:
                from ..utils import get_env
                key = get_env("OPENAI_API_KEY")
            
            if not key:
                raise RuntimeError(
                    "OPENAI_API_KEY is not configured for OpenAI GPT translation."
                )
            
            self._client = AsyncOpenAI(api_key=key)
            
            # Test the connection with a minimal request
            await self._test_connection()
            
        except Exception as e:
            raise RuntimeError(f"Failed to initialize OpenAI GPT provider: {e}")

    async def _test_connection(self) -> None:
        """Test the OpenAI API connection"""
        if not self._client:
            return
            
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5
            )
            # If we get here, the API is working
            
        except Exception as e:
            error_str = str(e)
            if "insufficient_quota" in error_str or "quota" in error_str.lower():
                raise RuntimeError(
                    "OpenAI API quota exceeded. Please add billing information at https://platform.openai.com/account/billing"
                )
            elif "invalid" in error_str.lower() or "authentication" in error_str.lower():
                raise RuntimeError(
                    "Invalid OpenAI API key. Please check your OPENAI_API_KEY."
                )
            else:
                raise RuntimeError(f"OpenAI API test failed: {e}")

    async def translate(self, text: str, *, is_final: bool) -> MTResult:
        """Translate English text to Thai using OpenAI GPT"""
        if not text.strip():
            return MTResult(text="", provider=self.name, is_final=is_final)
        
        if self._client is None:
            raise RuntimeError("OpenAIGPTProvider.setup() must be awaited before use.")
        
        try:
            # Create a focused translation prompt
            system_prompt = """You are a professional English-to-Thai translator. 
Translate the given English text to natural, fluent Thai. 
- Maintain the original meaning and tone
- Use appropriate Thai formality level
- For conversational speech, use natural Thai expressions
- Only return the Thai translation, nothing else"""

            user_prompt = f"Translate to Thai: {text}"
            
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=100,  # Reduced for faster response
                temperature=self.temperature,
                stream=False  # Ensure no streaming for faster completion
            )
            
            thai_text = response.choices[0].message.content.strip()
            
            # Remove any extra formatting or quotes that might be added
            if thai_text.startswith('"') and thai_text.endswith('"'):
                thai_text = thai_text[1:-1]
            
            return MTResult(
                text=thai_text,
                provider=self.name,
                is_final=is_final,
                raw={
                    "model": response.model,
                    "usage": response.usage.model_dump() if response.usage else None,
                    "finish_reason": response.choices[0].finish_reason
                }
            )
            
        except Exception as e:
            error_str = str(e)
            
            # Handle common OpenAI errors gracefully
            if "rate_limit" in error_str.lower():
                print(f"OpenAI rate limit hit: {e}")
                return MTResult(text=text, provider=self.name, is_final=is_final, raw={"error": "rate_limit"})
            elif "quota" in error_str.lower():
                print(f"OpenAI quota exceeded: {e}")
                return MTResult(text=text, provider=self.name, is_final=is_final, raw={"error": "quota_exceeded"})
            else:
                print(f"OpenAI GPT translation error: {e}")
                return MTResult(text=text, provider=self.name, is_final=is_final, raw={"error": str(e)})


__all__ = ["OpenAIGPTProvider"]