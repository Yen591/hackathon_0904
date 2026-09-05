import logging

logger = logging.getLogger(__name__)

class FinbertService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FinbertService, cls).__new__(cls)
            cls._instance._init_model()
        return cls._instance

    def _init_model(self):
        logger.info("初始化 FinBERT 模型中... (初次載入可能需要數分鐘下載)")
        try:
            from transformers import pipeline
            # 這裡我們使用知名的財經情緒模型
            self.nlp = pipeline("sentiment-analysis", model="ProsusAI/finbert")
            logger.info("FinBERT 模型載入成功！")
        except ImportError:
            logger.error("未安裝 transformers 或 torch 套件，跳過 FinBERT 初始化")
            self.nlp = None
        except Exception as e:
            logger.error(f"FinBERT 模型載入失敗: {e}")
            self.nlp = None

    def analyze(self, text: str):
        if not self.nlp:
            return {"label": "N/A", "score": 0.0}
        
        try:
            # 取前面文字避免超出 token 限制
            short_text = text[:512]
            result = self.nlp(short_text)[0]
            # result 格式為 {'label': 'positive', 'score': 0.9}
            return result
        except Exception as e:
            logger.error(f"FinBERT 分析發生錯誤: {e}")
            return {"label": "Error", "score": 0.0}
