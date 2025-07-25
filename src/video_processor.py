async def _download(self, video_url: str, task_name: str) -> Dict:
    """使用 yt-dlp 異步下載影片"""
    
    # 驗證 URL
    if not video_url or not video_url.strip():
        raise ValueError("影片 URL 不能為空")
    
    logger.info(f"🔽 準備下載影片: {video_url}")
    
    safe_name = self._sanitize_filename(task_name)
    output_template = self.temp_dir / f'{safe_name}.%(ext)s'
    
    cmd = [
        'yt-dlp',
        video_url,  # ⚠️ 確保 URL 在這裡！
        '--format', 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        '--merge-output-format', 'mp4',
        '--write-thumbnail',
        '--write-info-json',
        '--no-playlist',
        '--extractor-retries', '3',
        '--output', str(output_template)
    ]
    
    # 加入除錯日誌
    logger.info(f"🔽 正在執行 yt-dlp 下載指令...")
    logger.debug(f"完整命令: {' '.join(cmd)}")
    
    process = await asyncio.create_subprocess_exec(
        *cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_message = stderr.decode('utf-8', errors='ignore')
        logger.error(f"❌ yt-dlp 下載失敗: {error_message}")
        
        # 特別處理 Facebook 的錯誤
        if "facebook" in video_url.lower() and "login" in error_message.lower():
            logger.error("💡 提示：Facebook 影片可能需要登入才能下載")
        
        raise Exception(f"yt-dlp download failed: {error_message}")

    logger.info("✅ 影片下載成功")
    return await self._find_downloaded_files(safe_name)