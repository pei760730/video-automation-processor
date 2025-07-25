# 檔案路徑: src/notion_video_processor.py

import os
import sys
import json
import tempfile
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

import yt_dlp
import boto3
from openai import OpenAI
from botocore.exceptions import ClientError
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

# --- 直接對應 Notion 欄位的資料結構 ---
@dataclass
class NotionTask:
    """
    直接映射 Notion "Video Pipeline" 資料庫的資料結構。
    """
    # === 輸入欄位 (來自 Notion / 環境變數) ===
    notion_page_id: str         # 用來更新 Notion 特定頁面的 ID
    task_name: str              # 對應 Notion 的「任務名稱」
    person_in_charge: str       # 對應 Notion 的「負責人」
    videographer: str           # 對應 Notion 的「攝影師」
    original_link: str          # 對應 Notion 的「原始連結」
    
    # === 處理中/輸出欄位 (由程式生成) ===
    status: str = "處理中"      # 對應 Notion 的「狀態」
    
    # 儲存到 R2 的結果連結
    processed_video_url: Optional[str] = None
    processed_thumbnail_url: Optional[str] = None
    
    # AI 生成的內容，對應 Notion 欄位
    ai_title_suggestions: List[str] = field(default_factory=list) # 對應「AI標題建議」
    ai_content_summary: Optional[str] = None                      # 對應「內容摘要」
    ai_tag_suggestions: List[str] = field(default_factory=list)   # 對應「標籤建議」

    # 處理過程中的內部資訊
    task_id: str = ""           # 本次處理的唯一 ID，用於命名檔案
    error_message: Optional[str] = None # 如果失敗，記錄錯誤訊息

    def __post_init__(self):
        """在初始化後，生成唯一的 task_id"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hash_input = f"{self.original_link}_{timestamp}"
        hash_suffix = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        self.task_id = f"task_{timestamp}_{hash_suffix}"

# --- 日誌設定 (保持不變) ---
logger = structlog.get_logger(__name__)

# --- 核心處理器 ---
class NotionVideoProcessor:
    """
    為 Notion Video Pipeline 設計的影片處理器
    """
    def __init__(self):
        """初始化，讀取環境變數並設定客戶端"""
        self.temp_dir = tempfile.mkdtemp(prefix='video_pipeline_')
        self._setup_task_from_env()
        self._setup_clients()
        logger.info("Notion 影片處理器初始化完成", task_id=self.task.task_id, temp_dir=self.temp_dir)

    def _setup_task_from_env(self):
        """從環境變數讀取資訊，建立 NotionTask 物件"""
        required_vars = [
            'NOTION_PAGE_ID', 'TASK_NAME', 'PERSON_IN_CHARGE',
            'VIDEOGRAPHER', 'ORIGINAL_LINK'
        ]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"缺少必要的環境變數: {', '.join(missing_vars)}")
        
        self.task = NotionTask(
            notion_page_id=os.getenv('NOTION_PAGE_ID'),
            task_name=os.getenv('TASK_NAME'),
            person_in_charge=os.getenv('PERSON_IN_CHARGE'),
            videographer=os.getenv('VIDEOGRAPHER'),
            original_link=os.getenv('ORIGINAL_LINK')
        )
        logger.info("任務資料載入成功", task_name=self.task.task_name)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _setup_clients(self):
        """設定 OpenAI 和 R2 客戶端"""
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'), timeout=60.0)
        self.r2_client = boto3.client(
            's3',
            endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
            aws_access_key_id=os.getenv('R2_ACCESS_KEY'),
            aws_secret_access_key=os.getenv('R2_SECRET_KEY'),
            region_name='auto'
        )
        logger.info("外部服務客戶端設定完成")

    def _download_video(self) -> Tuple[str, Optional[str]]:
        """下載影片和縮圖，返回檔案路徑"""
        logger.info("開始下載影片", url=self.task.original_link)
        output_path = os.path.join(self.temp_dir, f"{self.task.task_id}_video")
        ydl_opts = {'format': 'best[height<=1080]/best', 'outtmpl': f'{output_path}.%(ext)s', 'writethumbnail': True}
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([self.task.original_link])
        
        # 尋找下載的檔案
        video_files = list(Path(self.temp_dir).glob(f"{self.task.task_id}_video.*"))
        video_file = next((str(f) for f in video_files if f.suffix not in ['.webp', '.jpg', '.png']), None)
        thumbnail_file = next((str(f) for f in video_files if f.suffix in ['.webp', '.jpg', '.png']), None)
        
        if not video_file:
            raise FileNotFoundError("影片下載失敗或找不到檔案")
        
        logger.info("影片下載完成", video_file=Path(video_file).name)
        return video_file, thumbnail_file

    def _upload_to_r2(self, local_path: str, file_type: str) -> str:
        """上傳單一檔案到 R2，返回公開 URL"""
        bucket = os.getenv('R2_BUCKET')
        timestamp_path = datetime.now().strftime("%Y/%m/%d")
        r2_key = f"{file_type}/{timestamp_path}/{self.task.task_id}{Path(local_path).suffix}"
        
        content_type_map = {'.mp4': 'video/mp4', '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
        content_type = content_type_map.get(Path(local_path).suffix, 'application/octet-stream')
        
        self.r2_client.upload_file(local_path, bucket, r2_key, ExtraArgs={'ContentType': content_type})
        
        # 組成公開 URL
        r2_public_domain = os.getenv('R2_CUSTOM_DOMAIN', f"pub-{os.getenv('R2_ACCOUNT_ID')}.r2.dev")
        url = f"https://{r2_public_domain}/{r2_key}"
        logger.info(f"{file_type} 上傳完成", url=url)
        return url

    def _generate_ai_content(self):
        """呼叫 AI 生成內容，並更新 task 物件"""
        logger.info("開始生成 AI 內容")
        prompt = f"""
        請分析以下影片任務，並以台灣社群媒體風格提供內容建議。
        任務名稱: {self.task.task_name}
        
        請嚴格按照以下 JSON 格式回覆，不要有任何額外的文字或解釋：
        {{
          "AI標題建議": ["吸引人的標題1", "有趣的標題2", "病毒式標題3"],
          "內容摘要": "一段約50-100字的影片內容摘要，要能引起觀看興趣。",
          "標籤建議": ["#相關標籤1", "#熱門標籤2", "#台灣", "#fyp"]
        }}
        """
        response = self.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "你是一位台灣短影音行銷專家，擅長創造吸引人的標題、摘要和標籤。"},
                {"role": "user", "content": prompt}
            ]
        )
        try:
            ai_data = json.loads(response.choices[0].message.content)
            self.task.ai_title_suggestions = ai_data.get("AI標題建議", [])
            self.task.ai_content_summary = ai_data.get("內容摘要", "")
            self.task.ai_tag_suggestions = ai_data.get("標籤建議", [])
            logger.info("AI 內容生成成功")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("AI 回應解析失敗", error=str(e))
            self.task.error_message = "AI 回應格式錯誤" # 記錄錯誤

    def _cleanup(self):
        """清理臨時資料夾"""
        import shutil
        shutil.rmtree(self.temp_dir)
        logger.info("臨時檔案清理完成")

    def process(self) -> Dict[str, Any]:
        """執行完整的處理流程"""
        try:
            # 1. 下載
            video_path, thumb_path = self._download_video()
            
            # 2. 上傳
            self.task.processed_video_url = self._upload_to_r2(video_path, "videos")
            if thumb_path:
                self.task.processed_thumbnail_url = self._upload_to_r2(thumb_path, "thumbnails")
            
            # 3. AI 分析
            self._generate_ai_content()
            
            # 4. 更新最終狀態
            if not self.task.error_message: # 如果AI步驟沒有出錯
                self.task.status = "完成"

        except Exception as e:
            logger.error("處理過程中發生錯誤", error=str(e), exc_info=True)
            self.task.status = "失敗"
            self.task.error_message = str(e)
        
        finally:
            self._cleanup()
            logger.info("任務處理結束", status=self.task.status)
            return asdict(self.task) # 回傳處理結果