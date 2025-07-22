#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# process_task.py - 短影音處理核心引擎 (容錯優化版)

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
import glob
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import openai

# === 編碼修復 ===
if sys.platform == 'win32':
    import locale
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except:
        try:
            locale.setlocale(locale.LC_ALL, 'C.UTF-8')
        except:
            pass

# === 日誌設定 ===
class SafeFormatter(logging.Formatter):
    """安全的日誌格式化器，處理 emoji 和編碼問題"""
    def format(self, record):
        msg = super().format(record)
        # 移除 emoji（Windows 相容性）
        emoji_map = {
            '🎬': '[VIDEO]', '📹': '[LINK]', '🔽': '[DOWNLOAD]',
            '✅': '[SUCCESS]', '❌': '[ERROR]', '⚠️': '[WARNING]',
            '☁️': '[CLOUD]', '🤖': '[AI]', '📤': '[SEND]',
            '🎉': '[COMPLETE]', '⏱️': '[TIME]', '🗑️': '[CLEANUP]',
            '💥': '[FAILED]', '📁': '[FOLDER]', '📋': '[TASK]',
            '🔒': '[SECURITY]', '⏭️': '[SKIP]'
        }
        for emoji, replacement in emoji_map.items():
            msg = msg.replace(emoji, replacement)
        return msg

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("processing.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
logger.handlers[0].setFormatter(SafeFormatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.handlers[1].setFormatter(SafeFormatter('%(asctime)s - %(levelname)s - %(message)s'))

class VideoProcessor:
    def __init__(self):
        """初始化處理器"""
        # === 環境變數 ===
        self.skip_failed = os.getenv('SKIP_FAILED_DOWNLOADS', 'false').lower() == 'true'
        
        # === API 配置 ===
        self.r2_account_id = os.getenv('R2_ACCOUNT_ID', '')
        self.r2_access_key = os.getenv('R2_ACCESS_KEY', '')
        self.r2_secret_key = os.getenv('R2_SECRET_KEY', '')
        self.r2_bucket = os.getenv('R2_BUCKET', 'video-automation')
        self.openai_api_key = os.getenv('OPENAI_API_KEY', '')
        
        # === Webhook 配置 ===
        self.webhook_url = os.getenv('N8N_WEBHOOK_URL', '')
        self.webhook_secret = os.getenv('N8N_WEBHOOK_SECRET', 'your-secret')
        
        # === 任務參數 ===
        self.video_url = os.getenv('VIDEO_URL', '')
        self.task_name = os.getenv('TASK_NAME', f'任務_{int(time.time())}')
        self.assignee = os.getenv('ASSIGNEE', '')
        self.photographer = os.getenv('PHOTOGRAPHER', '')
        self.shoot_date = os.getenv('SHOOT_DATE') or datetime.now().strftime('%Y-%m-%d')
        self.notes = os.getenv('NOTES', '')
        self.row_index = os.getenv('GSHEET_ROW_INDEX', '1')
        
        # === 驗證必要參數 ===
        if not self.video_url:
            raise ValueError("必要環境變數 VIDEO_URL 未設置")
            
        # === 生成任務 ID ===
        self.task_id = hashlib.md5(f"{self.task_name}_{time.time()}".encode()).hexdigest()[:12]
        
        # === 初始化客戶端 ===
        if self.openai_api_key:
            self.openai_client = openai.OpenAI(api_key=self.openai_api_key)
        else:
            logger.warning("[WARNING] OpenAI API key 未設置，將使用預設內容")
            self.openai_client = None
            
        if all([self.r2_account_id, self.r2_access_key, self.r2_secret_key]):
            self.r2_client = boto3.client(
                's3',
                endpoint_url=f'https://{self.r2_account_id}.r2.cloudflarestorage.com',
                aws_access_key_id=self.r2_access_key,
                aws_secret_access_key=self.r2_secret_key,
                region_name='auto'
            )
        else:
            logger.warning("[WARNING] R2 配置不完整，將跳過上傳")
            self.r2_client = None
            
        logger.info("="*70)
        logger.info(f"[VIDEO] 開始處理任務: {self.task_name} (ID: {self.task_id})")
        logger.info(f"[LINK] 影片連結: {self.video_url}")
        logger.info(f"[SKIP] 跳過失敗模式: {'開啟' if self.skip_failed else '關閉'}")
        logger.info("="*70)
        
    def create_temp_directory(self):
        """創建臨時目錄"""
        self.temp_dir = tempfile.mkdtemp(prefix=f'video_{self.task_id}_')
        logger.info(f"[FOLDER] 創建臨時目錄: {self.temp_dir}")
        return self.temp_dir
        
    def download_video(self) -> bool:
        """下載影片（容錯版本）"""
        try:
            logger.info("[DOWNLOAD] 開始下載影片...")
            
            # 基本下載命令
            cmd = [
                'yt-dlp',
                '--no-warnings',
                '--quiet',
                '--no-progress',
                '--format', 'best[height<=720]/best',
                '--merge-output-format', 'mp4',
                '--write-thumbnail',
                '--no-playlist',
                '--output', os.path.join(self.temp_dir, '%(title).100s.%(ext)s'),
                self.video_url
            ]
            
            # 執行下載
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=300,  # 5分鐘超時
                cwd=self.temp_dir
            )
            
            # 檢查結果
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                logger.error(f"[ERROR] yt-dlp 錯誤: {error_msg}")
                
                # 如果是小紅書或需要登入的網站，記錄但繼續
                if any(x in error_msg.lower() for x in ['xiaohongshu', 'xhs', 'login', 'cookie', 'no video formats']):
                    logger.warning("[WARNING] 此網站可能需要登入，跳過下載")
                    if self.skip_failed:
                        return self._create_placeholder_video()
                    return False
                    
                raise Exception(f"下載失敗: {error_msg}")
                
            # 查找下載的檔案
            video_files = glob.glob(os.path.join(self.temp_dir, '*.mp4'))
            if not video_files:
                logger.warning("[WARNING] 找不到 MP4 檔案，嘗試其他格式")
                video_files = glob.glob(os.path.join(self.temp_dir, '*'))
                video_files = [f for f in video_files if any(f.endswith(ext) for ext in ['.mp4', '.webm', '.mkv', '.mov', '.avi'])]
                
            if video_files:
                self.video_file = Path(video_files[0])
                logger.info(f"[SUCCESS] 影片下載成功: {self.video_file.name}")
            else:
                if self.skip_failed:
                    return self._create_placeholder_video()
                return False
                
            # 查找縮圖
            thumb_files = glob.glob(os.path.join(self.temp_dir, '*.jpg')) + \
                         glob.glob(os.path.join(self.temp_dir, '*.png')) + \
                         glob.glob(os.path.join(self.temp_dir, '*.webp'))
            
            if thumb_files:
                self.thumbnail_file = Path(thumb_files[0])
                logger.info(f"[SUCCESS] 縮圖找到: {self.thumbnail_file.name}")
            else:
                self.thumbnail_file = None
                logger.info("[INFO] 沒有縮圖")
                
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("[ERROR] 下載超時")
            if self.skip_failed:
                return self._create_placeholder_video()
            return False
        except Exception as e:
            logger.error(f"[ERROR] 下載異常: {str(e)}")
            if self.skip_failed:
                return self._create_placeholder_video()
            return False
            
    def _create_placeholder_video(self) -> bool:
        """創建佔位影片"""
        try:
            logger.info("[INFO] 創建佔位內容...")
            
            # 創建簡單的文字檔作為佔位
            placeholder_path = Path(self.temp_dir) / f"{self.task_id}_placeholder.txt"
            with open(placeholder_path, 'w', encoding='utf-8') as f:
                f.write(f"影片下載失敗\n")
                f.write(f"任務: {self.task_name}\n")
                f.write(f"URL: {self.video_url}\n")
                f.write(f"時間: {datetime.now()}\n")
                
            self.video_file = placeholder_path
            self.thumbnail_file = None
            self.is_placeholder = True
            
            logger.info("[SUCCESS] 佔位內容創建成功")
            return True
        except Exception as e:
            logger.error(f"[ERROR] 佔位內容創建失敗: {str(e)}")
            return False
            
    def upload_to_r2(self) -> bool:
        """上傳到 R2（容錯版本）"""
        if not self.r2_client:
            logger.warning("[SKIP] 跳過 R2 上傳（未配置）")
            self.video_url_r2 = self.video_url
            self.thumbnail_url_r2 = None
            return True
            
        try:
            logger.info("[CLOUD] 開始上傳到 R2...")
            
            # 構建路徑
            date_folder = datetime.now().strftime('%Y-%m-%d')
            base_path = f"videos/{date_folder}/{self.task_id}"
            
            # 上傳主檔案
            if hasattr(self, 'video_file') and self.video_file.exists():
                file_key = f"{base_path}/{self.video_file.name}"
                
                with open(self.video_file, 'rb') as f:
                    self.r2_client.put_object(
                        Bucket=self.r2_bucket,
                        Key=file_key,
                        Body=f,
                        ContentType='video/mp4' if self.video_file.suffix == '.mp4' else 'application/octet-stream'
                    )
                    
                # 生成 URL
                if os.getenv('R2_CUSTOM_DOMAIN'):
                    self.video_url_r2 = f"https://{os.getenv('R2_CUSTOM_DOMAIN')}/{file_key}"
                else:
                    self.video_url_r2 = f"https://{self.r2_bucket}.{self.r2_account_id}.r2.cloudflarestorage.com/{file_key}"
                    
                logger.info(f"[SUCCESS] 影片上傳成功: {self.video_url_r2}")
            else:
                self.video_url_r2 = self.video_url
                
            # 上傳縮圖
            if hasattr(self, 'thumbnail_file') and self.thumbnail_file and self.thumbnail_file.exists():
                thumb_key = f"{base_path}/{self.thumbnail_file.name}"
                
                with open(self.thumbnail_file, 'rb') as f:
                    self.r2_client.put_object(
                        Bucket=self.r2_bucket,
                        Key=thumb_key,
                        Body=f,
                        ContentType='image/jpeg'
                    )
                    
                if os.getenv('R2_CUSTOM_DOMAIN'):
                    self.thumbnail_url_r2 = f"https://{os.getenv('R2_CUSTOM_DOMAIN')}/{thumb_key}"
                else:
                    self.thumbnail_url_r2 = f"https://{self.r2_bucket}.{self.r2_account_id}.r2.cloudflarestorage.com/{thumb_key}"
                    
                logger.info(f"[SUCCESS] 縮圖上傳成功: {self.thumbnail_url_r2}")
            else:
                self.thumbnail_url_r2 = None
                
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] R2 上傳失敗: {str(e)}")
            # 上傳失敗時使用原始 URL
            self.video_url_r2 = self.video_url
            self.thumbnail_url_r2 = None
            return True  # 繼續流程
            
    def generate_ai_content(self) -> bool:
        """生成 AI 內容（容錯版本）"""
        try:
            if not self.openai_client:
                logger.info("[SKIP] 使用預設內容（無 OpenAI key）")
                self._use_default_content()
                return True
                
            logger.info("[AI] 生成 AI 內容...")
            
            prompt = f"""
作為專業的短影音內容策劃師，請根據以下資訊生成內容：

任務名稱：{self.task_name}
備註：{self.notes}

請生成以下內容（JSON格式）：
{{
  "標題建議": ["吸睛標題1", "吸睛標題2", "吸睛標題3"],
  "內容摘要": "50字內的影片重點描述",
  "標籤建議": ["#標籤1", "#標籤2", "#標籤3", "#標籤4", "#標籤5"],
  "目標受眾": "主要觀眾群體",
  "內容分類": "影片類型",
  "發布建議": {{"最佳時段": "晚上8-10點", "平台適配": ["YouTube Shorts", "Instagram Reels"]}},
  "創意要點": "3個內容亮點",
  "SEO關鍵詞": ["關鍵詞1", "關鍵詞2", "關鍵詞3"]
}}
"""

            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",  # 使用更便宜的模型
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=800
            )
            
            content = response.choices[0].message.content
            # 嘗試解析 JSON
            try:
                # 移除可能的 markdown 標記
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0]
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0]
                    
                self.ai_content = json.loads(content)
                logger.info("[SUCCESS] AI 內容生成成功")
            except:
                logger.warning("[WARNING] AI 回應解析失敗，使用預設內容")
                self._use_default_content()
                
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] AI 生成失敗: {str(e)}")
            self._use_default_content()
            return True
            
    def _use_default_content(self):
        """使用預設內容"""
        self.ai_content = {
            "標題建議": [
                self.task_name,
                f"精彩分享：{self.task_name}",
                f"必看！{self.task_name}"
            ],
            "內容摘要": f"這是關於{self.task_name}的精彩內容，值得觀看和分享。",
            "標籤建議": ["#短影音", "#精彩內容", "#分享", "#推薦", "#熱門"],
            "目標受眾": "一般觀眾",
            "內容分類": "綜合",
            "發布建議": {
                "最佳時段": "晚上8-10點",
                "平台適配": ["YouTube Shorts", "Instagram Reels", "TikTok"]
            },
            "創意要點": "內容豐富、畫面精彩、適合分享",
            "SEO關鍵詞": [self.task_name, "短影音", "精彩"]
        }
        
    def send_webhook_result(self, success: bool = True, error_message: Optional[str] = None):
        """發送結果到 n8n"""
        if not self.webhook_url:
            logger.warning("[WARNING] 未設置 Webhook URL")
            return
            
        try:
            logger.info("[SEND] 發送結果到 n8n...")
            
            if success:
                # 成功 payload
                payload = {
                    "status": "success",
                    "secret": self.webhook_secret,
                    "task_id": self.task_id,
                    "gsheet_row_index": self.row_index,
                    "page_title": self.ai_content["標題建議"][0],
                    "properties": {
                        "任務名稱": self.task_name,
                        "負責人": self.assignee or "未指定",
                        "攝影師": self.photographer or "未指定",
                        "拍攝日期": self.shoot_date,
                        "原始連結": self.video_url,
                        "R2影片連結": getattr(self, 'video_url_r2', self.video_url),
                        "AI標題建議": "\n".join(self.ai_content.get("標題建議", [])),
                        "內容摘要": self.ai_content.get("內容摘要", ""),
                        "標籤建議": ", ".join(self.ai_content.get("標籤建議", [])),
                        "內容分類": self.ai_content.get("內容分類", ""),
                        "目標受眾": self.ai_content.get("目標受眾", ""),
                        "SEO關鍵詞": ", ".join(self.ai_content.get("SEO關鍵詞", [])),
                        "備註": self.notes,
                        "處理時間": datetime.now().isoformat()
                    },
                    "content_blocks": {
                        "thumbnail_url": getattr(self, 'thumbnail_url_r2', ''),
                        "ai_titles": self.ai_content.get("標題建議", []),
                        "summary": self.ai_content.get("內容摘要", ""),
                        "tags": self.ai_content.get("標籤建議", []),
                        "creative_points": self.ai_content.get("創意要點", ""),
                        "publish_suggestion": self.ai_content.get("發布建議", {})
                    },
                    "processed_time": datetime.now().isoformat()
                }
            else:
                # 失敗 payload
                payload = {
                    "status": "error",
                    "secret": self.webhook_secret,
                    "task_id": self.task_id,
                    "gsheet_row_index": self.row_index,
                    "task_name": self.task_name,
                    "error_message": error_message or "處理失敗",
                    "processed_time": datetime.now().isoformat()
                }
                
            # 發送請求
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"[SUCCESS] Webhook 發送成功 (HTTP {response.status_code})")
            else:
                logger.warning(f"[WARNING] Webhook 回應: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"[ERROR] Webhook 發送失敗: {str(e)}")
            
    def cleanup(self):
        """清理臨時檔案"""
        try:
            if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"[CLEANUP] 清理完成: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"[WARNING] 清理失敗: {str(e)}")
            
    def process(self):
        """主處理流程"""
        start_time = time.time()
        success = False
        
        try:
            # 1. 創建臨時目錄
            self.create_temp_directory()
            
            # 2. 下載影片
            if not self.download_video():
                if not self.skip_failed:
                    raise Exception("影片下載失敗")
                logger.warning("[WARNING] 下載失敗但繼續處理")
                
            # 3. 上傳到 R2
            self.upload_to_r2()
            
            # 4. 生成 AI 內容
            self.generate_ai_content()
            
            # 5. 發送成功結果
            self.send_webhook_result(success=True)
            success = True
            
            # 完成
            elapsed = time.time() - start_time
            logger.info("="*70)
            logger.info(f"[COMPLETE] 任務完成！處理時間: {elapsed:.2f} 秒")
            logger.info("="*70)
            
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            logger.error("="*70)
            logger.error(f"[FAILED] 任務失敗: {error_msg}")
            logger.error(f"[TIME] 處理時間: {elapsed:.2f} 秒")
            logger.error("="*70)
            
            self.send_webhook_result(success=False, error_message=error_msg)
            
        finally:
            self.cleanup()
            
        # 如果失敗且不是跳過模式，退出碼 1
        if not success and not self.skip_failed:
            sys.exit(1)

if __name__ == "__main__":
    try:
        processor = VideoProcessor()
        processor.process()
    except Exception as e:
        logger.error(f"[FATAL] 初始化失敗: {str(e)}")
        sys.exit(1)