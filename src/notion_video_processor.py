"""
Notion 影片處理器 - 優化版
使用 Multi-select 屬性類型，更精簡的資料結構，增強錯誤處理和日誌功能
"""

import os
import asyncio
import json
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
from notion_client import AsyncClient
from notion_client.errors import APIError, RequestTimeoutError
import logging

logger = logging.getLogger(__name__)

class NotionVideoProcessor:
    """Notion 影片處理器 - 重構優化版"""
    
    def __init__(self):
        """初始化 Notion 處理器"""
        self.api_key = os.environ.get("NOTION_API_KEY")
        self.database_id = os.environ.get("NOTION_DATABASE_ID")
        
        # 配置驗證
        if not self.api_key or not self.database_id:
            logger.warning("⚠️ Notion 配置不完整，將跳過 Notion 操作")
            logger.warning(f"   API Key: {'已設置' if self.api_key else '未設置'}")
            logger.warning(f"   Database ID: {'已設置' if self.database_id else '未設置'}")
            self.enabled = False
            self.client = None
        else:
            self.enabled = True
            self.client = AsyncClient(auth=self.api_key)
            logger.info(f"✅ Notion 已配置")
            logger.info(f"   Database ID: {self.database_id[:8]}...")
    
    async def validate_database_structure(self) -> bool:
        """驗證資料庫結構是否符合要求"""
        if not self.enabled:
            return False
        
        try:
            logger.info("🔍 驗證 Notion 資料庫結構...")
            database = await self.client.databases.retrieve(database_id=self.database_id)
            
            properties = database.get("properties", {})
            required_fields = {
                "任務名稱": "title",
                "狀態": "select", 
                "AI標題建議": "multi_select",
                "標籤建議": "multi_select"
            }
            
            missing_fields = []
            wrong_type_fields = []
            
            for field_name, expected_type in required_fields.items():
                if field_name not in properties:
                    missing_fields.append(field_name)
                elif properties[field_name]["type"] != expected_type:
                    wrong_type_fields.append(f"{field_name} (期望: {expected_type}, 實際: {properties[field_name]['type']})")
            
            if missing_fields or wrong_type_fields:
                logger.error("❌ 資料庫結構驗證失敗")
                if missing_fields:
                    logger.error(f"   缺少欄位: {', '.join(missing_fields)}")
                if wrong_type_fields:
                    logger.error(f"   類型錯誤: {', '.join(wrong_type_fields)}")
                return False
            
            logger.info("✅ 資料庫結構驗證通過")
            return True
            
        except Exception as e:
            logger.error(f"❌ 驗證資料庫結構時發生錯誤：{str(e)}")
            return False
    
    async def create_page(self, task_data: Dict, ai_content: Dict) -> Optional[Dict]:
        """創建 Notion 頁面 - 優化版"""
        if not self.enabled:
            logger.warning("Notion 未啟用，跳過創建頁面")
            return None
        
        # 驗證資料庫結構
        if not await self.validate_database_structure():
            logger.error("資料庫結構驗證失敗，跳過創建頁面")
            return None
        
        try:
            # 準備頁面屬性
            properties = self._prepare_page_properties(task_data, ai_content)
            
            # 創建頁面內容
            children = self._create_page_content(task_data, ai_content)
            
            # 創建 Notion 頁面
            task_name = task_data.get("task_name", "未命名任務")
            logger.info(f"📝 創建 Notion 頁面：{task_name}")
            
            response = await self._create_page_with_retry(properties, children)
            
            if response:
                logger.info(f"✅ Notion 頁面創建成功")
                logger.info(f"   ID: {response['id']}")
                logger.info(f"   URL: {response['url']}")
                
                return {
                    "id": response["id"],
                    "url": response["url"],
                    "created_time": response["created_time"],
                    "status": "success"
                }
            else:
                return None
            
        except Exception as e:
            logger.error(f"❌ 創建 Notion 頁面失敗：{str(e)}")
            logger.error(f"   錯誤類型：{type(e).__name__}")
            logger.error(f"   任務名稱：{task_data.get('task_name', 'Unknown')}")
            return None
    
    def _prepare_page_properties(self, task_data: Dict, ai_content: Dict) -> Dict:
        """準備頁面屬性"""
        properties = {
            "任務名稱": {
                "title": [{"text": {"content": task_data.get("task_name", "未命名任務")}}]
            },
            "狀態": {
                "select": {"name": "AI處理完成"}
            }
        }
        
        # 可選文字欄位
        optional_text_fields = {
            "負責人": task_data.get("assignee", ""),
            "攝影師": task_data.get("photographer", ""),
            "處理時間": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        }
        
        for field_name, value in optional_text_fields.items():
            if value:
                properties[field_name] = {
                    "rich_text": [{"text": {"content": str(value)}}]
                }
        
        # URL 欄位
        if task_data.get("video_url"):
            properties["原始連結"] = {
                "url": task_data.get("video_url", "")
            }
        
        # AI 內容摘要
        if ai_content.get("summary"):
            summary_text = ai_content["summary"][:2000]  # Notion 限制
            properties["內容摘要"] = {
                "rich_text": [{"text": {"content": summary_text}}]
            }
        
        # AI 標題建議 - Multi-select
        if ai_content.get("titles") and isinstance(ai_content["titles"], list):
            valid_titles = [
                {"name": self._sanitize_option_name(title)} 
                for title in ai_content["titles"][:5]  # 最多 5 個
                if title and isinstance(title, str)
            ]
            if valid_titles:
                properties["AI標題建議"] = {"multi_select": valid_titles}
        
        # 標籤建議 - Multi-select
        if ai_content.get("tags") and isinstance(ai_content["tags"], list):
            valid_tags = [
                {"name": self._sanitize_option_name(tag)} 
                for tag in ai_content["tags"][:10]  # 最多 10 個
                if tag and isinstance(tag, str)
            ]
            if valid_tags:
                properties["標籤建議"] = {"multi_select": valid_tags}
        
        return properties
    
    def _sanitize_option_name(self, name: str) -> str:
        """清理選項名稱，確保符合 Notion 要求"""
        if not isinstance(name, str):
            return str(name)
        
        # 移除前後空白，限制長度
        sanitized = name.strip()[:100]
        
        # 移除不允許的字符（如果有的話）
        # Notion multi-select 選項名稱相對寬鬆，但仍需避免某些特殊字符
        sanitized = sanitized.replace('\n', ' ').replace('\r', ' ')
        
        return sanitized if sanitized else "未命名選項"
    
    async def _create_page_with_retry(self, properties: Dict, children: List[Dict], max_retries: int = 3) -> Optional[Dict]:
        """帶重試機制的頁面創建"""
        for attempt in range(max_retries):
            try:
                response = await self.client.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties,
                    children=children
                )
                return response
                
            except RequestTimeoutError:
                logger.warning(f"⏱️ 請求超時，嘗試重試 ({attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # 指數退避
                    
            except APIError as e:
                if e.status == 429:  # Rate limit
                    logger.warning(f"📊 API 速率限制，等待後重試 ({attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5 * (attempt + 1))
                else:
                    logger.error(f"❌ Notion API 錯誤 (狀態碼: {e.status})：{str(e)}")
                    break
                    
            except Exception as e:
                logger.error(f"❌ 創建頁面時發生未預期錯誤：{str(e)}")
                break
        
        return None
    
    def _create_page_content(self, task_data: Dict, ai_content: Dict) -> List[Dict]:
        """創建頁面內容 - 優化版"""
        blocks = []
        
        # 主標題
        task_name = task_data.get("task_name", "影片分析")
        blocks.append({
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"text": {"content": f"🎬 {task_name}"}}]
            }
        })
        
        # 處理狀態卡片
        status_text = f"✅ AI 處理完成\n📅 處理時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"text": {"content": status_text}}],
                "icon": {"emoji": "✅"},
                "color": "green_background"
            }
        })
        
        # 基本資訊區塊
        self._add_basic_info_blocks(blocks, task_data)
        
        # AI 分析結果
        self._add_ai_analysis_blocks(blocks, ai_content)
        
        # 原始連結
        self._add_original_link_block(blocks, task_data)
        
        return blocks
    
    def _add_basic_info_blocks(self, blocks: List[Dict], task_data: Dict) -> None:
        """添加基本資訊區塊"""
        info_items = []
        
        if task_data.get("assignee"):
            info_items.append(f"👤 負責人：{task_data['assignee']}")
        if task_data.get("photographer"):
            info_items.append(f"📸 攝影師：{task_data['photographer']}")
        
        if info_items:
            blocks.extend([
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"text": {"content": "📋 基本資訊"}}]}
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": "\n".join(info_items)}}]}
                }
            ])
    
    def _add_ai_analysis_blocks(self, blocks: List[Dict], ai_content: Dict) -> None:
        """添加 AI 分析結果區塊"""
        if not ai_content:
            return
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"text": {"content": "🤖 AI 分析結果"}}]}
        })
        
        # 內容摘要
        if ai_content.get("summary"):
            blocks.extend([
                {
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {"rich_text": [{"text": {"content": "📝 內容摘要"}}]}
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": ai_content["summary"]}}]}
                }
            ])
        
        # 建議標題列表
        if ai_content.get("titles"):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"text": {"content": "💡 建議標題"}}]}
            })
            
            for i, title in enumerate(ai_content["titles"][:5], 1):
                blocks.append({
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": {
                        "rich_text": [{"text": {"content": title}}]
                    }
                })
        
        # 建議標籤
        if ai_content.get("tags"):
            tags_text = " • ".join(f"#{tag}" for tag in ai_content["tags"][:10])
            blocks.extend([
                {
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {"rich_text": [{"text": {"content": "🏷️ 建議標籤"}}]}
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": tags_text}}]}
                }
            ])
    
    def _add_original_link_block(self, blocks: List[Dict], task_data: Dict) -> None:
        """添加原始連結區塊"""
        if not task_data.get("video_url"):
            return
        
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
    
    async def update_page_status(self, page_id: str, status: str, additional_properties: Optional[Dict] = None) -> bool:
        """更新頁面狀態"""
        if not self.enabled or not page_id:
            return False
        
        try:
            properties = {
                "狀態": {"select": {"name": status}}
            }
            
            if additional_properties:
                properties.update(additional_properties)
            
            await self.client.pages.update(
                page_id=page_id,
                properties=properties
            )
            
            logger.info(f"✅ 更新 Notion 頁面狀態：{status}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 更新頁面狀態失敗：{str(e)}")
            return False
    
    async def get_page_info(self, page_id: str) -> Optional[Dict]:
        """獲取頁面資訊"""
        if not self.enabled or not page_id:
            return None
        
        try:
            response = await self.client.pages.retrieve(page_id=page_id)
            return {
                "id": response["id"],
                "url": response["url"],
                "created_time": response["created_time"],
                "last_edited_time": response["last_edited_time"],
                "properties": response.get("properties", {})
            }
        except Exception as e:
            logger.error(f"❌ 獲取頁面資訊失敗：{str(e)}")
            return None


# 向後相容性別名
NotionHandler = NotionVideoProcessor