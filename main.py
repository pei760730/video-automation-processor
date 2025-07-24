# main.py - 流程指揮中心 (v1.1 - 修正版)

import os
import sys
import logging
import asyncio
from datetime import datetime
import aiohttp
from typing import Dict  # <--- 修正: 加入了這一行，解決 NameError

# 將 src 目錄加入 Python 路徑，這樣才能導入其他模組
# 確保無論從哪裡執行，都能找到 src
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from video_processor import VideoProcessor
from ai_analyzer import AIAnalyzer
from notion_handler import NotionHandler

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def send_webhook(webhook_url: str, payload: Dict):
    """發送精簡的 webhook 通知"""
    if not webhook_url:
        logger.warning("⚠️ 未配置 Webhook URL，跳過發送")
        return
        
    try:
        # 將 webhook secret 加入 payload，增強安全性
        payload['secret'] = os.environ.get('N8N_WEBHOOK_SECRET', '')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url, 
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if 200 <= response.status < 300:
                    logger.info(f"✅ Webhook 發送成功 (HTTP {response.status})")
                else:
                    logger.error(f"❌ Webhook 失敗: {response.status}")
                    logger.error(f"   Response: {await response.text()}")
    except Exception as e:
        logger.error(f"❌ Webhook 錯誤: {str(e)}")

async def main_process():
    """主處理流程"""
    # --- 1. 從環境變數獲取任務資料 ---
    webhook_url = os.environ.get("N8N_WEBHOOK_URL")
    task_data = {
        "video_url": os.environ.get("VIDEO_URL"),
        "task_name": os.environ.get("TASK_NAME", "未命名任務"),
        "gsheet_row_index": os.environ.get("GSHEET_ROW_INDEX"),
        "assignee": os.environ.get("ASSIGNEE", ""),
        "photographer": os.environ.get("PHOTOGRAPHER", ""),
        "shoot_date": os.environ.get("SHOOT_DATE", datetime.now().strftime('%Y-%m-%d')),
        "notes": os.environ.get("NOTES", "")
    }

    # 檢查必要參數
    if not task_data.get("video_url") or not task_data.get("gsheet_row_index"):
        error_msg = "缺少必要的環境變數 VIDEO_URL 或 GSHEET_ROW_INDEX"
        logger.error(f"❌ {error_msg}")
        # 即使缺少參數，也要嘗試發送失敗通知
        await send_webhook(webhook_url, {
            "status": "error",
            "gsheet_row_index": task_data.get("gsheet_row_index", "0"),
            "error_message": error_msg,
            "processed_at": datetime.now().isoformat()
        })
        sys.exit(1)

    logger.info("="*50)
    logger.info(f"🚀 開始處理任務: {task_data['task_name']}")
    logger.info(f"   行號: {task_data['gsheet_row_index']}")
    logger.info("="*50)

    try:
        # --- 2. 處理影片 (下載 & 上傳R2) ---
        # 舊寫法: processor = VideoProcessor(); video_info = await processor.process_video(video_url)
        # 修正: 統一使用 process 方法
        processor = VideoProcessor()
        video_info = await processor.process(task_data['video_url'], task_data['task_name'])
        
        # --- 3. AI 分析 ---
        # 舊寫法: analyzer = AIAnalyzer(); ai_content = await analyzer.analyze_content(video_info)
        # 修正: 傳入更多上下文，讓 AI 分析更準確
        analyzer = AIAnalyzer()
        ai_content = await analyzer.analyze(video_info, task_data)

        # --- 4. 創建 Notion 頁面 ---
        # 舊寫法: notion = NotionHandler(); notion_result = await notion.create_page(task_data, ai_content)
        # 修正: 傳入 video_info，可以在 Notion 頁面中加入更多資訊
        notion = NotionHandler()
        notion_result = await notion.create_page(task_data, ai_content, video_info)
        
        # --- 5. 準備並發送成功通知 ---
        success_payload = {
            "status": "success",
            "gsheet_row_index": task_data['gsheet_row_index'],
            "processed_at": datetime.now().isoformat()
        }
        if notion_result and notion_result.get("url"):
            success_payload["notion_page_url"] = notion_result["url"]
        
        await send_webhook(webhook_url, success_payload)
        logger.info("🎉 任務全部處理完成！")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"💥 任務處理流程失敗: {error_msg}", exc_info=True) # exc_info=True 會打印詳細的追蹤日誌
        # --- 6. 準備並發送失敗通知 ---
        await send_webhook(webhook_url, {
            "status": "error",
            "gsheet_row_index": task_data.get("gsheet_row_index", "0"),
            "error_message": error_msg,
            "processed_at": datetime.now().isoformat()
        })
        sys.exit(1)

if __name__ == "__main__":
    # 統一調用主流程函數
    asyncio.run(main_process())