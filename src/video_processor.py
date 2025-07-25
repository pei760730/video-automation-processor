# src/video_processor.py - 影片處理器 (v1.1 - 修正版)

import os
import subprocess
import tempfile
import shutil
import logging
import hashlib
from pathlib import Path
from typing import Dict, Optional
import json
import boto3
import asyncio

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self):
        # ... __init__ 函數的內容保持不變 ...
        self.r2_account_id = os.environ.get('R2_ACCOUNT_ID')
        self.r2_access_key = os.environ.get('R2_ACCESS_KEY_ID')
        self.r2_secret_key = os.environ.get('R2_SECRET_ACCESS_KEY')
        self.r2_bucket = os.environ.get('R2_BUCKET_NAME', 'video-automation-processor')
        
        self.r2_enabled = all([self.r2_account_id, self.r2_access_key, self.r2_secret_key, self.r2_bucket])
        if not self.r2_enabled:
            logger.warning("⚠️ R2 配置不完整，將跳過上傳操作")
            self.r2_client = None
        else:
            self.r2_client = boto3.client(
                's3',
                endpoint_url=f'https://{self.r2_account_id}.r2.cloudflarestorage.com',
                aws_access_key_id=self.r2_access_key,
                aws_secret_access_key=self.r2_secret_key,
                region_name='auto'
            )
            logger.info("✅ R2 客戶端已初始化")

    # --- 核心修正：將函數名稱從 process_video 改為 process ---
    async def process(self, video_url: str, task_name: str) -> Dict:
        """處理影片的主流程：下載、上傳、清理"""
        self.task_id = self._generate_task_id(task_name, video_url)
        self.temp_dir = Path(tempfile.mkdtemp(prefix=f'video_{self.task_id}_'))
        logger.info(f"📁 創建臨時目錄: {self.temp_dir}")
        
        try:
            # 下載
            downloaded_files = await self._download(video_url, task_name)
            if not downloaded_files.get('video_path'):
                raise Exception("影片下載失敗")
            
            # 上傳 R2
            uploaded_urls = await self._upload(downloaded_files, task_name)
            
            # 準備回傳資訊
            video_info = downloaded_files.get('info', {})
            video_info.update(uploaded_urls) # 合併 R2 URLs
            video_info['task_id'] = self.task_id
# src/video_processor.py - 影片處理器 (v1.2 - 修正版)

import os
import subprocess
import tempfile
import shutil
import logging
import hashlib
from datetime import datetime  # <--- 修正: 加入了這一行，解決 NameError
from pathlib import Path
from typing import Dict, Optional
import json
import boto3
import asyncio

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self):
        """初始化影片處理器，檢查並設置 R2 客戶端"""
        self.r2_account_id = os.environ.get('R2_ACCOUNT_ID')
        self.r2_access_key = os.environ.get('R2_ACCESS_KEY_ID')
        self.r2_secret_key = os.environ.get('R2_SECRET_ACCESS_KEY')
        self.r2_bucket = os.environ.get('R2_BUCKET_NAME', 'video-automation-processor')
        
        # 檢查 R2 配置是否完整
        self.r2_enabled = all([self.r2_account_id, self.r2_access_key, self.r2_secret_key, self.r2_bucket])
        
        if not self.r2_enabled:
            logger.warning("⚠️ R2 配置不完整，將跳過上傳操作")
            self.r2_client = None
        else:
            self.r2_client = boto3.client(
                's3',
                endpoint_url=f'https://{self.r2_account_id}.r2.cloudflarestorage.com',
                aws_access_key_id=self.r2_access_key,
                aws_secret_access_key=self.r2_secret_key,
                region_name='auto'  # R2 需要 'auto'
            )
            logger.info("✅ R2 客戶端已成功初始化")

    async def process(self, video_url: str, task_name: str) -> Dict:
        """處理影片的主流程：下載、上傳、清理"""
        self.task_id = self._generate_task_id(task_name, video_url)
        self.temp_dir = Path(tempfile.mkdtemp(prefix=f'video_{self.task_id}_'))
        logger.info(f"📁 創建臨時目錄: {self.temp_dir}")
        
        try:
            # 1. 下載影片和相關檔案
            downloaded_files = await self._download(video_url, task_name)
            if not downloaded_files.get('video_path'):
                raise Exception("影片下載失敗，未找到影片檔案")
            
            # 2. 上傳到 Cloudflare R2
            uploaded_urls = await self._upload(downloaded_files, task_name)
            
            # 3. 準備並回傳包含所有路徑和資訊的字典
            video_info = downloaded_files.get('info', {})
            video_info.update(uploaded_urls) # 將 R2 的 URL 合併進來
            video_info['task_id'] = self.task_id
            
            return video_info
        
        finally:
            # 確保無論成功或失敗，都會執行清理
            self._cleanup()

    async def _download(self, video_url: str, task_name: str) -> Dict:
        """使用 yt-dlp 異步下載影片"""
        safe_name = self._sanitize_filename(task_name)
        output_template = self.temp_dir / f'{safe_name}.%(ext)s'
        
        cmd = [
            'yt-dlp', 
            '--format', 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '--merge-output-format', 'mp4',
            '--write-thumbnail',
            '--write-info-json',
            '--no-playlist',
            '--extractor-retries', '3',
            '--output', str(output_template)
        ]
        
        logger.info(f"🔽 正在執行 yt-dlp 下載指令...")
        process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_message = stderr.decode('utf-8', errors='ignore')
            logger.error(f"❌ yt-dlp 下載失敗: {error_message}")
            raise Exception(f"yt-dlp download failed: {error_message}")

        logger.info("✅ 影片下載成功")
        return await self._find_downloaded_files(safe_name)

    async def _find_downloaded_files(self, base_name: str) -> Dict:
        """在臨時目錄中尋找下載好的影片、縮圖和資訊檔案"""
        video_path = next(self.temp_dir.glob(f'{base_name}.mp4'), None)
        # 尋找最常見的縮圖格式
        thumb_path = next(self.temp_dir.glob(f'{base_name}*.jpg'), 
                        next(self.temp_dir.glob(f'{base_name}*.webp'), None))
        info_path = next(self.temp_dir.glob(f'{base_name}*.json'), None)

        if not video_path:
            raise FileNotFoundError("找不到下載後的影片檔案")

        info_data = {}
        if info_path and info_path.exists():
            with open(info_path, 'r', encoding='utf-8') as f:
                info_data = json.load(f)
        
        return {"video_path": video_path, "thumb_path": thumb_path, "info": info_data}

    async def _upload(self, files: Dict, task_name: str) -> Dict:
        """上傳檔案到 R2"""
        if not self.r2_enabled:
            return {}
        
        date_folder = datetime.now().strftime('%Y-%m')
        safe_name = self._sanitize_filename(task_name)
        base_path = f"videos/{date_folder}/{safe_name}_{self.task_id}"
        
        video_url_r2, thumb_url_r2 = None, None
        
        if files.get('video_path'):
            video_key = f"{base_path}/video.mp4"
            await self._upload_file(files['video_path'], video_key, 'video/mp4')
            video_url_r2 = self._get_r2_public_url(video_key)
            
        if files.get('thumb_path'):
            thumb_key = f"{base_path}/thumbnail.jpg"
            await self._upload_file(files['thumb_path'], thumb_key, 'image/jpeg')
            thumb_url_r2 = self._get_r2_public_url(thumb_key)

        logger.info(f"✅ R2 上傳完成: {base_path}")
        return {"r2_video_url": video_url_r2, "r2_thumbnail_url": thumb_url_r2}

    async def _upload_file(self, file_path: Path, key: str, content_type: str):
        """異步執行檔案上傳"""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, 
            self.r2_client.upload_file, 
            str(file_path), 
            self.r2_bucket, 
            key, 
            ExtraArgs={'ContentType': content_type}
        )

    def _get_r2_public_url(self, key: str) -> str:
        """生成 R2 的公開存取 URL"""
        # 優先使用自訂域名
        custom_domain = os.environ.get('R2_PUBLIC_URL')
        if custom_domain:
            # 確保 custom_domain 後面沒有多餘的斜線
            return f"{custom_domain.rstrip('/')}/{key}"
        return f"https://{self.r2_bucket}.{self.r2_account_id}.r2.cloudflarestorage.com/{key}"

    def _cleanup(self):
        """清理臨時工作目錄"""
        if hasattr(self, 'temp_dir') and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"🗑️ 已成功清理臨時目錄: {self.temp_dir}")
            except Exception as e:
                logger.warning(f"⚠️ 清理臨時目錄失敗: {e}")

    def _generate_task_id(self, task_name, video_url) -> str:
        """根據任務資訊和當前時間生成唯一的任務 ID"""
        # 使用 datetime.now() 需要先導入 datetime
        seed = f"{task_name}{video_url}{datetime.now().isoformat()}"
        return hashlib.md5(seed.encode()).hexdigest()[:12]

    def _sanitize_filename(self, filename: str) -> str:
        """清理檔案名稱，移除不安全的字符，並限制長度"""
        import re
        # 移除非法字符
        safe_name = re.sub(r'[\\/*?:"<>|]', "", filename)
        # 限制長度
        return safe_name[:100]