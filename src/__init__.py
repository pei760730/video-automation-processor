"""
src 模組初始化檔案
確保 Python 能正確識別這個目錄為一個模組
"""

# 可以在這裡匯出常用的類別，方便其他模組使用
from .notion_handler import NotionHandler
from .notion_video_processor import NotionVideoProcessor
from .video_processor import VideoProcessor
from .ai_analyzer import AIAnalyzer
from .config import Config

__all__ = [
    'NotionHandler',
    'NotionVideoProcessor',
    'VideoProcessor',
    'AIAnalyzer',
    'Config'
]

# 版本資訊
__version__ = '1.0.0'