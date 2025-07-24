"""
主程式 - 優化版
精簡 webhook payload，只傳必要資訊
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
import aiohttp

# 添加 src 到 Python 路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.video_processor import VideoProcessor
from src.ai_analyzer import AIAnalyzer
from src.notion_handler import NotionHandler

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def send_webhook(webhook_url: str, payload: Dict):
    """發送精簡的 webhook 通知"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url, 
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    logger.info("✅ Webhook 發送成功")
                else:
                    logger.error(f"❌ Webhook 失敗: {response.status}")
                    logger.error(f"Response: {await response.text()}")
    except Exception as e:
        logger.error(f"❌ Webhook 錯誤: {str(e)}")

async def main():
    """主函數 - 優化版"""
    # 從環境變數獲取資料
    video_url = os.environ.get("VIDEO_URL", "")
    task_name = os.environ.get("TASK_NAME", "")
    gsheet_row_index = os.environ.get("GSHEET_ROW_INDEX", "0")
    assignee = os.environ.get("ASSIGNEE", "")
    photographer = os.environ.get("PHOTOGRAPHER", "")
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    
    # 檢查必要參數
    if not video_url:
        logger.error("❌ 缺少 VIDEO_URL")
        sys.exit(1)
    
    if not gsheet_row_index:
        logger.error("❌ 缺少 GSHEET_ROW_INDEX")
        sys.exit(1)
    
    task_data = {
        "video_url": video_url,
        "task_name": task_name,
        "gsheet_row_index": gsheet_row_index,
        "assignee": assignee,
        "photographer": photographer
    }
    
    logger.info("🚀 開始處理任務")
    logger.info(f"   任務：{task_name}")
    logger.info(f"   影片：{video_url}")
    logger.info(f"   行號：{gsheet_row_index}")
    
    try:
        # 1. 處理影片
        processor = VideoProcessor()
        video_info = await processor.process_video(video_url)
        
        if not video_info.get("success"):
            raise Exception(f"影片處理失敗: {video_info.get('error', '未知錯誤')}")
        
        # 2. AI 分析
        analyzer = AIAnalyzer()
        ai_content = await analyzer.analyze_content(video_info)
        
        # 3. 創建 Notion 頁面
        notion = NotionHandler()
        notion_result = await notion.create_page(task_data, ai_content)
        
        # 準備精簡的成功 payload
        success_payload = {
            "status": "success",
            "gsheet_row_index": gsheet_row_index,
            "processed_at": datetime.now().isoformat()
        }
        
        # 如果 Notion 創建成功，加入連結
        if notion_result and notion_result.get("url"):
            success_payload["notion_page_url"] = notion_result["url"]
            logger.info(f"📄 Notion 頁面: {notion_result['url']}")
        else:
            logger.warning("⚠️ Notion 頁面未創建，但任務處理成功")
        
        # 4. 發送成功通知
        if webhook_url:
            await send_webhook(webhook_url, success_payload)
        
        logger.info("✅ 任務處理完成！")
        
    except Exception as e:
        logger.error(f"❌ 處理失敗: {str(e)}")
        
        # 發送失敗通知 - 極簡版
        if webhook_url:
            await send_webhook(webhook_url, {
                "status": "error",
                "gsheet_row_index": gsheet_row_index,
                "error_message": str(e),
                "processed_at": datetime.now().isoformat()
            })
        
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())