import os
import json
from dotenv import load_dotenv

load_dotenv()

def get_llm_response(prompt: str, system_prompt: str = "", provider: str = None) -> str:
    """
    統一的 LLM 呼叫介面，支援 OpenAI 與 Gemini 切換。
    
    Args:
        prompt: 使用者 prompt (新聞內容 + 公司清單等)
        system_prompt: 系統指令 (定義 AI 角色與輸出格式)
        provider: 指定使用 "openai" 或 "gemini"，若不指定則讀取 .env 的 LLM_PROVIDER
    
    Returns:
        LLM 回傳的文字內容
    """
    if provider is None:
        provider = os.getenv("LLM_PROVIDER", "gemini")
    
    if provider == "openai":
        return _call_openai(prompt, system_prompt)
    elif provider == "gemini":
        return _call_gemini(prompt, system_prompt)
    else:
        raise ValueError(f"不支援的 LLM provider: {provider}")


def get_llm_json_response(prompt: str, system_prompt: str = "", provider: str = None) -> dict:
    """
    呼叫 LLM 並解析 JSON 回傳。
    若 LLM 回傳的文字包含 markdown code block，會自動清理後再解析。
    """
    raw = get_llm_response(prompt, system_prompt, provider)
    
    # 清理可能的 markdown code block 包裝
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    
    return json.loads(cleaned)


def _call_openai(prompt: str, system_prompt: str) -> str:
    from openai import OpenAI
    
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    if not api_key:
        raise ValueError("OPENAI_API_KEY 未設定，請檢查 .env 檔案")
    
    client = OpenAI(api_key=api_key)
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
    )
    
    return response.choices[0].message.content


def _call_gemini(prompt: str, system_prompt: str) -> str:
    import google.generativeai as genai
    
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    if not api_key:
        raise ValueError("GEMINI_API_KEY 未設定，請檢查 .env 檔案")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_prompt if system_prompt else None,
    )
    
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(temperature=0.3),
    )
    
    return response.text

