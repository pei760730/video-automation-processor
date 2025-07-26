"""
影片自動化處理套件 - 初始化模組
優化版本：清理和整合所有模組
"""

import logging

# 設定套件日誌
logger = logging.getLogger(__name__)

# 套件資訊
__version__ = "2.1.0"
__author__ = "Video Automation Team"
__description__ = "影片自動化處理系統，整合 Notion、AI 分析和影片處理功能"

# 主要模組匯入
try:
    # 核心處理器（主要使用）
    from .notion_video_processor import NotionVideoProcessor
    
    # 輔助模組（如果存在）
    try:
        from .config import Config
    except ImportError:
        logger.debug("Config 模組未找到，跳過載入")
        Config = None
    
    try:
        from .ai_analyzer import AIAnalyzer
    except ImportError:
        logger.debug("AIAnalyzer 模組未找到，跳過載入")
        AIAnalyzer = None
    
    # 向後相容性別名
    NotionHandler = NotionVideoProcessor
    VideoProcessor = NotionVideoProcessor  # 統一使用 NotionVideoProcessor
    
    logger.info(f"✅ 影片自動化處理套件 v{__version__} 載入成功")
    
except ImportError as e:
    logger.warning(f"⚠️ 部分模組載入失敗：{e}")
    logger.warning("請確認所有相依套件已正確安裝")
    
    # 創建替代類別以防止程式崩潰
    class NotionVideoProcessor:
        def __init__(self):
            logger.error("❌ NotionVideoProcessor 模組載入失敗")
            raise ImportError("無法載入 NotionVideoProcessor")
    
    NotionHandler = NotionVideoProcessor
    VideoProcessor = NotionVideoProcessor
    Config = None
    AIAnalyzer = None

# 匯出的公開介面
__all__ = [
    # 主要類別
    'NotionVideoProcessor',
    
    # 向後相容性別名
    'NotionHandler',
    'VideoProcessor',
    
    # 輔助類別（如果可用）
    'Config',
    'AIAnalyzer',
    
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
        'openai_configured': bool(os.environ.get('OPENAI_API_KEY')),
        'notion_configured': bool(os.environ.get('NOTION_API_KEY') and os.environ.get('NOTION_DATABASE_ID')),
        'r2_configured': bool(
            os.environ.get('R2_ACCOUNT_ID') and 
            os.environ.get('R2_ACCESS_KEY') and 
            os.environ.get('R2_SECRET_KEY') and 
            os.environ.get('R2_BUCKET')
        ),
        'core_vars_configured': bool(
            os.environ.get('NOTION_PAGE_ID') and
            os.environ.get('TASK_NAME') and
            os.environ.get('ORIGINAL_LINK')
        )
    }
    
    logger.info("📊 套件配置狀態：")
    status_messages = {
        'core_vars_configured': '核心變數',
        'openai_configured': 'OpenAI API',
        'notion_configured': 'Notion 整合',
        'r2_configured': 'R2 雲端儲存'
    }
    
    for component, status in config_status.items():
        status_icon = "✅" if status else "⚠️"
        message = status_messages.get(component, component)
        logger.info(f"   {status_icon} {message}: {'已配置' if status else '未配置'}")
    
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

def validate_environment():
    """快速驗證環境配置"""
    import os
    
    required_vars = ['NOTION_PAGE_ID', 'TASK_NAME', 'ORIGINAL_LINK', 'OPENAI_API_KEY']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        logger.error(f"❌ 缺少必要環境變數: {', '.join(missing_vars)}")
        return False
    
    logger.info("✅ 基本環境變數驗證通過")
    return True