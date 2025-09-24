"""
Simple Thai translation provider using basic word mapping.
This is a minimal implementation for demonstration purposes.
"""
from __future__ import annotations

import asyncio
import re

from .mt_base import MTProvider, MTResult


class SimpleThaiProvider(MTProvider):
    name = "simple_thai"

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # Basic English to Thai word mappings for common words
        self.word_map = {
            "hello": "สวัสดี",
            "hi": "สวัสดี",
            "how": "อย่างไร",
            "are": "เป็น",
            "you": "คุณ",
            "good": "ดี",
            "bad": "แย่",
            "yes": "ใช่",
            "no": "ไม่",
            "please": "กรุณา",
            "thank": "ขอบคุณ",
            "thanks": "ขอบคุณ",
            "sorry": "ขอโทษ",
            "excuse": "ขอโทษ",
            "me": "ฉัน",
            "I": "ฉัน",
            "we": "เรา",
            "they": "พวกเขา",
            "this": "นี่",
            "that": "นั่น",
            "what": "อะไร",
            "where": "ที่ไหน",
            "when": "เมื่อไหร่",
            "why": "ทำไม",
            "who": "ใคร",
            "and": "และ",
            "or": "หรือ",
            "but": "แต่",
            "the": "",  # Thai doesn't use articles
            "a": "",
            "an": "",
            "is": "เป็น",
            "am": "เป็น",
            "was": "เป็น",
            "were": "เป็น",
            "have": "มี",
            "has": "มี",
            "had": "มี",
            "do": "ทำ",
            "does": "ทำ",
            "did": "ทำ",
            "will": "จะ",
            "would": "จะ",
            "can": "สามารถ",
            "could": "สามารถ",
            "should": "ควร",
            "must": "ต้อง",
            "my": "ของฉัน",
            "your": "ของคุณ",
            "his": "ของเขา",
            "her": "ของเธอ",
            "our": "ของเรา",
            "their": "ของพวกเขา",
            "one": "หนึ่ง",
            "two": "สอง",
            "three": "สาม",
            "four": "สี่",
            "five": "ห้า",
            "today": "วันนี้",
            "tomorrow": "พรุ่งนี้",
            "yesterday": "เมื่อวาน",
            "now": "ตอนนี้",
            "here": "ที่นี่",
            "there": "ที่นั่น",
            "go": "ไป",
            "come": "มา",
            "see": "เห็น",
            "look": "ดู",
            "listen": "ฟัง",
            "speak": "พูด",
            "talk": "คุย",
            "eat": "กิน",
            "drink": "ดื่ม",
            "sleep": "นอน",
            "work": "ทำงาน",
            "play": "เล่น",
            "study": "เรียน",
            "learn": "เรียนรู้",
            "teach": "สอน",
            "read": "อ่าน",
            "write": "เขียน",
            "understand": "เข้าใจ",
            "know": "รู้",
            "think": "คิด",
            "like": "ชอบ",
            "love": "รัก",
            "want": "ต้องการ",
            "need": "ต้องการ",
            "help": "ช่วย",
            "call": "โทร",
            "buy": "ซื้อ",
            "sell": "ขาย",
            "give": "ให้",
            "take": "เอา",
            "get": "ได้",
            "make": "ทำ",
            "put": "วาง",
            "find": "หา",
            "open": "เปิด",
            "close": "ปิด",
            "start": "เริ่ม",
            "stop": "หยุด",
            "finish": "จบ",
            "big": "ใหญ่",
            "small": "เล็ก",
            "new": "ใหม่",
            "old": "เก่า",
            "hot": "ร้อน",
            "cold": "เย็น",
            "fast": "เร็ว",
            "slow": "ช้า",
            "high": "สูง",
            "low": "ต่ำ",
            "long": "ยาว",
            "short": "สั้น",
            "easy": "ง่าย",
            "hard": "ยาก",
            "right": "ถูก",
            "wrong": "ผิด",
            "important": "สำคัญ",
            "different": "ต่าง",
            "same": "เหมือน",
            "more": "มากกว่า",
            "less": "น้อยกว่า",
            "very": "มาก",
            "quite": "ค่อนข้าง",
            "really": "จริงๆ",
            "maybe": "บางที",
            "perhaps": "อาจจะ",
            "probably": "น่าจะ",
            "definitely": "แน่นอน",
            "always": "เสมอ",
            "never": "ไม่เคย",
            "sometimes": "บางครั้ง",
            "often": "บ่อย",
            "usually": "ปกติ",
            "love": "รัก",
            "like": "ชอบ",
            "want": "ต้องการ",
            "need": "ต้องการ",
            "know": "รู้",
            "understand": "เข้าใจ",
            "help": "ช่วย",
            "give": "ให้",
            "take": "เอา",
            "get": "ได้",
            "put": "วาง",
            "make": "ทำ",
            "buy": "ซื้อ",
            "sell": "ขาย",
            "pay": "จ่าย",
            "money": "เงิน",
            "time": "เวลา",
            "day": "วัน",
            "night": "คืน",
            "morning": "เช้า",
            "afternoon": "บ่าย",
            "evening": "เย็น",
            "week": "สัปดาห์",
            "month": "เดือน",
            "year": "ปี",
            "water": "น้ำ",
            "food": "อาหาร",
            "house": "บ้าน",
            "car": "รถ",
            "phone": "โทรศัพท์",
            "computer": "คอมพิวเตอร์",
            "book": "หนังสือ",
            "music": "เพลง",
            "movie": "หนัง",
            "game": "เกม",
            "friend": "เพื่อน",
            "family": "ครอบครัว",
            "mother": "แม่",
            "father": "พ่อ",
            "sister": "พี่สาว",
            "brother": "พี่ชาย",
            "big": "ใหญ่",
            "small": "เล็ก",
            "old": "เก่า",
            "new": "ใหม่",
            "hot": "ร้อน",
            "cold": "เย็น",
            "fast": "เร็ว",
            "slow": "ช้า",
            "easy": "ง่าย",
            "hard": "ยาก",
            "happy": "มีความสุข",
            "sad": "เศร้า",
            "angry": "โกรธ",
            "beautiful": "สวย",
            "ugly": "น่าเกลียด"
        }

    async def setup(self) -> None:
        # No setup required for simple mapping
        pass

    async def translate(self, text: str, *, is_final: bool) -> MTResult:
        if not text.strip():
            return MTResult(text="", provider=self.name, is_final=is_final)
        
        # Simple word-by-word translation
        thai_text = self._translate_simple(text.lower())
        
        return MTResult(
            text=thai_text,
            provider=self.name,
            is_final=is_final,
            raw={"original": text, "method": "simple_mapping"}
        )

    def _translate_simple(self, text: str) -> str:
        """
        Simple word-by-word translation using the word mapping.
        """
        # Remove punctuation and split into words
        words = re.findall(r'\b\w+\b', text.lower())
        
        translated_words = []
        for word in words:
            if word in self.word_map:
                thai_word = self.word_map[word]
                if thai_word:  # Skip empty translations (like articles)
                    translated_words.append(thai_word)
            else:
                # Keep unknown words as is, but mark them
                translated_words.append(f"[{word}]")
        
        return " ".join(translated_words)


__all__ = ["SimpleThaiProvider"]
