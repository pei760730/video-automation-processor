# 檔案路徑: src/notion_video_processor.py

import os
import sys
import json
import tempfile
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

import yt_dlp
import boto3
from openai import OpenAI
from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential

# 設定日誌
logger = logging.getLogger(__name__)

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

# --- 核心處理器 ---
class NotionVideoProcessor:
    """
    為 Notion Video Pipeline 設計的影片處理器 - 生產版本
    """
    def __init__(self):
        """初始化，讀取環境變數並設定客戶端"""
        self.temp_dir = tempfile.mkdtemp(prefix='video_pipeline_')
        self._setup_task_from_env()
        self._setup_clients()
        logger.info(f"✅ Notion 影片處理器初始化完成 - Task ID: {self.task.task_id}")

    def _setup_task_from_env(self):
        """從環境變數讀取資訊，建立 NotionTask 物件"""
        required_vars = [
            'NOTION_PAGE_ID', 'TASK_NAME', 'PERSON_IN_CHARGE',
            'VIDEOGRAPHER', 'ORIGINAL_LINK'
        ]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"❌ 缺少必要的環境變數: {', '.join(missing_vars)}")
        
        self.task = NotionTask(
            notion_page_id=os.getenv('NOTION_PAGE_ID'),
            task_name=os.getenv('TASK_NAME'),
            person_in_charge=os.getenv('PERSON_IN_CHARGE'),
            videographer=os.getenv('VIDEOGRAPHER'),
            original_link=os.getenv('ORIGINAL_LINK')
        )
        logger.info(f"📋 任務資料載入成功 - {self.task.task_name}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _setup_clients(self):
        """設定 OpenAI 和 R2 客戶端"""
        # 檢查 OpenAI API Key
        openai_key = os.getenv('OPENAI_API_KEY')
        if not openai_key:
            raise ValueError("❌ 缺少 OPENAI_API_KEY 環境變數")
        
        try:
            self.openai_client = OpenAI(api_key=openai_key, timeout=60.0)
            logger.info("✅ OpenAI 客戶端初始化成功")
        except Exception as e:
            raise ValueError(f"❌ OpenAI 客戶端初始化失敗: {e}")
        
        # 檢查 R2 配置
        r2_config = {
            'account_id': os.getenv('R2_ACCOUNT_ID'),
            'access_key': os.getenv('R2_ACCESS_KEY'),
            'secret_key': os.getenv('R2_SECRET_KEY'),
            'bucket': os.getenv('R2_BUCKET')
        }
        
        missing_r2 = [k for k, v in r2_config.items() if not v]
        if missing_r2:
            logger.warning(f"⚠️ R2 配置不完整，缺少: {', '.join(missing_r2)}")
            logger.warning("📁 檔案將保存在本地，不會上傳到雲端")
            self.r2_client = None
            self.r2_enabled = False
        else:
            try:
                self.r2_client = boto3.client(
                    's3',
                    endpoint_url=f"https://{r2_config['account_id']}.r2.cloudflarestorage.com",
                    aws_access_key_id=r2_config['access_key'],
                    aws_secret_access_key=r2_config['secret_key'],
                    region_name='auto'
                )
                self.r2_enabled = True
                logger.info("✅ R2 客戶端初始化成功")
            except Exception as e:
                logger.error(f"❌ R2 客戶端初始化失敗: {e}")
                self.r2_client = None
                self.r2_enabled = False

    def _download_video(self) -> Tuple[str, Optional[str]]:
        """下載影片和縮圖，返回檔案路徑"""
        logger.info(f"📥 開始下載影片: {self.task.original_link}")
        output_path = os.path.join(self.temp_dir, f"{self.task.task_id}_video")
        
        ydl_opts = {
            'format': 'best[height<=1080]/best', 
            'outtmpl': f'{output_path}.%(ext)s', 
            'writethumbnail': True,
            'writeinfojson': False,
            'writesubtitles': False,
            'quiet': False,
            'no_warnings': False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.task.original_link, download=True)
                logger.info(f"📺 影片資訊: {info.get('title', 'Unknown')} - {info.get('duration', 'Unknown')}秒")
        except Exception as e:
            logger.error(f"❌ 影片下載失敗: {e}")
            raise RuntimeError(f"影片下載失敗: {str(e)}")
        
        # 尋找下載的檔案
        video_files = list(Path(self.temp_dir).glob(f"{self.task.task_id}_video.*"))
        video_file = next((str(f) for f in video_files if f.suffix not in ['.webp', '.jpg', '.png']), None)
        thumbnail_file = next((str(f) for f in video_files if f.suffix in ['.webp', '.jpg', '.png']), None)
        
        if not video_file:
            raise FileNotFoundError("❌ 影片檔案未找到，下載可能失敗")
        
        video_size = os.path.getsize(video_file) / (1024 * 1024)  # MB
        logger.info(f"✅ 影片下載完成: {Path(video_file).name} ({video_size:.1f}MB)")
        if thumbnail_file:
            logger.info(f"🖼️ 縮圖下載完成: {Path(thumbnail_file).name}")
        
        return video_file, thumbnail_file

    def _upload_to_r2(self, local_path: str, file_type: str) -> str:
        """上傳單一檔案到 R2，返回公開 URL"""
        if not self.r2_enabled:
            logger.info(f"💾 {file_type} 保存在本地: {local_path}")
            return f"local://{local_path}"
        
        bucket = os.getenv('R2_BUCKET')
        timestamp_path = datetime.now().strftime("%Y/%m/%d")
        file_ext = Path(local_path).suffix
        r2_key = f"{file_type}/{timestamp_path}/{self.task.task_id}{file_ext}"
        
        content_type_map = {
            '.mp4': 'video/mp4', 
            '.webm': 'video/webm',
            '.jpg': 'image/jpeg', 
            '.jpeg': 'image/jpeg',
            '.png': 'image/png', 
            '.webp': 'image/webp'
        }
        content_type = content_type_map.get(file_ext.lower(), 'application/octet-stream')
        
        try:
            file_size = os.path.getsize(local_path) / (1024 * 1024)  # MB
            logger.info(f"☁️ 開始上傳 {file_type}: {Path(local_path).name} ({file_size:.1f}MB)")
            
            self.r2_client.upload_file(
                local_path, 
                bucket, 
                r2_key, 
                ExtraArgs={
                    'ContentType': content_type,
                    'CacheControl': 'public, max-age=31536000',  # 1年快取
                }
            )
            
            # 組成公開 URL
            r2_public_domain = os.getenv('R2_CUSTOM_DOMAIN')
            if r2_public_domain:
                url = f"https://{r2_public_domain}/{r2_key}"
            else:
                url = f"https://pub-{os.getenv('R2_ACCOUNT_ID')}.r2.dev/{r2_key}"
            
            logger.info(f"✅ {file_type} 上傳完成: {url}")
            return url
            
        except Exception as e:
            logger.error(f"❌ {file_type} 上傳失敗: {e}")
            return f"upload_failed://{local_path}"

    def _generate_ai_content(self):
        """呼叫 AI 生成內容，並更新 task 物件"""
        logger.info("🤖 開始 AI 內容生成...")
        
        prompt = f"""
        請分析以下影片任務，並以台灣社群媒體風格提供內容建議。
        
        任務資訊：
        - 任務名稱: {self.task.task_name}
        - 負責人: {self.task.person_in_charge}
        - 攝影師: {self.task.videographer}
        
        請嚴格按照以下 JSON 格式回覆，不要有任何額外的文字或解釋：
        {{
          "AI標題建議": ["吸引人的標題1", "有趣的標題2", "病毒式標題3", "創意標題4", "熱門標題5"],
          "內容摘要": "一段約80-120字的影片內容摘要，要能引起觀看興趣，突出影片亮點。",
          "標籤建議": ["#相關標籤1", "#熱門標籤2", "#台灣", "#影片", "#創作", "#生活", "#有趣", "#推薦"]
        }}
        
        請確保標題具有吸引力且適合台灣觀眾，標籤要包含相關且熱門的關鍵字。
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system", 
                        "content": "你是一位專業的台灣短影音行銷專家，擅長創造吸引人的標題、摘要和標籤。你了解台灣網路文化和流行趨勢。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=1500,
                top_p=0.9
            )
            
            ai_content = response.choices[0].message.content
            logger.info(f"🤖 AI 原始回應長度: {len(ai_content)} 字元")
            
            ai_data = json.loads(ai_content)
            
            # 驗證和清理 AI 回應
            self.task.ai_title_suggestions = ai_data.get("AI標題建議", [])[:5]  # 最多5個標題
            self.task.ai_content_summary = ai_data.get("內容摘要", "")[:500]    # 限制摘要長度
            self.task.ai_tag_suggestions = ai_data.get("標籤建議", [])[:10]     # 最多10個標籤
            
            # 記錄生成結果
            logger.info(f"✅ AI 內容生成成功:")
            logger.info(f"   📝 標題數量: {len(self.task.ai_title_suggestions)}")
            logger.info(f"   📄 摘要長度: {len(self.task.ai_content_summary)} 字元")
            logger.info(f"   🏷️ 標籤數量: {len(self.task.ai_tag_suggestions)}")
            
            # 顯示生成的內容
            if self.task.ai_title_suggestions:
                logger.info("💡 建議標題:")
                for i, title in enumerate(self.task.ai_title_suggestions, 1):
                    logger.info(f"   {i}. {title}")
            
            if self.task.ai_tag_suggestions:
                logger.info(f"🏷️ 建議標籤: {' '.join(self.task.ai_tag_suggestions)}")
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ AI 回應 JSON 解析失敗: {e}")
            logger.error(f"原始回應: {ai_content[:200]}...")
            self.task.error_message = "AI 回應格式錯誤"
        except Exception as e:
            logger.error(f"❌ AI 內容生成失敗: {e}")
            self.task.error_message = f"AI 服務錯誤: {str(e)}"

    def _cleanup(self):
        """清理臨時資料夾"""
        try:
            import shutil
            shutil.rmtree(self.temp_dir)
            logger.info("🧹 臨時檔案清理完成")
        except Exception as e:
            logger.warning(f"⚠️ 臨時檔案清理失敗: {e}")

    def process(self) -> Dict[str, Any]:
        """執行完整的處理流程"""
        start_time = datetime.now()
        logger.info("="*60)
        logger.info(f"🚀 開始執行影片處理流程")
        logger.info(f"📋 任務 ID: {self.task.task_id}")
        logger.info(f"🎬 任務名稱: {self.task.task_name}")
        logger.info("="*60)
        
        try:
            # 步驟 1: 下載影片和縮圖
            logger.info("📥 步驟 1/3: 下載影片")
            video_path, thumb_path = self._download_video()
            
            # 步驟 2: 上傳到 R2（如果啟用）
            logger.info("☁️ 步驟 2/3: 上傳檔案")
            self.task.processed_video_url = self._upload_to_r2(video_path, "videos")
            if thumb_path:
                self.task.processed_thumbnail_url = self._upload_to_r2(thumb_path, "thumbnails")
            
            # 步驟 3: AI 分析
            logger.info("🤖 步驟 3/3: AI 內容生成")
            self._generate_ai_content()
            
            # 更新最終狀態
            if not self.task.error_message:
                self.task.status = "完成"
                logger.info("🎉 影片處理流程完全成功")
            else:
                self.task.status = "部分完成"
                logger.warning(f"⚠️ 處理完成但有錯誤: {self.task.error_message}")

        except Exception as e:
            logger.error("❌ 處理過程中發生致命錯誤")
            logger.error(f"錯誤詳情: {str(e)}")
            logger.error(f"錯誤類型: {type(e).__name__}")
            
            self.task.status = "失敗"
            self.task.error_message = str(e)
        
        finally:
            # 計算處理時間
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # 清理臨時檔案
            self._cleanup()
            
            # 輸出最終結果
            logger.info("="*60)
            logger.info("📊 處理結果摘要")
            logger.info("="*60)
            logger.info(f"⏱️ 總處理時間: {duration:.1f} 秒")
            logger.info(f"📄 任務 ID: {self.task.task_id}")
            logger.info(f"✅ 最終狀態: {self.task.status}")
            
            if self.task.processed_video_url:
                logger.info(f"🎥 影片連結: {self.task.processed_video_url}")
            if self.task.processed_thumbnail_url:
                logger.info(f"🖼️ 縮圖連結: {self.task.processed_thumbnail_url}")
            
            logger.info("="*60)
            
            return asdict(self.task)