"""
影片處理器 - 下載和基本處理
"""

import os
import logging
from typing import Dict, Optional
import yt_dlp

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self):
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)
    
    async def process_video(self, video_url: str) -> Dict:
        """處理影片"""
        logger.info(f"🎬 開始處理影片: {video_url}")
        
        try:
            # 使用 yt-dlp 獲取影片資訊
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                
                result = {
                    "title": info.get('title', ''),
                    "description": info.get('description', ''),
                    "duration": info.get('duration', 0),
                    "uploader": info.get('uploader', ''),
                    "thumbnail": info.get('thumbnail', ''),
                    "success": True
                }
                
                logger.info(f"✅ 影片資訊提取成功: {result['title']}")
                return result
                
        except Exception as e:
            logger.error(f"❌ 影片處理失敗: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }