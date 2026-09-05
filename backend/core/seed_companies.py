"""
公司種子資料載入 — 讀取 JSON 寫入資料庫，並生成 embedding
"""
import os
import sys
import json
import logging

# 確保能 import 同層模組
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, init_db
from models import Company
from core.embedding_service import get_embedding, embedding_to_json

logger = logging.getLogger(__name__)

_SEED_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "companies_seed.json"
)


def load_seed_companies(generate_embeddings: bool = True):
    """
    從 JSON 檔案載入公司種子資料到資料庫。

    Args:
        generate_embeddings: 是否同時生成公司描述的 embedding
    """
    init_db()

    with open(_SEED_FILE, "r", encoding="utf-8") as f:
        companies_data = json.load(f)

    db = SessionLocal()
    try:
        added = 0
        skipped = 0

        for comp in companies_data:
            # 檢查是否已存在
            existing = db.query(Company).filter(
                Company.company_id == comp["company_id"]
            ).first()

            if existing:
                logger.info(f"公司已存在，跳過: {comp['company_name']}")
                skipped += 1
                continue

            # 生成 embedding
            embedding_json = None
            if generate_embeddings:
                try:
                    # 用公司描述 + 供應鏈標籤 組合成 embedding 輸入
                    embed_text = (
                        f"{comp['company_name']} ({comp['industry']})\n"
                        f"{comp['business_description']}\n"
                        f"相關領域：{', '.join(comp['supply_chain_tags'])}"
                    )
                    embedding = get_embedding(embed_text)
                    embedding_json = embedding_to_json(embedding)
                    logger.info(f"已生成 embedding: {comp['company_name']}")
                except Exception as e:
                    logger.warning(f"生成 embedding 失敗 ({comp['company_name']}): {e}")

            company = Company(
                company_id=comp["company_id"],
                company_name=comp["company_name"],
                ticker=comp["ticker"],
                industry=comp["industry"],
                business_description=comp["business_description"],
                supply_chain_tags=json.dumps(comp["supply_chain_tags"], ensure_ascii=False),
                embedding=embedding_json,
            )
            db.add(company)
            added += 1

        db.commit()
        logger.info(f"公司種子資料載入完成：新增 {added} 家，跳過 {skipped} 家")
        return added

    except Exception as e:
        db.rollback()
        logger.error(f"載入公司種子資料失敗: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    load_seed_companies()
