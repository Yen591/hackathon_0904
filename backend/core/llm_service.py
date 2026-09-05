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
    from openai import OpenAI, BadRequestError
    
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    if not api_key:
        raise ValueError("OPENAI_API_KEY 未設定，請檢查 .env 檔案")
    
    client = OpenAI(api_key=api_key)
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
        )
    except BadRequestError as e:
        if "temperature" in str(e).lower():
            response = client.chat.completions.create(
                model=model,
                messages=messages,
            )
        else:
            raise
    
    return response.choices[0].message.content


def _call_gemini(prompt: str, system_prompt: str) -> str:
    import time
    import logging
    from google import genai
    from google.genai import types

    logger = logging.getLogger("core.llm_service")

    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    if not api_key:
        raise ValueError("GEMINI_API_KEY 未設定，請檢查 .env 檔案")

    client = genai.Client(api_key=api_key)

    config = types.GenerateContentConfig(temperature=0.3)
    if system_prompt:
        config.system_instruction = system_prompt

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            return response.text
        except Exception as e:
            error_msg = str(e)
            if attempt < max_retries - 1 and ("EOF" in error_msg or "stream" in error_msg or "429" in error_msg or "503" in error_msg):
                wait_time = (attempt + 1) * 5  # 5s, 10s, 15s
                logger.warning(f"Gemini API 呼叫失敗 (第 {attempt+1} 次): {error_msg}，{wait_time} 秒後重試...")
                time.sleep(wait_time)
            else:
                raise

