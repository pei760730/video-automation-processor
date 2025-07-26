"""
影片自動化處理系統 - 主程式
整合 Notion、影片處理和 AI 分析功能
"""

import os
import sys
import asyncio
import logging
import traceback
from typing import Dict, Optional, Any
from datetime import datetime
from pathlib import Path

# 確保能找到 src 模組
sys.path.insert(0, str(Path(__file__).parent))

# 導入自定義模組
from src.notion_video_processor import NotionVideoProcessor
from src.video_processor import VideoProcessor
from src.ai_analyzer import AIAnalyzer
from src.config import Config

# 設定詳細的 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('process.log', mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class VideoAutomationProcessor:
    """影片自動化處理主控制器"""
    
    def __init__(self):
        """初始化處理器"""
        self.notion_processor = None
        self.video_processor = None
        self.ai_analyzer = None
        self.config = Config()
        
        # 處理結果追蹤
        self.processing_results = {
            "start_time": None,
            "end_time": None,
            "status": "initializing",
            "notion_page": None,
            "video_analysis": None,
            "ai_results": None,
            "errors": []
        }
    
    async def initialize_processors(self) -> bool:
        """初始化所有處理器"""
        try:
            logger.info("🚀 初始化處理器...")
            
            # 初始化各個處理器
            self.notion_processor = NotionVideoProcessor()
            self.video_processor = VideoProcessor()
            self.ai_analyzer = AIAnalyzer()
            
            # 檢查必要的處理器是否可用
            processors_status = {
                "Notion": self.notion_processor.enabled if self.notion_processor else False,
                "Video": hasattr(self.video_processor, 'enabled') and self.video_processor.enabled if self.video_processor else True,
                "AI": hasattr(self.ai_analyzer, 'enabled') and self.ai_analyzer.enabled if self.ai_analyzer else True
            }
            
            logger.info("📊 處理器狀態：")
            for name, status in processors_status.items():
                status_icon = "✅" if status else "⚠️"
                logger.info(f"   {status_icon} {name}: {'已啟用' if status else '已停用'}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化處理器失敗：{str(e)}")
            self.processing_results["errors"].append(f"初始化失敗: {str(e)}")
            return False
    
    def validate_environment(self) -> Dict[str, Any]:
        """驗證環境變數和配置"""
        logger.info("🔍 驗證環境配置...")
        
        # 必要的環境變數
        required_env = {
            "ORIGINAL_LINK": "影片連結",
            "TASK_NAME": "任務名稱"
        }
        
        # 可選的環境變數
        optional_env = {
            "NOTION_PAGE_ID": "Notion 頁面 ID",
            "PERSON_IN_CHARGE": "負責人",
            "VIDEOGRAPHER": "攝影師",
            "NOTION_API_KEY": "Notion API 金鑰",
            "NOTION_DATABASE_ID": "Notion 資料庫 ID"
        }
        
        validation_result = {
            "valid": True,
            "missing_required": [],
            "missing_optional": [],
            "config": {}
        }
        
        # 檢查必要環境變數
        for env_key, description in required_env.items():
            value = os.environ.get(env_key)
            if not value:
                validation_result["missing_required"].append(f"{env_key} ({description})")
                validation_result["valid"] = False
            else:
                validation_result["config"][env_key] = value
        
        # 檢查可選環境變數
        for env_key, description in optional_env.items():
            value = os.environ.get(env_key)
            if not value:
                validation_result["missing_optional"].append(f"{env_key} ({description})")
            else:
                validation_result["config"][env_key] = value
        
        # 記錄驗證結果
        if validation_result["missing_required"]:
            logger.error("❌ 缺少必要環境變數：")
            for missing in validation_result["missing_required"]:
                logger.error(f"   - {missing}")
        
        if validation_result["missing_optional"]:
            logger.warning("⚠️ 缺少可選環境變數：")
            for missing in validation_result["missing_optional"]:
                logger.warning(f"   - {missing}")
        
        if validation_result["valid"]:
            logger.info("✅ 環境配置驗證通過")
        
        return validation_result
    
    def prepare_task_data(self, env_config: Dict[str, str]) -> Dict[str, Any]:
        """準備任務資料"""
        task_data = {
            "notion_page_id": env_config.get("NOTION_PAGE_ID"),
            "video_url": env_config.get("ORIGINAL_LINK"),
            "task_name": env_config.get("TASK_NAME", "未命名任務"),
            "assignee": env_config.get("PERSON_IN_CHARGE", ""),
            "photographer": env_config.get("VIDEOGRAPHER", ""),
            "created_at": datetime.now().isoformat(),
            "processing_id": f"proc_{int(datetime.now().timestamp())}"
        }
        
        logger.info("📋 任務資料準備完成：")
        logger.info(f"   - 任務名稱：{task_data['task_name']}")
        logger.info(f"   - 影片連結：{task_data['video_url']}")
        logger.info(f"   - 負責人：{task_data['assignee'] or '未指定'}")
        logger.info(f"   - 攝影師：{task_data['photographer'] or '未指定'}")
        logger.info(f"   - Notion Page ID：{task_data['notion_page_id'] or '未指定'}")
        logger.info(f"   - 處理 ID：{task_data['processing_id']}")
        
        return task_data
    
    async def process_video(self, task_data: Dict[str, Any]) -> Optional[Dict]:
        """處理影片分析"""
        if not self.video_processor:
            logger.warning("⚠️ 影片處理器未初始化，跳過影片處理")
            return None
        
        try:
            logger.info("🎥 開始影片處理...")
            
            # 這裡根據你的 VideoProcessor 實際介面調整
            video_result = await self.video_processor.process(task_data["video_url"])
            
            if video_result:
                logger.info("✅ 影片處理完成")
                self.processing_results["video_analysis"] = video_result
                return video_result
            else:
                logger.warning("⚠️ 影片處理無結果")
                return None
                
        except Exception as e:
            logger.error(f"❌ 影片處理失敗：{str(e)}")
            self.processing_results["errors"].append(f"影片處理失敗: {str(e)}")
            return None
    
    async def analyze_with_ai(self, task_data: Dict[str, Any], video_data: Optional[Dict] = None) -> Optional[Dict]:
        """AI 分析處理"""
        if not self.ai_analyzer:
            logger.warning("⚠️ AI 分析器未初始化，跳過 AI 分析")
            return None
        
        try:
            logger.info("🤖 開始 AI 分析...")
            
            # 準備 AI 分析的輸入資料
            analysis_input = {
                "video_url": task_data["video_url"],
                "task_name": task_data["task_name"],
                "video_data": video_data
            }
            
            # 根據你的 AIAnalyzer 實際介面調整
            ai_result = await self.ai_analyzer.analyze(analysis_input)
            
            if ai_result:
                logger.info("✅ AI 分析完成")
                logger.info(f"   - 生成摘要：{'是' if ai_result.get('summary') else '否'}")
                logger.info(f"   - 建議標題數量：{len(ai_result.get('titles', []))}")
                logger.info(f"   - 建議標籤數量：{len(ai_result.get('tags', []))}")
                
                self.processing_results["ai_results"] = ai_result
                return ai_result
            else:
                logger.warning("⚠️ AI 分析無結果")
                return None
                
        except Exception as e:
            logger.error(f"❌ AI 分析失敗：{str(e)}")
            self.processing_results["errors"].append(f"AI 分析失敗: {str(e)}")
            return None
    
    async def create_notion_page(self, task_data: Dict[str, Any], ai_content: Dict) -> Optional[Dict]:
        """創建 Notion 頁面"""
        if not self.notion_processor or not self.notion_processor.enabled:
            logger.warning("⚠️ Notion 處理器未啟用，跳過 Notion 頁面創建")
            return None
        
        try:
            logger.info("📝 創建 Notion 頁面...")
            
            notion_result = await self.notion_processor.create_page(task_data, ai_content)
            
            if notion_result:
                logger.info("✅ Notion 頁面創建成功")
                self.processing_results["notion_page"] = notion_result
                return notion_result
            else:
                logger.warning("⚠️ Notion 頁面創建失敗")
                return None
                
        except Exception as e:
            logger.error(f"❌ Notion 頁面創建過程發生錯誤：{str(e)}")
            self.processing_results["errors"].append(f"Notion 頁面創建失敗: {str(e)}")
            return None
    
    def generate_summary_report(self) -> None:
        """生成處理總結報告"""
        self.processing_results["end_time"] = datetime.now().isoformat()
        
        # 計算處理時間
        if self.processing_results["start_time"]:
            start = datetime.fromisoformat(self.processing_results["start_time"])
            end = datetime.fromisoformat(self.processing_results["end_time"])
            duration = (end - start).total_seconds()
        else:
            duration = 0
        
        logger.info("="*60)
        logger.info("📊 處理總結報告")
        logger.info("="*60)
        logger.info(f"⏱️ 總處理時間：{duration:.2f} 秒")
        logger.info(f"📄 Notion 頁面：{'已創建' if self.processing_results['notion_page'] else '未創建'}")
        logger.info(f"🎥 影片分析：{'已完成' if self.processing_results['video_analysis'] else '未完成'}")
        logger.info(f"🤖 AI 分析：{'已完成' if self.processing_results['ai_results'] else '未完成'}")
        
        if self.processing_results["errors"]:
            logger.warning(f"⚠️ 處理過程中發生 {len(self.processing_results['errors'])} 個錯誤：")
            for i, error in enumerate(self.processing_results["errors"], 1):
                logger.warning(f"   {i}. {error}")
        else:
            logger.info("✅ 處理過程無錯誤")
        
        # 輸出 Notion 頁面連結（如果有）
        if self.processing_results["notion_page"]:
            logger.info(f"🔗 Notion 頁面連結：{self.processing_results['notion_page']['url']}")
        
        logger.info("="*60)
    
    async def run(self) -> int:
        """執行完整的處理流程"""
        self.processing_results["start_time"] = datetime.now().isoformat()
        self.processing_results["status"] = "running"
        
        try:
            logger.info("="*60)
            logger.info("🚀 開始執行影片處理流程")
            logger.info("="*60)
            
            # 1. 驗證環境配置
            validation_result = self.validate_environment()
            if not validation_result["valid"]:
                logger.error("❌ 環境配置驗證失敗，程式終止")
                self.processing_results["status"] = "failed"
                return 1
            
            # 2. 準備任務資料
            task_data = self.prepare_task_data(validation_result["config"])
            
            # 3. 初始化處理器
            if not await self.initialize_processors():
                logger.error("❌ 處理器初始化失敗，程式終止")
                self.processing_results["status"] = "failed"
                return 1
            
            # 4. 影片處理（可選）
            video_data = await self.process_video(task_data)
            
            # 5. AI 分析
            ai_content = await self.analyze_with_ai(task_data, video_data)
            if not ai_content:
                logger.error("❌ AI 分析失敗，無法繼續處理")
                self.processing_results["status"] = "failed"
                return 1
            
            # 6. 創建 Notion 頁面
            notion_result = await self.create_notion_page(task_data, ai_content)
            
            # 7. 判斷整體處理結果
            if notion_result or not self.notion_processor.enabled:
                self.processing_results["status"] = "completed"
                logger.info("🎉 處理流程全部完成")
                return 0
            else:
                self.processing_results["status"] = "partial"
                logger.warning("⚠️ 處理流程部分完成，但 Notion 頁面創建失敗")
                return 2
        
        except KeyboardInterrupt:
            logger.warning("⚠️ 使用者中斷處理流程")
            self.processing_results["status"] = "interrupted"
            return 130
        
        except Exception as e:
            logger.error(f"❌ 處理流程發生未預期錯誤：{str(e)}")
            logger.error(f"   錯誤類型：{type(e).__name__}")
            logger.error("   錯誤堆疊：")
            logger.error(traceback.format_exc())
            
            self.processing_results["status"] = "error"
            self.processing_results["errors"].append(f"未預期錯誤: {str(e)}")
            return 1
        
        finally:
            # 生成總結報告
            self.generate_summary_report()


async def main():
    """主程式入口"""
    processor = VideoAutomationProcessor()
    exit_code = await processor.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    # 設定事件迴圈策略（Windows 相容性）
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("⚠️ 程式被使用者中斷")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ 程式啟動失敗：{str(e)}")
        sys.exit(1)