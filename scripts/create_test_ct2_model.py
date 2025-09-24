#!/usr/bin/env python3
"""
Create a simple test CTranslate2 model setup.

This creates a minimal model structure that the CTranslate2 provider can load,
even if it doesn't produce high-quality translations.
"""
import json
from pathlib import Path


def create_test_ct2_model():
    """Create a minimal CTranslate2 model for testing the provider."""
    output_dir = Path("models/ctranslate2/en-th")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a minimal config.json
    config = {
        "model_type": "TransformerDecoder",
        "version": "4.0.0",
        "source_vocabulary_size": 32000,
        "target_vocabulary_size": 32000,
        "num_layers": 6,
        "num_heads": 8,
        "ffn_inner_dim": 2048,
        "model_dim": 512,
    }
    
    with open(output_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2)
    
    print("Created minimal config.json")
    
    # Create a simple vocabulary file for SentencePiece
    # This is a very basic vocab for testing
    vocab_tokens = [
        "<unk>", "<s>", "</s>", "▁", "▁the", "▁a", "▁an", "▁and", "▁or", "▁but",
        "▁is", "▁are", "▁was", "▁were", "▁be", "▁been", "▁being",
        "▁I", "▁you", "▁he", "▁she", "▁it", "▁we", "▁they",
        "▁hello", "▁hi", "▁good", "▁morning", "▁afternoon", "▁evening",
        "▁yes", "▁no", "▁please", "▁thank", "▁thanks", "▁welcome",
        "▁how", "▁what", "▁when", "▁where", "▁who", "▁why",
        "▁do", "▁does", "▁did", "▁will", "▁would", "▁can", "▁could",
        "▁go", "▁come", "▁see", "▁look", "▁take", "▁give", "▁get",
        # Thai tokens (basic)
        "▁สวัสดี", "▁ขอบคุณ", "▁ครับ", "▁ค่ะ", "▁ไป", "▁มา", "▁เป็น", "▁อยู่",
        "▁ที่", "▁นี่", "▁นั่น", "▁อะไร", "▁ยังไง", "▁เมื่อไหร่", "▁ที่ไหน",
    ]
    
    # Extend to 32000 tokens with numbered placeholders
    while len(vocab_tokens) < 32000:
        vocab_tokens.append(f"▁token_{len(vocab_tokens)}")
    
    print(f"Generated {len(vocab_tokens)} vocabulary tokens")
    
    # Note: We can't create actual model.bin files without trained weights
    # The provider will fail during actual loading, but this gives us the structure
    print(f"Basic model structure created at {output_dir}")
    print("Note: This is just a test structure. For real translation, you'll need:")
    print("1. A properly trained model (model.bin)")
    print("2. Proper SentencePiece files (.spm)")
    print("3. Consider using a cloud MT provider for production use")


if __name__ == "__main__":
    create_test_ct2_model()