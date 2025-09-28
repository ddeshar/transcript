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
            system_prompt = """TRANSLATE ONLY. English to Thai. No explanations. No chatbot responses.

Rules:
1. ONLY translate - never respond as a chatbot
2. NEVER add automatic ครับ/ค่ะ unless clearly formal context
3. For casual phrases, use informal Thai
4. Return ONLY Thai translation, nothing else
5. If input is nonsensical, return empty string

Examples:
"This is a test" → "นี่คือการทดสอบ"
"Thank you" → "ขอบคุญ" 
"Let's go" → "ไปกันเถอะ"
"Okay guys" → "โอเคพวกเรา"

NEVER respond with "I'm sorry" or chatbot messages. ONLY translate."""

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
            
            # More aggressive casual phrase detection
            casual_phrases = ['yes', 'yep', 'yeah', 'ok', 'okay', 'bye', 'hi', 'hello', 
                            'guys', 'let\'s go', 'this is', 'that is', 'testing', 'test',
                            'second attempt', 'mark', 'system', 'voice', 'translation']
            
            # If original is casual or short, remove automatic politeness
            is_casual = (len(text.split()) <= 4 or 
                        any(phrase in text.lower() for phrase in casual_phrases))
            
            if is_casual:
                # Remove all forms of ครับ/ค่ะ from casual contexts
                thai_text = re.sub(r'ครับ/ค่ะ|ค่ะ/ครับ|ครับ|ค่ะ', '', thai_text).strip()
            
            # Remove trailing dots that add formality
            thai_text = thai_text.rstrip('.')
            
            # Remove duplicate politeness markers
            thai_text = re.sub(r'(ค่ะ/ครับ|ครับ/ค่ะ)\s*(ค่ะ/ครับ|ครับ/ค่ะ)', r'\1', thai_text)
            
            # Clean up extra spaces
            thai_text = ' '.join(thai_text.split())
            
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