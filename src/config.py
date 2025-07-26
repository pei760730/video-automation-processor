"""
配置管理模組 - 增強版
統一管理環境變數、預設值和配置驗證
"""

import os
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class NotionConfig:
    """Notion 相關配置"""
    api_key: Optional[str] = field(default_factory=lambda: os.environ.get("NOTION_API_KEY"))
    database_id: Optional[str] = field(default_factory=lambda: os.environ.get("NOTION_DATABASE_ID"))
    page_id: Optional[str] = field(default_factory=lambda: os.environ.get("NOTION_PAGE_ID"))
    timeout: int = 30
    max_retries: int = 3
    
    @property
    def is_configured(self) -> bool:
        """檢查 Notion 是否已正確配置"""
        return bool(self.api_key and self.database_id)
    
    def validate(self) -> List[str]:
        """驗證配置並返回錯誤訊息列表"""
        errors = []
        
        if not self.api_key:
            errors.append("缺少 NOTION_API_KEY 環境變數")
        elif not self.api_key.startswith("ntn_"):
            errors.append("NOTION_API_KEY 格式不正確，應以 'ntn_' 開頭")
        
        if not self.database_id:
            errors.append("缺少 NOTION_DATABASE_ID 環境變數")
        elif len(self.database_id) != 32:
            errors.append("NOTION_DATABASE_ID 格式不正確，應為 32 字元")
        
        return errors

@dataclass
class TaskConfig:
    """任務相關配置"""
    task_name: str = field(default_factory=lambda: os.environ.get("TASK_NAME", "未命名任務"))
    video_url: Optional[str] = field(default_factory=lambda: os.environ.get("ORIGINAL_LINK"))
    assignee: str = field(default_factory=lambda: os.environ.get("PERSON_IN_CHARGE", ""))
    photographer: str = field(default_factory=lambda: os.environ.get("VIDEOGRAPHER", ""))
    
    def validate(self) -> List[str]:
        """驗證任務配置"""
        errors = []
        
        if not self.video_url:
            errors.append("缺少 ORIGINAL_LINK 環境變數（影片連結）")
        elif not self._is_valid_url(self.video_url):
            errors.append("ORIGINAL_LINK 不是有效的 URL 格式")
        
        return errors
    
    def _is_valid_url(self, url: str) -> bool:
        """簡單的 URL 格式驗證"""
        return url.startswith(('http://', 'https://'))

@dataclass
class ProcessingConfig:
    """處理相關配置"""
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))
    log_file: str = field(default_factory=lambda: os.environ.get("LOG_FILE", "process.log"))
    max_concurrent_tasks: int = field(default_factory=lambda: int(os.environ.get("MAX_CONCURRENT_TASKS", "3")))
    timeout_seconds: int = field(default_factory=lambda: int(os.environ.get("TIMEOUT_SECONDS", "300")))
    
    # AI 相關配置
    ai_max_tokens: int = field(default_factory=lambda: int(os.environ.get("AI_MAX_TOKENS", "2000")))
    ai_temperature: float = field(default_factory=lambda: float(os.environ.get("AI_TEMPERATURE", "0.7")))
    
    # 影片處理配置
    video_download_timeout: int = field(default_factory=lambda: int(os.environ.get("VIDEO_DOWNLOAD_TIMEOUT", "300")))
    max_video_size_mb: int = field(default_factory=lambda: int(os.environ.get("MAX_VIDEO_SIZE_MB", "500")))

class Config:
    """主配置類別 - 統一管理所有配置"""
    
    def __init__(self):
        """初始化配置"""
        self.notion = NotionConfig()
        self.task = TaskConfig()
        self.processing = ProcessingConfig()
        
        self._setup_logging()
        self._validate_all_configs()
    
    def _setup_logging(self):
        """設定日誌配置"""
        try:
            # 確保日誌目錄存在
            log_file = Path(self.processing.log_file)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 設定日誌級別
            numeric_level = getattr(logging, self.processing.log_level.upper(), logging.INFO)
            logging.getLogger().setLevel(numeric_level)
            
            logger.info(f"✅ 日誌配置完成 - 級別: {self.processing.log_level}")
            
        except Exception as e:
            logger.warning(f"⚠️ 日誌配置失敗：{e}")
    
    def _validate_all_configs(self):
        """驗證所有配置"""
        all_errors = []
        
        # 驗證各個配置區塊
        notion_errors = self.notion.validate()
        task_errors = self.task.validate()
        
        all_errors.extend([f"Notion: {err}" for err in notion_errors])
        all_errors.extend([f"Task: {err}" for err in task_errors])
        
        # 記錄驗證結果
        if all_errors:
            logger.warning("⚠️ 配置驗證發現問題：")
            for error in all_errors:
                logger.warning(f"   - {error}")
        else:
            logger.info("✅ 所有配置驗證通過")
        
        self._validation_errors = all_errors
    
    @property
    def is_valid(self) -> bool:
        """檢查配置是否有效"""
        return len(self._validation_errors) == 0
    
    @property
    def validation_errors(self) -> List[str]:
        """取得配置驗證錯誤"""
        return self._validation_errors.copy()
    
    def get_task_data(self) -> Dict[str, Any]:
        """取得任務資料字典"""
        return {
            "notion_page_id": self.notion.page_id,
            "video_url": self.task.video_url,
            "task_name": self.task.task_name,
            "assignee": self.task.assignee,
            "photographer": self.task.photographer
        }
    
    def print_config_summary(self):
        """列印配置摘要"""
        logger.info("="*50)
        logger.info("📋 配置摘要")
        logger.info("="*50)
        
        # Notion 配置
        logger.info("🔧 Notion 配置：")
        logger.info(f"   - API Key: {'已設置' if self.notion.api_key else '未設置'}")
        logger.info(f"   - Database ID: {'已設置' if self.notion.database_id else '未設置'}")
        logger.info(f"   - Page ID: {self.notion.page_id or '未設置'}")
        logger.info(f"   - 重試次數: {self.notion.max_retries}")
        
        # 任務配置
        logger.info("📋 任務配置：")
        logger.info(f"   - 任務名稱: {self.task.task_name}")
        logger.info(f"   - 影片連結: {'已設置' if self.task.video_url else '未設置'}")
        logger.info(f"   - 負責人: {self.task.assignee or '未設置'}")
        logger.info(f"   - 攝影師: {self.task.photographer or '未設置'}")
        
        # 處理配置
        logger.info("⚙️ 處理配置：")
        logger.info(f"   - 日誌級別: {self.processing.log_level}")
        logger.info(f"   - 並發任務數: {self.processing.max_concurrent_tasks}")
        logger.info(f"   - 超時時間: {self.processing.timeout_seconds}秒")
        logger.info(f"   - AI 最大 Token: {self.processing.ai_max_tokens}")
        
        logger.info("="*50)
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'Config':
        """從字典創建配置實例"""
        # 暫時設置環境變數
        original_env = {}
        
        try:
            for key, value in config_dict.items():
                if key in os.environ:
                    original_env[key] = os.environ[key]
                os.environ[key] = str(value)
            
            return cls()
            
        finally:
            # 恢復原始環境變數
            for key in config_dict.keys():
                if key in original_env:
                    os.environ[key] = original_env[key]
                elif key in os.environ:
                    del os.environ[key]
    
    def to_dict(self) -> Dict[str, Any]:
        """將配置轉換為字典"""
        return {
            "notion": {
                "api_key_set": bool(self.notion.api_key),
                "database_id_set": bool(self.notion.database_id),
                "page_id": self.notion.page_id,
                "timeout": self.notion.timeout,
                "max_retries": self.notion.max_retries
            },
            "task": {
                "task_name": self.task.task_name,
                "video_url_set": bool(self.task.video_url),
                "assignee": self.task.assignee,
                "photographer": self.task.photographer
            },
            "processing": {
                "log_level": self.processing.log_level,
                "max_concurrent_tasks": self.processing.max_concurrent_tasks,
                "timeout_seconds": self.processing.timeout_seconds,
                "ai_max_tokens": self.processing.ai_max_tokens,
                "ai_temperature": self.processing.ai_temperature
            }
        }


# 便利函數
def load_config() -> Config:
    """載入並返回配置實例"""
    return Config()

def check_required_env_vars() -> Dict[str, bool]:
    """檢查必要的環境變數是否設置"""
    required_vars = {
        "ORIGINAL_LINK": bool(os.environ.get("ORIGINAL_LINK")),
        "TASK_NAME": bool(os.environ.get("TASK_NAME")),
    }
    
    optional_vars = {
        "NOTION_API_KEY": bool(os.environ.get("NOTION_API_KEY")),
        "NOTION_DATABASE_ID": bool(os.environ.get("NOTION_DATABASE_ID")),
        "PERSON_IN_CHARGE": bool(os.environ.get("PERSON_IN_CHARGE")),
        "VIDEOGRAPHER": bool(os.environ.get("VIDEOGRAPHER")),
    }
    
    return {
        "required": required_vars,
        "optional": optional_vars,
        "all_required_set": all(required_vars.values())
    }