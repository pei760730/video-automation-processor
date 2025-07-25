# src/__init__.py

# 這是一個空檔案，讓 Python 認識這是一個 package

# 將常用的 class 或變數提升到 package 層級，方便外部匯入
from .config import config
from .ai_analyzer import AIAnalyzer
from .video_processor import VideoProcessor
# ... 其他您想提升的項目