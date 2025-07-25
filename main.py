# main.py - 流程指揮中心 (v1.3 - 加強版 & 繁體中文)

import os
import sys
import logging
import asyncio
from datetime import datetime
import aiohttp
from typing import Dict

# 將 src 目錄加入 Python 路徑
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from video_processor import VideoProcessor
from ai_analyzer import AIAnalyzer
from notion_handler import NotionHandler

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def send_webhook(webhook_url: str, payload: Dict):
    """發送 webhook 通知，並提供清晰的錯誤提示"""
    if not webhook_url:
        logger.warning("⚠️ 未配置 Webhook URL，跳過發送")
        return
        
    try:
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
                    response_text = await response.text()
                    logger.error(f"❌ Webhook 失敗: {response.status}")
                    logger.error(f"   Response: {response_text}")
                    # 為 n8n 404 錯誤提供特別提示
                    if response.status == 404 and "not registered" in response_text:
                        logger.error("💡 提示：這是一個 n8n Webhook 404 錯誤。請確保：")
                        logger.error("   1. n8n 工作流 2 已被啟用 (Active)。")
                        logger.error("   2. GitHub Secret 'N8N_WEBHOOK_URL' 使用的是 Production URL，而不是 Test URL。")
                        
    except Exception as e:
        logger.error(f"❌ Webhook 發生未知錯誤: {str(e)}")

async def main_process():
    """主處理流程"""
    webhook_url = os.environ.get("N8N_WEBHOOK_URL")
    
    # --- 1. 獲取並驗證輸入參數 ---
    task_data = {
        "video_url": (os.environ.get("VIDEO_URL") or "").strip(),
        "task_name": (os.environ.get("TASK_NAME") or "未命名任務").strip(),
        "gsheet_row_index": os.environ.get("GSHEET_ROW_INDEX"),
        "assignee": os.environ.get("ASSIGNEE", ""),
        "photographer": os.environ.get("PHOTOGRAPHER", ""),
        "shoot_date": os.environ.get("SHOOT_DATE", datetime.now().strftime('%Y-%m-%d')),
        "notes": os.environ.get("NOTES", "")
    }

    # 在流程早期驗證必要參數，如果失敗則立即退出並通知
    if not task_data.get("gsheet_row_index"):
        logger.error("❌ 致命錯誤：缺少 GSHEET_ROW_INDEX，無法繼續處理。")
        sys.exit(1) # 無法更新狀態，只能直接退出

    if not task_data.get("video_url") or not task_data["video_url"].startswith(('http://', 'https://')):
        error_msg = f"無效或空的影片 URL: '{task_data.get('video_url')}'"
        logger.error(f"❌ {error_msg}")
        await send_webhook(webhook_url, {
            "status": "error",
            "gsheet_row_index": task_data["gsheet_row_index"],
            "error_message": error_msg
        })
        sys.exit(1)

    logger.info("="*50)
    logger.info(f"🚀 開始處理任務: {task_data['task_name']}")
    logger.info(f"   行號: {task_data['gsheet_row_index']}")
    logger.info(f"   URL: {task_data['video_url']}")
    logger.info("="*50)

    try:
        # --- 2. 核心處理流程 ---
        processor = VideoProcessor()
        video_info = await processor.process(task_data['video_url'], task_data['task_name'])
        
        analyzer = AIAnalyzer()
        ai_content = await analyzer.analyze(video_info, task_data)

        notion = NotionHandler()
        notion_result = await notion.create_page(task_data, ai_content, video_info)
        
        # --- 3. 準備並發送成功通知 ---
        success_payload = {
            "status": "success",
            "gsheet_row_index": task_data['gsheet_row_index'],
            "notion_page_url": notion_result.get("url") if notion_result else ""
        }
        await send_webhook(webhook_url, success_payload)
        logger.info("🎉 任務全部處理完成！")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"💥 任務處理流程失敗: {error_msg}", exc_info=True)
        # --- 4. 準備並發送失敗通知 ---
        await send_webhook(webhook_url, {
            "status": "error",
            "gsheet_row_index": task_data["gsheet_row_index"],
            "error_message": error_msg[:500] # 限制長度
        })
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main_process())