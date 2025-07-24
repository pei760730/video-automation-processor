"""
Notion 處理器 - 優化版
使用 Multi-select 屬性類型，更精簡的資料結構
"""

import os
import asyncio
from typing import Dict, Optional, List
from datetime import datetime
from notion_client import AsyncClient
import logging

logger = logging.getLogger(__name__)

class NotionHandler:
    def __init__(self):
        self.api_key = os.environ.get("NOTION_API_KEY")
        self.database_id = os.environ.get("NOTION_DATABASE_ID")
        
        if not self.api_key or not self.database_id:
            logger.warning("⚠️ Notion 配置不完整，將跳過 Notion 操作")
            self.enabled = False
            self.client = None
        else:
            self.enabled = True
            self.client = AsyncClient(auth=self.api_key)
            logger.info(f"✅ Notion 已配置 - Database ID: {self.database_id[:8]}...")
    
    async def create_page(self, task_data: Dict, ai_content: Dict) -> Optional[Dict]:
        """創建 Notion 頁面 - 優化版"""
        if not self.enabled:
            logger.warning("Notion 未啟用，跳過創建頁面")
            return None
        
        try:
            # 準備頁面屬性
            properties = {
                "任務名稱": {
                    "title": [{"text": {"content": task_data.get("task_name", "未命名任務")}}]
                },
                "狀態": {
                    "select": {"name": "AI判定中"}
                },
                "負責人": {
                    "rich_text": [{"text": {"content": str(task_data.get("assignee", ""))}}]
                },
                "攝影師": {
                    "rich_text": [{"text": {"content": str(task_data.get("photographer", ""))}}]
                },
                "原始連結": {
                    "url": task_data.get("video_url", "")
                }
            }
            
            # 內容摘要 - 保持 rich_text
            if ai_content.get("summary"):
                properties["內容摘要"] = {
                    "rich_text": [{"text": {"content": ai_content["summary"][:2000]}}]
                }
            
            # AI標題建議 - 改用 Multi-select
            if ai_content.get("titles"):
                properties["AI標題建議"] = {
                    "multi_select": [
                        {"name": title[:100]} 
                        for title in ai_content.get("titles", [])[:5]  # 最多 5 個
                    ]
                }
            
            # 標籤建議 - 改用 Multi-select
            if ai_content.get("tags"):
                properties["標籤建議"] = {
                    "multi_select": [
                        {"name": tag[:100]} 
                        for tag in ai_content.get("tags", [])[:10]  # 最多 10 個
                    ]
                }
            
            # 創建頁面內容
            children = self._create_page_content(task_data, ai_content)
            
            # 創建 Notion 頁面
            logger.info(f"📝 創建 Notion 頁面：{task_data.get('task_name', 'Unknown')}")
            
            response = await self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
                children=children
            )
            
            logger.info(f"✅ Notion 頁面創建成功")
            logger.info(f"   ID: {response['id']}")
            logger.info(f"   URL: {response['url']}")
            
            return {
                "id": response["id"],
                "url": response["url"],
                "created_time": response["created_time"]
            }
            
        except Exception as e:
            logger.error(f"❌ 創建 Notion 頁面失敗：{str(e)}")
            if "validation" in str(e).lower():
                logger.error("💡 提示：請確認 Notion 資料庫中的欄位類型設置正確")
                logger.error("   - AI標題建議：應為 Multi-select 類型")
                logger.error("   - 標籤建議：應為 Multi-select 類型")
            return None
    
    def _create_page_content(self, task_data: Dict, ai_content: Dict) -> List[Dict]:
        """創建頁面內容 - 優化版"""
        blocks = []
        
        # 標題區塊
        blocks.append({
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"text": {"content": f"🎬 {task_data.get('task_name', '影片分析')}"}}]
            }
        })
        
        # 基本資訊卡片
        info_text = f"📅 處理時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        if task_data.get("assignee"):
            info_text += f"👤 負責人：{task_data['assignee']}\n"
        if task_data.get("photographer"):
            info_text += f"📸 攝影師：{task_data['photographer']}"
        
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"text": {"content": info_text.strip()}}],
                "icon": {"emoji": "📋"},
                "color": "blue_background"
            }
        })
        
        # 內容摘要
        if ai_content.get("summary"):
            blocks.extend([
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"text": {"content": "📝 內容摘要"}}]}
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": ai_content["summary"]}}]}
                }
            ])
        
        # 原始連結
        if task_data.get("video_url"):
            blocks.extend([
                {
                    "object": "block",
                    "type": "divider",
                    "divider": {}
                },
                {
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {"rich_text": [{"text": {"content": "🔗 原始影片"}}]}
                },
                {
                    "object": "block",
                    "type": "bookmark",
                    "bookmark": {"url": task_data.get("video_url")}
                }
            ])
        
        return blocks