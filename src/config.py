#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
短影音自動化處理系統 - 設定檔案
優化版本 v2.1
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

@dataclass
class VideoProcessingConfig:
    """影片處理設定"""
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    max_duration: int = 600  # 10分鐘
    preferred_formats: List[str] = None
    quality_preference: str = "best[height<=1080]/best[height<=720]/worst"
    
    def __post_init__(self):
        if self.preferred_formats is None:
            self.preferred_formats = ['mp4', 'webm', 'mov']

@dataclass
class AIContentConfig:
    """AI內容生成設定"""
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: int = 60
    max_retries: int = 3
    
    # AI 提示詞模板設定
    system_prompt: str = """你是專業的短影音內容策劃師和社群媒體專家，擅長創造吸引人的標題和內容建議。
你熟悉台灣本地文化和網路用語，能夠為不同類型的短影音內容提供精準的行銷建議。
請總是以JSON格式回覆，確保所有建議都符合台灣觀眾的喜好和當前的社群媒體趨勢。"""
    
    required_fields: List[str] = None
    
    def __post_init__(self):
        if self.required_fields is None:
            self.required_fields = [
                '標題建議', '內容摘要', '標籤建議', '目標受眾', 
                '內容分類', 'SEO關鍵詞', '發布建議', '創意要點'
            ]

@dataclass
class R2StorageConfig:
    """R2儲存設定"""
    bucket: str = ""
    custom_domain: str = ""
    cache_control: str = "max-age=31536000"  # 1年緩存
    
    # 檔案路徑模板
    video_path_template: str = "videos/{timestamp}/{task_id}_video{ext}"
    thumbnail_path_template: str = "thumbnails/{timestamp}/{task_id}_thumb{ext}"
    metadata_path_template: str = "metadata/{timestamp}/{task_id}_metadata.json"
    
    # 支援的內容類型
    content_types: Dict[str, str] = None
    
    def __post_init__(self):
        if self.content_types is None:
            self.content_types = {
                '.mp4': 'video/mp4',
                '.webm': 'video/webm',
                '.mov': 'video/quicktime',
                '.avi': 'video/x-msvideo',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.webp': 'image/webp'
            }

@dataclass
class WebhookConfig:
    """Webhook 設定"""
    url: str = ""
    secret: str = ""
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 2
    
    # 回調資料模板
    success_template: Dict = None
    error_template: Dict = None
    
    def __post_init__(self):
        if self.success_template is None:
            self.success_template = {
                'status': 'success',
                'task_id': '',
                'task_name': '',
                'gsheet_row_index': '',
                'processed_time': '',
                'processor_version': 'v2.1'
            }
        
        if self.error_template is None:
            self.error_template = {
                'status': 'failed',
                'task_id': '',
                'task_name': '',
                'gsheet_row_index': '',
                'error_message': '',
                'processed_time': '',
                'processor_version': 'v2.1'
            }

@dataclass
class LoggingConfig:
    """日誌設定"""
    level: str = "INFO"
    format: str = "%(asctime)s | %(levelname)s | %(message)s"
    file_name: str = "process_task.log"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    encoding: str = "utf-8"

class SystemConfig:
    """系統設定管理器"""
    
    def __init__(self):
        """初始化設定"""
        self.video_processing = VideoProcessingConfig()
        self.ai_content = AIContentConfig()
        self.r2_storage = R2StorageConfig()
        self.webhook = WebhookConfig()
        self.logging = LoggingConfig()
        
        # 從環境變數載入設定
        self.load_from_environment()
    
    def load_from_environment(self):
        """從環境變數載入設定"""
        # R2 設定
        self.r2_storage.bucket = os.getenv('R2_BUCKET', '')
        self.r2_storage.custom_domain = os.getenv('R2_CUSTOM_DOMAIN', '')
        
        # Webhook 設定
        self.webhook.url = os.getenv('N8N_WEBHOOK_URL', '')
        self.webhook.secret = os.getenv('N8N_WEBHOOK_SECRET', '')
        
        # AI 設定
        openai_model = os.getenv('OPENAI_MODEL')
        if openai_model:
            self.ai_content.model = openai_model
        
        # 影片處理設定
        max_file_size = os.getenv('MAX_FILE_SIZE')
        if max_file_size:
            try:
                self.video_processing.max_file_size = int(max_file_size)
            except ValueError:
                pass
        
        max_duration = os.getenv('MAX_DURATION')
        if max_duration:
            try:
                self.video_processing.max_duration = int(max_duration)
            except ValueError:
                pass
    
    def validate(self) -> List[str]:
        """驗證設定"""
        errors = []
        
        # 檢查必要的環境變數
        required_env_vars = [
            'VIDEO_URL', 'TASK_NAME', 'RESPONSIBLE_PERSON',
            'PHOTOGRAPHER', 'SHOOT_DATE', 'GSHEET_ROW_INDEX',
            'OPENAI_API_KEY', 'R2_ACCOUNT_ID', 'R2_ACCESS_KEY',
            'R2_SECRET_KEY', 'R2_BUCKET'
        ]
        
        for var in required_env_vars:
            if not os.getenv(var):
                errors.append(f"缺少必要環境變數: {var}")
        
        # 檢查檔案大小限制
        if self.video_processing.max_file_size <= 0:
            errors.append("max_file_size 必須大於 0")
        
        # 檢查持續時間限制
        if self.video_processing.max_duration <= 0:
            errors.append("max_duration 必須大於 0")
        
        # 檢查 AI 設定
        if self.ai_content.temperature < 0 or self.ai_content.temperature > 2:
            errors.append("AI temperature 必須在 0-2 之間")
        
        if self.ai_content.max_tokens <= 0:
            errors.append("AI max_tokens 必須大於 0")
        
        return errors
    
    def get_yt_dlp_options(self, output_path: str) -> Dict:
        """取得 yt-dlp 設定選項"""
        return {
            'format': self.video_processing.quality_preference,
            'outtmpl': f'{output_path}.%(ext)s',
            'writeinfojson': True,
            'writethumbnail': True,
            'extract_flat': False,
            'ignoreerrors': False,
            'no_warnings': False,
            'extractaudio': False,
            'embed_subs': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'max_filesize': self.video_processing.max_file_size,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            'retries': 5,
            'fragment_retries': 5,
            'skip_unavailable_fragments': True,
            'keepvideo': False,
            'format_sort': ['quality', 'res:720', 'fps'],
            'throttledratelimit': 100000,  # 100KB/s minimum
        }
    
    def get_openai_options(self) -> Dict:
        """取得 OpenAI 設定選項"""
        return {
            'model': self.ai_content.model,
            'temperature': self.ai_content.temperature,
            'max_tokens': self.ai_content.max_tokens,
            'timeout': self.ai_content.timeout,
            'top_p': 0.9,
            'frequency_penalty': 0.1,
            'presence_penalty': 0.1
        }
    
    def get_r2_upload_options(self, file_type: str, metadata: Dict = None) -> Dict:
        """取得 R2 上傳設定選項"""
        content_type = self.r2_storage.content_types.get(
            Path(file_type).suffix.lower(), 
            'application/octet-stream'
        )
        
        extra_args = {
            'ContentType': content_type,
            'CacheControl': self.r2_storage.cache_control,
        }
        
        if metadata:
            extra_args['Metadata'] = metadata
        
        return {'ExtraArgs': extra_args}
    
    def to_dict(self) -> Dict:
        """轉換為字典格式"""
        return {
            'video_processing': {
                'max_file_size': self.video_processing.max_file_size,
                'max_duration': self.video_processing.max_duration,
                'preferred_formats': self.video_processing.preferred_formats,
                'quality_preference': self.video_processing.quality_preference
            },
            'ai_content': {
                'model': self.ai_content.model,
                'temperature': self.ai_content.temperature,
                'max_tokens': self.ai_content.max_tokens,
                'timeout': self.ai_content.timeout,
                'max_retries': self.ai_content.max_retries
            },
            'r2_storage': {
                'bucket': self.r2_storage.bucket,
                'custom_domain': self.r2_storage.custom_domain,
                'cache_control': self.r2_storage.cache_control
            },
            'webhook': {
                'url': self.webhook.url,
                'timeout': self.webhook.timeout,
                'max_retries': self.webhook.max_retries
            },
            'logging': {
                'level': self.logging.level,
                'file_name': self.logging.file_name,
                'max_file_size': self.logging.max_file_size
            }
        }

# 全域設定實例
config = SystemConfig()

# 常用設定常數
class Constants:
    """系統常數"""
    
    # 版本資訊
    VERSION = "v2.1"
    PROCESSOR_NAME = "短影音自動化處理系統"
    
    # 支援的影片格式
    SUPPORTED_VIDEO_FORMATS = ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv']
    
    # 支援的圖片格式
    SUPPORTED_IMAGE_FORMATS = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
    
    # 檔案大小限制 (位元組)
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    MIN_FILE_SIZE = 1024  # 1KB
    
    # 時間限制 (秒)
    MAX_DURATION = 600  # 10分鐘
    MIN_DURATION = 1  # 1秒
    
    # AI 內容生成限制
    MAX_TITLE_COUNT = 10
    MAX_TAG_COUNT = 20
    MAX_KEYWORD_COUNT = 10
    
    # 重試設定
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 2
    
    # 日誌等級
    LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    
    # 平台清單
    SUPPORTED_PLATFORMS = [
        'YouTube', 'YouTube Shorts', 'Instagram', 'Instagram Reels',
        'TikTok', 'Facebook', 'Twitter', 'LinkedIn', 'Pinterest'
    ]
    
    # 內容分類
    CONTENT_CATEGORIES = [
        '娛樂', '教育', '科技', '生活', '美食', '旅遊', '運動',
        '音樂', '遊戲', '新聞', '商業', '藝術', '時尚', '健康'
    ]
    
    # 發布時段建議
    OPTIMAL_PUBLISH_TIMES = {
        '平日早晨': '07:00-09:00',
        '平日午休': '12:00-13:00',
        '平日晚間': '18:00-22:00',
        '週末上午': '10:00-12:00',
        '週末下午': '14:00-17:00',
        '週末晚間': '19:00-23:00'
    }
    
    # 熱門標籤範本
    POPULAR_TAGS_TEMPLATES = [
        '#短影音', '#必看', '#熱門', '#推薦', '#精彩',
        '#台灣', '#創意', '#有趣', '#實用', '#分享',
        '#trending', '#viral', '#fyp', '#explore', '#reels'
    ]

class ErrorMessages:
    """錯誤訊息常數"""
    
    # 環境設定錯誤
    MISSING_ENV_VAR = "缺少必要環境變數: {var}"
    INVALID_ENV_VAR = "環境變數格式錯誤: {var}={value}"
    
    # 檔案處理錯誤
    FILE_NOT_FOUND = "找不到檔案: {file_path}"
    FILE_TOO_LARGE = "檔案過大: {size}MB，超過限制 {limit}MB"
    FILE_TOO_SMALL = "檔案過小: {size}KB，低於最小限制 {limit}KB"
    UNSUPPORTED_FORMAT = "不支援的檔案格式: {format}"
    
    # 網路相關錯誤
    DOWNLOAD_FAILED = "影片下載失敗: {url}"
    UPLOAD_FAILED = "檔案上傳失敗: {destination}"
    NETWORK_TIMEOUT = "網路請求逾時: {url}"
    API_ERROR = "API 請求失敗: {service} - {error}"
    
    # AI 相關錯誤
    AI_GENERATION_FAILED = "AI 內容生成失敗: {error}"
    AI_RESPONSE_INVALID = "AI 回應格式無效: {response}"
    AI_QUOTA_EXCEEDED = "AI API 配額已用完"
    
    # R2 儲存錯誤
    R2_CONNECTION_FAILED = "R2 連接失敗: {error}"
    R2_PERMISSION_DENIED = "R2 權限不足: {operation}"
    R2_BUCKET_NOT_FOUND = "R2 儲存桶不存在: {bucket}"
    
    # Webhook 錯誤
    WEBHOOK_FAILED = "Webhook 發送失敗: {url} - {error}"
    WEBHOOK_TIMEOUT = "Webhook 請求逾時: {url}"

class SuccessMessages:
    """成功訊息常數"""
    
    INIT_SUCCESS = "🚀 {component} 初始化成功"
    DOWNLOAD_SUCCESS = "✅ 影片下載完成: {file_path}"
    UPLOAD_SUCCESS = "✅ 檔案上傳完成: {destination}"
    AI_GENERATION_SUCCESS = "✅ AI 內容生成完成"
    TASK_COMPLETED = "🎉 任務處理完成: {task_id}"
    WEBHOOK_SUCCESS = "✅ Webhook 回調發送成功"
    CLEANUP_SUCCESS = "🧹 臨時檔案清理完成"

# 匯出主要設定物件
__all__ = [
    'SystemConfig', 'config', 'Constants', 
    'ErrorMessages', 'SuccessMessages',
    'VideoProcessingConfig', 'AIContentConfig', 
    'R2StorageConfig', 'WebhookConfig', 'LoggingConfig'
]