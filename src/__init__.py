"""
影片自動化處理套件 - 初始化模組
優化版本，提供更好的模組管理和向後相容性
"""

import logging

# 設定套件日誌
logger = logging.getLogger(__name__)

# 套件資訊
__version__ = "2.0.0"
__author__ = "Video Automation Team"
__description__ = "影片自動化處理系統，整合 Notion、AI 分析和影片處理功能"

# 主要模組匯入
try:
    # 新版本模組名稱（推薦使用）
    from .notion_video_processor import NotionVideoProcessor
    from .video_processor import VideoProcessor
    from .ai_analyzer import AIAnalyzer
    from .config import Config
    
    # 向後相容性別名
    NotionHandler = NotionVideoProcessor
    
    logger.info(f"✅ 影片自動化處理套件 v{__version__} 載入成功")
    
except ImportError as e:
    logger.warning(f"⚠️ 部分模組載入失敗：{e}")
    logger.warning("請確認所有相依套件已正確安裝")

# 匯出的公開介面
__all__ = [
    # 主要類別
    'NotionVideoProcessor',
    'VideoProcessor', 
    'AIAnalyzer',
    'Config',
    
    # 向後相容性別名
    'NotionHandler',
    
    # 套件資訊
    '__version__',
    '__author__',
    '__description__'
]

# 套件配置檢查
def check_configuration():
    """檢查套件配置完整性"""
    import os
    
    config_status = {
        'notion_configured': bool(os.environ.get('NOTION_API_KEY') and os.environ.get('NOTION_DATABASE_ID')),
        'video_processor_available': True,  # 根據實際情況調整
        'ai_analyzer_available': True,      # 根據實際情況調整
    }
    
    logger.info("📊 套件配置狀態：")
    for component, status in config_status.items():
        status_icon = "✅" if status else "⚠️"
        logger.info(f"   {status_icon} {component}: {'已配置' if status else '未配置'}")
    
    return config_status

# 便利函數
def get_version():
    """取得套件版本"""
    return __version__

def get_logger(name=None):
    """取得套件日誌器"""
    if name:
        return logging.getLogger(f"{__name__}.{name}")
    return logger