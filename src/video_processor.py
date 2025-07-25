"""
影片處理器 v2.0 - 優化版
- 更好的錯誤處理
- 支援更多平台
- 簡化的程式碼結構
"""

import os
import subprocess
import tempfile
import shutil
import logging
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
import json
import boto3
import asyncio
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class VideoProcessor:
    """影片處理器：下載、處理、上傳影片"""
    
    # 支援的平台和特殊處理
    PLATFORM_HANDLERS = {
        'facebook.com': {'cookies': True, 'format': 'best'},
        'instagram.com': {'cookies': True, 'format': 'best'},
        'tiktok.com': {'format': 'best'},
        'youtube.com': {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'},
        'youtu.be': {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'},
    }
    
    def __init__(self):
        """初始化處理器"""
        # R2 設定
        self.r2_config = {
            'account_id': os.environ.get('R2_ACCOUNT_ID'),
            'access_key': os.environ.get('R2_ACCESS_KEY_ID'),
            'secret_key': os.environ.get('R2_SECRET_ACCESS_KEY'),
            'bucket': os.environ.get('R2_BUCKET_NAME', 'video-automation-processor'),
            'public_url': os.environ.get('R2_PUBLIC_URL')
        }
        
        # 檢查 R2 設定
        self.r2_enabled = all([
            self.r2_config['account_id'],
            self.r2_config['access_key'],
            self.r2_config['secret_key']
        ])
        
        if self.r2_enabled:
            self._init_r2_client()
        else:
            logger.warning("⚠️ R2 配置不完整，將跳過上傳")
            self.r2_client = None
    
    def _init_r2_client(self):
        """初始化 R2 客戶端"""
        try:
            self.r2_client = boto3.client(
                's3',
                endpoint_url=f"https://{self.r2_config['account_id']}.r2.cloudflarestorage.com",
                aws_access_key_id=self.r2_config['access_key'],
                aws_secret_access_key=self.r2_config['secret_key'],
                region_name='auto'
            )
            logger.info("✅ R2 客戶端初始化成功")
        except Exception as e:
            logger.error(f"❌ R2 客戶端初始化失敗: {e}")
            self.r2_enabled = False
            self.r2_client = None
    
    async def process(self, video_url: str, task_name: str) -> Dict:
        """
        處理影片的主流程
        
        Args:
            video_url: 影片 URL
            task_name: 任務名稱
            
        Returns:
            包含影片資訊的字典
        """
        # 驗證輸入
        video_url = self._validate_url(video_url)
        task_name = task_name or "未命名任務"
        
        # 生成任務 ID 和建立臨時目錄
        self.task_id = self._generate_task_id(task_name, video_url)
        self.temp_dir = Path(tempfile.mkdtemp(prefix=f'video_{self.task_id}_'))
        
        logger.info(f"📁 工作目錄: {self.temp_dir}")
        logger.info(f"🎬 任務: {task_name}")
        logger.info(f"🔗 URL: {video_url}")
        
        try:
            # 1. 下載影片
            download_result = await self._download(video_url, task_name)
            
            # 2. 提取影片資訊
            video_info = self._extract_video_info(download_result)
            
            # 3. 上傳到 R2（如果啟用）
            if self.r2_enabled and download_result.get('video_path'):
                upload_urls = await self._upload_to_r2(download_result, task_name)
                video_info.update(upload_urls)
            
            # 4. 加入額外資訊
            video_info.update({
                'task_id': self.task_id,
                'task_name': task_name,
                'original_url': video_url,
                'processed_at': datetime.now().isoformat(),
                'success': True
            })
            
            return video_info
            
        except Exception as e:
            logger.error(f"❌ 處理失敗: {str(e)}")
            raise
        finally:
            self._cleanup()
    
    def _validate_url(self, url: str) -> str:
        """驗證並清理 URL"""
        if not url:
            raise ValueError("影片 URL 不能為空")
        
        url = url.strip()
        
        if not url.startswith(('http://', 'https://')):
            raise ValueError(f"無效的 URL 格式: {url}")
        
        return url
    
    def _get_platform_config(self, url: str) -> Dict:
        """根據 URL 取得平台特定設定"""
        domain = urlparse(url).netloc.lower()
        
        for platform, config in self.PLATFORM_HANDLERS.items():
            if platform in domain:
                logger.info(f"🎯 偵測到平台: {platform}")
                return config
        
        # 預設設定
        return {'format': 'best'}
    
    async def _download(self, video_url: str, task_name: str) -> Dict:
        """下載影片和相關檔案"""
        safe_name = self._sanitize_filename(task_name)
        output_template = str(self.temp_dir / f'{safe_name}.%(ext)s')
        
        # 取得平台設定
        platform_config = self._get_platform_config(video_url)
        
        # 建構 yt-dlp 命令
        cmd = [
            'yt-dlp',
            video_url,
            '--format', platform_config.get('format', 'best'),
            '--output', output_template,
            '--no-playlist',
            '--write-info-json',
            '--write-thumbnail',
            '--no-warnings',
            '--no-check-certificate',
            '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        ]
        
        # 如果是需要 cookies 的平台
        if platform_config.get('cookies'):
            cookies_file = Path('cookies.txt')
            if cookies_file.exists():
                cmd.extend(['--cookies', str(cookies_file)])
                logger.info("🍪 使用 cookies 檔案")
            else:
                logger.warning("⚠️ 此平台可能需要 cookies，但未找到 cookies.txt")
        
        # 合併為 mp4（如果需要）
        if 'bestvideo' in platform_config.get('format', ''):
            cmd.extend(['--merge-output-format', 'mp4'])
        
        # 執行下載
        logger.info("⬇️ 開始下載影片...")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                self._handle_download_error(video_url, error_msg)
                raise Exception(f"下載失敗: {error_msg}")
            
            logger.info("✅ 下載完成")
            
            # 尋找下載的檔案
            return await self._find_downloaded_files(safe_name)
            
        except Exception as e:
            logger.error(f"❌ 下載過程出錯: {str(e)}")
            raise
    
    def _handle_download_error(self, url: str, error_msg: str):
        """處理下載錯誤，提供有用的提示"""
        error_lower = error_msg.lower()
        
        if 'private' in error_lower or 'login' in error_lower:
            logger.error("🔒 影片可能是私人的或需要登入")
            logger.error("💡 解決方案：")
            logger.error("   1. 確認影片是公開的")
            logger.error("   2. 使用 cookies.txt 檔案")
        elif '404' in error_msg or 'not found' in error_lower:
            logger.error("❌ 找不到影片，請檢查 URL 是否正確")
        elif 'format' in error_lower:
            logger.error("⚠️ 影片格式問題，嘗試使用預設格式")
        else:
            logger.error(f"❌ 下載錯誤: {error_msg[:200]}")
    
    async def _find_downloaded_files(self, base_name: str) -> Dict:
        """尋找下載的檔案"""
        files = {}
        
        # 尋找影片檔案
        for ext in ['mp4', 'webm', 'mkv', 'mov']:
            video_path = self.temp_dir / f'{base_name}.{ext}'
            if video_path.exists():
                files['video_path'] = video_path
                logger.info(f"📹 找到影片: {video_path.name}")
                break
        
        # 尋找縮圖
        for pattern in [f'{base_name}*.jpg', f'{base_name}*.webp', f'{base_name}*.png']:
            thumb_paths = list(self.temp_dir.glob(pattern))
            if thumb_paths:
                files['thumb_path'] = thumb_paths[0]
                logger.info(f"🖼️ 找到縮圖: {thumb_paths[0].name}")
                break
        
        # 尋找資訊檔案
        info_path = self.temp_dir / f'{base_name}.info.json'
        if info_path.exists():
            files['info_path'] = info_path
            logger.info(f"📋 找到資訊檔案: {info_path.name}")
        
        if not files.get('video_path'):
            raise FileNotFoundError("找不到下載的影片檔案")
        
        return files
    
    def _extract_video_info(self, files: Dict) -> Dict:
        """從下載的檔案中提取資訊"""
        info = {
            'title': '未知標題',
            'duration': 0,
            'description': '',
            'uploader': '',
            'upload_date': '',
            'view_count': 0,
            'like_count': 0,
            'thumbnail': ''
        }
        
        # 如果有 info.json，從中提取資訊
        if files.get('info_path'):
            try:
                with open(files['info_path'], 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                    
                    info.update({
                        'title': json_data.get('title', info['title']),
                        'duration': json_data.get('duration', 0),
                        'description': json_data.get('description', '')[:1000],  # 限制長度
                        'uploader': json_data.get('uploader', ''),
                        'upload_date': json_data.get('upload_date', ''),
                        'view_count': json_data.get('view_count', 0),
                        'like_count': json_data.get('like_count', 0),
                        'thumbnail': json_data.get('thumbnail', '')
                    })
                    
                    logger.info(f"📊 影片資訊: {info['title']} ({info['duration']}秒)")
            except Exception as e:
                logger.warning(f"⚠️ 無法讀取影片資訊: {e}")
        
        return info
    
    async def _upload_to_r2(self, files: Dict, task_name: str) -> Dict:
        """上傳檔案到 R2"""
        if not self.r2_enabled:
            return {}
        
        urls = {}
        
        try:
            # 建立存儲路徑
            date_folder = datetime.now().strftime('%Y-%m')
            safe_name = self._sanitize_filename(task_name)
            base_path = f"videos/{date_folder}/{safe_name}_{self.task_id}"
            
            # 上傳影片
            if files.get('video_path'):
                video_key = f"{base_path}/video.mp4"
                await self._upload_file(files['video_path'], video_key, 'video/mp4')
                urls['r2_video_url'] = self._get_r2_url(video_key)
                logger.info(f"☁️ 影片已上傳: {video_key}")
            
            # 上傳縮圖
            if files.get('thumb_path'):
                thumb_ext = files['thumb_path'].suffix.lower()
                thumb_key = f"{base_path}/thumbnail{thumb_ext}"
                content_type = f"image/{thumb_ext.lstrip('.')}"
                await self._upload_file(files['thumb_path'], thumb_key, content_type)
                urls['r2_thumbnail_url'] = self._get_r2_url(thumb_key)
                logger.info(f"☁️ 縮圖已上傳: {thumb_key}")
            
            return urls
            
        except Exception as e:
            logger.error(f"❌ R2 上傳失敗: {e}")
            return urls
    
    async def _upload_file(self, file_path: Path, key: str, content_type: str):
        """上傳單個檔案到 R2"""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self.r2_client.upload_file,
            str(file_path),
            self.r2_config['bucket'],
            key,
            {'ContentType': content_type}
        )
    
    def _get_r2_url(self, key: str) -> str:
        """生成 R2 公開 URL"""
        if self.r2_config['public_url']:
            return f"{self.r2_config['public_url'].rstrip('/')}/{key}"
        
        return f"https://{self.r2_config['bucket']}.{self.r2_config['account_id']}.r2.cloudflarestorage.com/{key}"
    
    def _cleanup(self):
        """清理臨時檔案"""
        if hasattr(self, 'temp_dir') and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"🗑️ 已清理臨時目錄")
            except Exception as e:
                logger.warning(f"⚠️ 清理失敗: {e}")
    
    def _generate_task_id(self, task_name: str, video_url: str) -> str:
        """生成唯一任務 ID"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        hash_input = f"{task_name}{video_url}{timestamp}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理檔案名稱"""
        # 移除特殊字符
        safe_name = re.sub(r'[^\w\s\-\u4e00-\u9fff]', '', filename)
        # 替換空白為底線
        safe_name = re.sub(r'\s+', '_', safe_name)
        # 限制長度
        return safe_name[:80]