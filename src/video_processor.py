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
            
            return video_info
        
        finally:
            self._cleanup()

    # ... _download, _find_downloaded_files, _upload, 等其他輔助函數保持不變 ...
    async def _download(self, video_url: str, task_name: str) -> Dict:
        safe_name = self._sanitize_filename(task_name)
        output_template = self.temp_dir / f'{safe_name}.%(ext)s'
        
        cmd = [
            'yt-dlp', '--format', 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '--merge-output-format', 'mp4', '--write-thumbnail', '--write-info-json',
            '--no-playlist', '--extractor-retries', '3', '--output', str(output_template)
        ]
        
        logger.info(f"🔽 執行下載指令...")
        process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"yt-dlp 下載失敗: {stderr.decode('utf-8', errors='ignore')}")

        logger.info("✅ 下載完成")
        return await self._find_downloaded_files(safe_name)

    async def _find_downloaded_files(self, base_name: str) -> Dict:
        video_path = next(self.temp_dir.glob(f'{base_name}.mp4'), None)
        thumb_path = next(self.temp_dir.glob(f'{base_name}*.jpg'), 
                        next(self.temp_dir.glob(f'{base_name}*.webp'), None))
        info_path = next(self.temp_dir.glob(f'{base_name}*.json'), None)

        if not video_path: raise Exception("找不到下載的影片檔案")

        info = {}
        if info_path and info_path.exists():
            with open(info_path, 'r', encoding='utf-8') as f:
                info = json.load(f)
        
        return {"video_path": video_path, "thumb_path": thumb_path, "info": info}

    async def _upload(self, files: Dict, task_name: str) -> Dict:
        if not self.r2_enabled: return {}
        
        base_path = f"videos/{datetime.now().strftime('%Y-%m')}/{self._sanitize_filename(task_name)}_{self.task_id}"
        
        video_url_r2, thumb_url_r2 = None, None
        
        if files.get('video_path'):
            video_key = f"{base_path}/video.mp4"
            await self._upload_file(files['video_path'], video_key, 'video/mp4')
            video_url_r2 = self._get_r2_public_url(video_key)
            
        if files.get('thumb_path'):
            thumb_key = f"{base_path}/thumbnail.jpg"
            await self._upload_file(files['thumb_path'], thumb_key, 'image/jpeg')
            thumb_url_r2 = self._get_r2_public_url(thumb_key)

        logger.info("✅ R2 上傳完成")
        return {"r2_video_url": video_url_r2, "r2_thumbnail_url": thumb_url_r2}

    async def _upload_file(self, file_path: Path, key: str, content_type: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.r2_client.upload_file, str(file_path), self.r2_bucket, key, ExtraArgs={'ContentType': content_type})

    def _get_r2_public_url(self, key: str) -> str:
        custom_domain = os.environ.get('R2_PUBLIC_URL')
        if custom_domain:
            return f"{custom_domain.rstrip('/')}/{key}"
        return f"https://{self.r2_bucket}.{self.r2_account_id}.r2.cloudflarestorage.com/{key}"

    def _cleanup(self):
        if hasattr(self, 'temp_dir') and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            logger.info(f"🗑️ 已清理臨時目錄: {self.temp_dir}")

    def _generate_task_id(self, task_name, video_url) -> str:
        return hashlib.md5(f"{task_name}{video_url}{datetime.now()}".encode()).hexdigest()[:12]

    def _sanitize_filename(self, filename: str) -> str:
        import re
        return re.sub(r'[\\/*?:"<>|]', "", filename)[:100]