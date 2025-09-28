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
        temperature: float = 0.1,
        max_tokens: int = 80,
        frequency_penalty: float = 0.1,
        presence_penalty: float = 0.0
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
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
            # Create a focused translation prompt that reduces redundant politeness markers
            system_prompt = """You are a professional English-to-Thai translator for real-time subtitles.

Rules:
1. Translate naturally and accurately - do NOT add extra politeness markers
2. Only add ครับ/ค่ะ if it's clearly implied in the original English tone
3. For casual conversation, use informal Thai without forcing politeness
4. For formal speech, use appropriate level but don't over-polite
5. Translate short phrases simply - don't elaborate
6. Return ONLY the Thai translation, no explanations

Examples:
"This is a test" → "นี่คือการทดสอบ" (NOT "นี่คือการทดสอบค่ะ/ครับ")
"Thank you" → "ขอบคุณ" (NOT "ขอบคุณครับ/ค่ะ" unless clearly formal)
"Let's go" → "ไปกันเถอะ" (NOT "ไปกันเถอะค่ะ/ครับ")"""

            user_prompt = f"{text}"
            
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=0.9,
                frequency_penalty=self.frequency_penalty,
                presence_penalty=self.presence_penalty,
                stream=False
            )
            
            thai_text = response.choices[0].message.content.strip()
            
            # Remove any extra formatting or quotes that might be added
            if thai_text.startswith('"') and thai_text.endswith('"'):
                thai_text = thai_text[1:-1]
            
            # Clean up common redundant patterns
            # Remove excessive politeness markers that weren't in original English
            import re
            
            # If original text is very short and casual, remove automatic politeness
            if len(text.split()) <= 3 and text.lower() in ['yes', 'yep', 'yeah', 'ok', 'okay', 'bye', 'hi', 'hello']:
                thai_text = re.sub(r'ค่ะ/ครับ$|ครับ/ค่ะ$|ค่ะ$|ครับ$', '', thai_text).strip()
            
            # Remove trailing dots that add formality
            thai_text = thai_text.rstrip('.')
            
            # Remove duplicate politeness markers
            thai_text = re.sub(r'(ค่ะ/ครับ|ครับ/ค่ะ)\s*(ค่ะ/ครับ|ครับ/ค่ะ)', r'\1', thai_text)
            
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