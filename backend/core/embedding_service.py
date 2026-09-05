"""
Embedding 統一服務 — 封裝 Gemini / OpenAI 的 Embedding API
提供文字向量化與相似度計算功能
"""
import os
import json
import numpy as np
from dotenv import load_dotenv

load_dotenv()


def get_embedding(text: str, provider: str = None) -> list[float]:
    """
    取得文字的 embedding 向量。

    Args:
        text: 要向量化的文字
        provider: "gemini" 或 "openai"，預設讀取 .env 的 LLM_PROVIDER

    Returns:
        float list — embedding 向量
    """
    if provider is None:
        provider = os.getenv("LLM_PROVIDER", "gemini")

    if provider == "gemini":
        return _embed_gemini(text)
    elif provider == "openai":
        return _embed_openai(text)
    else:
        raise ValueError(f"不支援的 embedding provider: {provider}")


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """計算兩個向量的 cosine similarity"""
    a = np.array(vec1)
    b = np.array(vec2)
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def embedding_to_json(embedding: list[float]) -> str:
    """將 embedding 轉為 JSON 字串，供資料庫儲存"""
    return json.dumps(embedding)


def json_to_embedding(json_str: str) -> list[float]:
    """從 JSON 字串還原 embedding"""
    if not json_str:
        return []
    return json.loads(json_str)


def _embed_gemini(text: str) -> list[float]:
    """使用 Gemini Embedding API"""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 未設定，請檢查 .env 檔案")

    client = genai.Client(api_key=api_key)
    result = client.models.embed_content(
        model="gemini-embedding-1",
        contents=text,
        config=types.EmbedContentConfig(
            task_type="SEMANTIC_SIMILARITY",
        )
    )
    return result.embeddings[0].values


def _embed_openai(text: str) -> list[float]:
    """使用 OpenAI Embedding API"""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 未設定，請檢查 .env 檔案")

    client = OpenAI(api_key=api_key)
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding
