class VideoProcessor:
    """影片處理器 v2.1 - SSL 修復版"""
    
    # 平台設定（加入更多選項）
    PLATFORM_HANDLERS = {
        'facebook.com': {
            'cookies': True, 
            'format': 'best',
            'extra_args': ['--extractor-args', 'facebook:playwright=false']
        },
        'instagram.com': {
            'cookies': True, 
            'format': 'best',
            'extra_args': ['--extractor-args', 'instagram:playwright=false']
        },
        'tiktok.com': {
            'format': 'best',
            'extra_args': ['--extractor-args', 'tiktok:playwright=false']
        },
        'youtube.com': {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'
        },
        'youtu.be': {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'
        },
    }
    
    async def _download(self, video_url: str, task_name: str) -> Dict:
        """下載影片 - SSL 修復版"""
        safe_name = self._sanitize_filename(task_name)
        output_template = str(self.temp_dir / f'{safe_name}.%(ext)s')
        
        platform_config = self._get_platform_config(video_url)
        
        # 基本命令
        cmd = [
            'yt-dlp',
            video_url,
            '--format', platform_config.get('format', 'best'),
            '--output', output_template,
            '--no-playlist',
            '--write-info-json',
            '--write-thumbnail',
            '--no-warnings',
            '--no-check-certificates',  # 關鍵：忽略 SSL
            '--force-ipv4',
            '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        ]
        
        # 加入平台特定參數
        if 'extra_args' in platform_config:
            cmd.extend(platform_config['extra_args'])
        
        # Cookies 處理
        if platform_config.get('cookies'):
            cookies_file = Path('cookies.txt')
            if cookies_file.exists():
                cmd.extend(['--cookies', str(cookies_file)])
            else:
                # 嘗試使用瀏覽器 cookies
                cmd.extend(['--cookies-from-browser', 'chrome'])
        
        # 執行下載（帶 SSL 修復）
        logger.info(f"⬇️ 開始下載: {video_url}")
        
        try:
            env = os.environ.copy()
            env['PYTHONHTTPSVERIFY'] = '0'
            env['SSL_CERT_FILE'] = ''
            env['REQUESTS_CA_BUNDLE'] = ''
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            # 設置超時（60秒）
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=60.0
                )
            except asyncio.TimeoutError:
                process.kill()
                raise Exception("下載超時（60秒）")
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                
                # 特殊錯誤處理
                if 'SSL' in error_msg or 'certificate' in error_msg:
                    logger.error("🔒 SSL 錯誤，嘗試備用方案...")
                    # 可以在這裡實作備用下載方案
                
                self._handle_download_error(video_url, error_msg)
                raise Exception(f"下載失敗: {error_msg[:500]}")
            
            logger.info("✅ 下載完成")
            return await self._find_downloaded_files(safe_name)
            
        except Exception as e:
            logger.error(f"❌ 下載錯誤: {str(e)}")
            raise