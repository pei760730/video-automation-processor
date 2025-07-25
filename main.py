# 檔案路徑: main.py

import os
import sys
import json
import structlog

# 👇 關鍵在於這一行：我們要從新的 notion_video_processor 檔案匯入 NotionVideoProcessor 類別
from src.notion_video_processor import NotionVideoProcessor

# 設定日誌
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(ensure_ascii=False)
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logger = structlog.get_logger(__name__)

def main():
    try:
        logger.info("=== Video Pipeline 啟動 ===")
        
        processor = NotionVideoProcessor()
        result = processor.process()
        
        print("\n--- 處理結果 ---")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("------------------\n")

        if os.getenv('GITHUB_OUTPUT'):
            with open(os.getenv('GITHUB_OUTPUT'), 'a') as f:
                f.write(f"result_json={json.dumps(result, ensure_ascii=False)}\n")
        
        logger.info(f"✅ 任務 '{result.get('task_name')}' 處理完畢，最終狀態: {result.get('status')}")

    except Exception as e:
        logger.error("主程式執行失敗", error=str(e), exc_info=True)
        if os.getenv('GITHUB_STEP_SUMMARY'):
            with open(os.getenv('GITHUB_STEP_SUMMARY'), 'a') as f:
                f.write(f"## ❌ 處理失敗\n**錯誤:** `{str(e)}`\n")
        sys.exit(1)

if __name__ == "__main__":
    main()