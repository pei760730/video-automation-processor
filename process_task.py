#!/usr/bin/env python3
# process_task.py - 短影音處理核心引擎 (完整功能版)

import os
import sys
import json
import subprocess
import tempfile
import shutil
import requests
import boto3
import logging
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("processing.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self):
        """初始化處理器，從環境變數獲取配置"""
        # === API 與服務金鑰 ===
        self.r2_account_id = self._get_required_env('R2_ACCOUNT_ID')
        self.r2_access_key = self._get_required_env('R2_ACCESS_KEY')
        self.r2_secret_key = self._get_required_env('R2_SECRET_KEY')
        self.r2_bucket = os.getenv('R2_BUCKET', 'video-automation')
        self.openai_api_key = self._get_required_env('OPENAI_API_KEY')
        self.webhook_url = self._get_required_env('N8N_WEBHOOK_URL')
        self.webhook_secret = self._get_required_env('N8N_WEBHOOK_SECRET')

        # === 任務參數 ===
        self.video_url = self._get_required_env('VIDEO_URL')
        self.task_name = self._get_required_env('TASK_NAME')
        self.assignee = os.getenv('ASSIGNEE', '')
        self.photographer = os.getenv('PHOTOGRAPHER', '')
        self.shoot_date = os.getenv('SHOOT_DATE') or datetime.now().strftime('%Y-%m-%d')
        self.notes = os.getenv('NOTES', '')
        self.row_index = self._get_required_env('GSHEET_ROW_INDEX')
        
        # === 生成任務 ID ===
        self.task_id = self._generate_task_id()
        
        # === 初始化 OpenAI 客戶端 ===
        try:
            import openai
            self.openai_client = openai.OpenAI(api_key=self.openai_api_key)
        except ImportError:
            logger.error("需要安裝 openai 套件: pip install openai")
            sys.exit(1)
        
        # === 初始化 R2 客戶端 ===
        self.r2_client = boto3.client(
            's3',
            endpoint_url=f'https://{self.r2_account_id}.r2.cloudflarestorage.com',
            aws_access_key_id=self.r2_access_key,
            aws_secret_access_key=self.r2_secret_key,
            region_name='auto'
        )
        
        logger.info(f"🎬 開始處理任務: {self.task_name} (ID: {self.task_id})")
        logger.info(f"📹 影片連結: {self.video_url}")
        
    def _get_required_env(self, key: str) -> str:
        """取得必要的環境變數，如果不存在則拋出異常"""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"必要環境變數 {key} 未設置")
        return value
        
    def _generate_task_id(self) -> str:
        """生成唯一的任務 ID"""
        combined = f"{self.task_name}_{self.video_url}_{datetime.now().isoformat()}"
        return hashlib.md5(combined.encode()).hexdigest()[:12]
        
    def _sanitize_filename(self, filename: str) -> str:
        """清理檔案名稱，移除不安全字符"""
        import re
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
        safe_name = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', safe_name)
        return safe_name[:100]
        
    def create_temp_directory(self):
        """創建臨時工作目錄"""
        self.temp_dir = tempfile.mkdtemp(prefix=f'video_processor_{self.task_id}_')
        logger.info(f"📁 創建臨時目錄: {self.temp_dir}")
        return self.temp_dir
        
    def download_video(self) -> bool:
        """使用 yt-dlp 下載影片和縮圖"""
        try:
            safe_name = self._sanitize_filename(self.task_name)
            
            # yt-dlp 指令
            cmd = [
                'yt-dlp',
                '--format', 'bestvideo[height<=720]+bestaudio/best[height<=720]',
                '--merge-output-format', 'mp4',
                '--write-thumbnail',
                '--write-info-json',
                '--no-playlist',
                '--extractor-retries', '3',
                '--output', f'{self.temp_dir}/{safe_name}.%(ext)s',
                '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                self.video_url
            ]
            
            logger.info(f"🔽 執行下載指令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                logger.error(f"yt-dlp stderr: {result.stderr}")
                raise Exception(f"yt-dlp 下載失敗 (exit code: {result.returncode})")
                
            # 查找下載的檔案
            files = list(Path(self.temp_dir).glob('*'))
            logger.info(f"下載目錄包含檔案: {[f.name for f in files]}")
            
            self.video_file = None
            self.thumbnail_file = None
            self.info_file = None
            
            for file in files:
                if file.suffix.lower() in ['.mp4', '.webm', '.mkv'] and 'info' not in file.name.lower():
                    self.video_file = file
                elif 'thumb' in file.name.lower() and file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
                    self.thumbnail_file = file
                elif file.suffix == '.json' and 'info' in file.name.lower():
                    self.info_file = file

            if not self.video_file:
                raise Exception(f"找不到影片檔案。可用檔案: {[f.name for f in files]}")
            
            if not self.thumbnail_file:
                logger.warning("找不到縮圖檔案，將嘗試從影片生成")
                self._generate_thumbnail_from_video()
                
            # 讀取影片資訊
            if self.info_file:
                with open(self.info_file, 'r', encoding='utf-8') as f:
                    self.video_info = json.load(f)
            else:
                logger.warning("找不到 info.json，使用預設影片資訊")
                self.video_info = {
                    'title': self.task_name,
                    'duration': 'Unknown',
                    'extractor': 'Unknown'
                }
                
            logger.info("✅ 下載完成:")
            logger.info(f"   影片: {self.video_file.name} ({self._get_file_size(self.video_file)})")
            if self.thumbnail_file:
                logger.info(f"   縮圖: {self.thumbnail_file.name}")
            logger.info(f"   時長: {self.video_info.get('duration', 'N/A')} 秒")
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("❌ 下載超時 (10分鐘)")
            return False
        except Exception as e:
            logger.error(f"❌ 下載失敗: {str(e)}", exc_info=True)
            return False
            
    def _generate_thumbnail_from_video(self):
        """從影片中生成縮圖"""
        try:
            if not self.video_file:
                return
                
            thumbnail_path = Path(self.temp_dir) / f"{self.task_id}_thumb.jpg"
            cmd = [
                'ffmpeg', '-i', str(self.video_file),
                '-ss', '00:00:01',
                '-vframes', '1',
                '-q:v', '2',
                str(thumbnail_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and thumbnail_path.exists():
                self.thumbnail_file = thumbnail_path
                logger.info("✅ 成功從影片生成縮圖")
            else:
                logger.warning("⚠️ 無法生成縮圖")
                
        except Exception as e:
            logger.warning(f"⚠️ 縮圖生成失敗: {str(e)}")
            
    def _get_file_size(self, file_path: Path) -> str:
        """取得檔案大小的可讀格式"""
        size = file_path.stat().st_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    def upload_to_r2(self) -> bool:
        """上傳檔案到 Cloudflare R2"""
        try:
            # 構建 R2 路徑
            date_str = self.shoot_date
            base_path = f"videos/{date_str}/{self._sanitize_filename(self.task_name)}_{self.task_id}"
            
            # 上傳影片
            video_key = f"{base_path}/video{self.video_file.suffix}"
            self._upload_file_to_r2(self.video_file, video_key, 'video/mp4')
            
            # 上傳縮圖 (如果存在)
            thumbnail_key = None
            if self.thumbnail_file:
                thumbnail_key = f"{base_path}/thumbnail{self.thumbnail_file.suffix}"
                self._upload_file_to_r2(self.thumbnail_file, thumbnail_key, 'image/jpeg')
                
            # 上傳元數據
            metadata_key = f"{base_path}/metadata.json"
            metadata = {
                'task_id': self.task_id,
                'task_name': self.task_name,
                'video_url': self.video_url,
                'assignee': self.assignee,
                'photographer': self.photographer,
                'upload_time': datetime.now().isoformat(),
                'video_info': self.video_info,
                'file_sizes': {
                    'video': self._get_file_size(self.video_file),
                    'thumbnail': self._get_file_size(self.thumbnail_file) if self.thumbnail_file else None
                }
            }
            
            self.r2_client.put_object(
                Bucket=self.r2_bucket,
                Key=metadata_key,
                Body=json.dumps(metadata, ensure_ascii=False, indent=2),
                ContentType='application/json'
            )
            
            # 生成公開 URL
            custom_domain = os.getenv('R2_CUSTOM_DOMAIN')
            if custom_domain:
                base_url = f"https://{custom_domain}"
            else:
                base_url = f"https://{self.r2_bucket}.{self.r2_account_id}.r2.cloudflarestorage.com"
                
            self.video_url_r2 = f"{base_url}/{video_key}"
            self.thumbnail_url_r2 = f"{base_url}/{thumbnail_key}" if thumbnail_key else None
            self.r2_path = base_path
            
            logger.info(f"✅ 上傳到 R2 完成: {base_path}")
            logger.info(f"   影片 URL: {self.video_url_r2}")
            if self.thumbnail_url_r2:
                logger.info(f"   縮圖 URL: {self.thumbnail_url_r2}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ R2 上傳失敗: {str(e)}", exc_info=True)
            return False
            
    def _upload_file_to_r2(self, file_path: Path, key: str, content_type: str):
        """上傳單個檔案到 R2"""
        try:
            with open(file_path, 'rb') as f:
                self.r2_client.upload_fileobj(
                    f, self.r2_bucket, key,
                    ExtraArgs={'ContentType': content_type}
                )
            logger.info(f"✅ 上傳成功: {key}")
        except Exception as e:
            logger.error(f"❌ 上傳失敗 {key}: {str(e)}")
            raise

    def generate_ai_content(self) -> bool:
        """使用 OpenAI 生成內容"""
        try:
            prompt = f"""
作為專業的短影音內容策劃師，請根據以下資訊生成適合台灣市場的內容：

## 影片資訊
- 任務名稱：{self.task_name}
- 負責人：{self.assignee}
- 攝影師：{self.photographer}
- 影片時長：{self.video_info.get('duration', 'Unknown')} 秒
- 原始標題：{self.video_info.get('title', '')}
- 來源平台：{self.video_info.get('extractor', '')}
- 備註：{self.notes}

## 請生成以下內容（JSON格式）：
{{
  "標題建議": ["15字內吸睛標題1", "15字內吸睛標題2", "15字內吸睛標題3"],
  "內容摘要": "50字內的影片重點描述，突出價值點",
  "標籤建議": ["#標籤1", "#標籤2", "#標籤3", "#標籤4", "#標籤5"],
  "目標受眾": "描述主要觀眾群體特徵",
  "內容分類": "影片類型分類（如：教學、娛樂、生活等）",
  "發布建議": {{
    "最佳時段": "建議發布時間段",
    "平台適配": ["最適合的平台1", "適合的平台2"]
  }},
  "創意要點": "列出3-5個內容亮點",
  "SEO關鍵詞": ["關鍵詞1", "關鍵詞2", "關鍵詞3"]
}}

## 要求：
- 標題要有情緒張力和點擊慾望
- 標籤要混合熱門和長尾關鍵詞
- 內容要符合台灣短影音生態和用語習慣
- 考慮當前熱門趨勢
"""

            response = self.openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=1000
            )
            
            self.ai_content = json.loads(response.choices[0].message.content)
            
            # 驗證生成的內容
            if self._validate_ai_content(self.ai_content):
                logger.info("✅ AI 內容生成完成且通過驗證")
                return True
            else:
                logger.warning("⚠️ AI 內容驗證失敗，使用預設內容")
                self._use_fallback_content()
                return True
            
        except Exception as e:
            logger.error(f"❌ AI 內容生成失敗: {str(e)}", exc_info=True)
            self._use_fallback_content()
            return True
            
    def _validate_ai_content(self, content: Dict[str, Any]) -> bool:
        """驗證 AI 生成內容的品質"""
        required_keys = ['標題建議', '內容摘要', '標籤建議', '目標受眾']
        
        for key in required_keys:
            if key not in content:
                logger.warning(f"AI 內容缺少必要欄位: {key}")
                return False
                
        # 檢查標題長度
        if isinstance(content.get('標題建議'), list):
            for title in content['標題建議']:
                if len(str(title)) > 30:
                    logger.warning(f"標題過長: {title}")
                    return False
        
        # 檢查標籤格式
        if isinstance(content.get('標籤建議'), list):
            for tag in content['標籤建議']:
                if not str(tag).startswith('#'):
                    logger.warning(f"標籤格式錯誤: {tag}")
                    return False
        
        return True
        
    def _use_fallback_content(self):
        """使用預設內容作為後備方案"""
        self.ai_content = {
            "標題建議": [
                self.task_name,
                f"{self.task_name} - 精彩內容",
                f"必看！{self.task_name}重點整理"
            ],
            "內容摘要": f"{self.task_name}的精彩內容，值得一看",
            "標籤建議": ["#短影音", "#精彩", "#必看", "#分享", "#推薦"],
            "目標受眾": "一般觀眾",
            "內容分類": "生活",
            "發布建議": {
                "最佳時段": "晚上8-10點",
                "平台適配": ["YouTube Shorts", "Instagram Reels"]
            },
            "創意要點": "內容豐富有趣，適合分享",
            "SEO關鍵詞": ["短影音", "精彩", "分享"]
        }

    def send_webhook_result(self, success: bool = True, error_message: Optional[str] = None):
        """發送處理結果到 n8n Webhook"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'VideoProcessor/1.0'
            }
            
            if success:
                payload = {
                    "status": "success",
                    "secret": self.webhook_secret,
                    "task_id": self.task_id,
                    "gsheet_row_index": self.row_index,
                    "task_data": {
                        "任務名稱": self.task_name,
                        "負責人": self.assignee,
                        "攝影師": self.photographer,
                        "拍攝日期": self.shoot_date,
                        "備註": self.notes,
                        "原始連結": self.video_url
                    },
                    "r2_data": {
                        "video_url": self.video_url_r2,
                        "thumbnail_url": self.thumbnail_url_r2,
                        "r2_path": self.r2_path
                    },
                    "ai_content": self.ai_content,
                    "video_info": {
                        "duration": self.video_info.get('duration'),
                        "title": self.video_info.get('title'),
                        "extractor": self.video_info.get('extractor')
                    },
                    "processed_time": datetime.now().isoformat(),
                    "processing_stats": {
                        "video_size": self._get_file_size(self.video_file) if hasattr(self, 'video_file') else None,
                        "thumbnail_generated": self.thumbnail_file is not None
                    }
                }
            else:
                payload = {
                    "status": "error",
                    "secret": self.webhook_secret,
                    "task_id": self.task_id,
                    "gsheet_row_index": self.row_index,
                    "task_name": self.task_name,
                    "error_message": error_message,
                    "processed_time": datetime.now().isoformat()
                }
                
            response = requests.post(
                self.webhook_url, 
                json=payload, 
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            logger.info(f"✅ 結果已成功發送到 Webhook (狀態碼: {response.status_code})")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Webhook 網路錯誤: {str(e)}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ Webhook 發送錯誤: {str(e)}", exc_info=True)
            
    def cleanup(self):
        """清理臨時檔案"""
        try:
            if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"🗑️ 清理臨時目錄: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"⚠️ 清理失敗: {str(e)}")
            
    def process(self):
        """主要處理流程"""
        start_time = time.time()
        
        try:
            logger.info("="*50)
            logger.info(f"開始處理任務 {self.task_id}")
            logger.info("="*50)
            
            # 1. 創建工作目錄
            self.create_temp_directory()
            
            # 2. 下載影片
            logger.info("🔽 階段 1: 下載影片")
            if not self.download_video():
                raise Exception("影片下載階段失敗")
                
            # 3. 上傳到 R2
            logger.info("☁️ 階段 2: 上傳到 R2")
            if not self.upload_to_r2():
                raise Exception("R2 上傳階段失敗")
                
            # 4. 生成 AI 內容
            logger.info("🤖 階段 3: 生成 AI 內容")
            self.generate_ai_content()
            
            # 5. 發送成功結果
            logger.info("📤 階段 4: 發送結果")
            self.send_webhook_result(success=True)
            
            processing_time = time.time() - start_time
            logger.info("="*50)
            logger.info(f"🎉 任務 {self.task_id} 處理完成！")
            logger.info(f"⏱️ 總處理時間: {processing_time:.2f} 秒")
            logger.info("="*50)
            
        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = str(e)
            logger.error("="*50)
            logger.error(f"💥 任務 {self.task_id} 處理失敗: {error_msg}")
            logger.error(f"⏱️ 失敗前處理時間: {processing_time:.2f} 秒")
            logger.error("="*50, exc_info=True)
            
            self.send_webhook_result(success=False, error_message=error_msg)
            sys.exit(1)
            
        finally:
            self.cleanup()

if __name__ == "__main__":
    processor = VideoProcessor()
    processor.process()