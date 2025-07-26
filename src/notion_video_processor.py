# 增強版 src/notion_video_processor.py

import cv2
import numpy as np
from PIL import Image
import base64
import io

class EnhancedNotionVideoProcessor(NotionVideoProcessor):
    """增強版影片處理器 - 新增 Whisper 和本地備份功能"""
    
    def __init__(self):
        super().__init__()
        self.downloads_dir = Path("downloads")
        self.downloads_dir.mkdir(exist_ok=True)
        
    def _extract_video_frame(self, video_path: str, timestamp: float = 1.0) -> Optional[str]:
        """提取影片中的一幀作為縮圖"""
        try:
            cap = cv2.VideoCapture(video_path)
            
            # 設置到指定時間點
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_number = int(fps * timestamp)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                logger.warning("⚠️ 無法提取影片幀，使用預設時間點")
                return None
            
            # 轉換為 RGB 格式
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 調整大小（可選）
            height, width = frame_rgb.shape[:2]
            if width > 1280:
                ratio = 1280 / width
                new_width = 1280
                new_height = int(height * ratio)
                frame_rgb = cv2.resize(frame_rgb, (new_width, new_height))
            
            # 保存為文件
            frame_path = os.path.join(self.temp_dir, f"{self.task.task_id}_frame.jpg")
            cv2.imwrite(frame_path, cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR))
            
            logger.info(f"✅ 提取影片幀成功: {frame_path}")
            return frame_path
            
        except Exception as e:
            logger.error(f"❌ 提取影片幀失敗: {e}")
            return None
    
    def _transcribe_with_whisper(self, video_path: str) -> Optional[Dict[str, Any]]:
        """使用 Whisper 進行語音轉文字"""
        if not self.openai_client:
            logger.warning("⚠️ OpenAI 客戶端未配置，跳過語音轉文字")
            return None
            
        try:
            logger.info("🎤 開始語音轉文字 (Whisper)...")
            
            with open(video_path, 'rb') as audio_file:
                transcript = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    language="zh"  # 指定中文
                )
            
            result = {
                "text": transcript.text,
                "language": transcript.language,
                "duration": transcript.duration,
                "segments": getattr(transcript, 'segments', [])
            }
            
            logger.info(f"✅ 語音轉文字完成: {len(result['text'])} 字元")
            logger.info(f"🗣️ 轉錄文字: {result['text'][:100]}...")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 語音轉文字失敗: {e}")
            return None
    
    def _backup_to_downloads(self, video_path: str, thumbnail_path: Optional[str] = None) -> Dict[str, str]:
        """備份檔案到 downloads 資料夾"""
        import shutil
        
        backup_paths = {}
        
        try:
            # 備份影片
            video_backup = self.downloads_dir / f"{self.task.task_id}_video{Path(video_path).suffix}"
            shutil.copy2(video_path, video_backup)
            backup_paths['video'] = str(video_backup)
            logger.info(f"📁 影片備份完成: {video_backup}")
            
            # 備份縮圖
            if thumbnail_path:
                thumb_backup = self.downloads_dir / f"{self.task.task_id}_thumb{Path(thumbnail_path).suffix}"
                shutil.copy2(thumbnail_path, thumb_backup)
                backup_paths['thumbnail'] = str(thumb_backup)
                logger.info(f"📁 縮圖備份完成: {thumb_backup}")
                
        except Exception as e:
            logger.error(f"❌ 備份失敗: {e}")
            
        return backup_paths
    
    def _enhanced_ai_content_with_transcript(self, transcript_data: Optional[Dict] = None):
        """使用轉錄文字增強 AI 內容生成"""
        if not self.openai_client:
            logger.warning("⚠️ OpenAI 客戶端未配置，跳過 AI 內容生成")
            return
            
        logger.info("🤖 開始增強版 AI 內容生成...")
        
        # 準備提示詞
        transcript_text = ""
        if transcript_data and transcript_data.get('text'):
            transcript_text = f"\n影片轉錄內容: {transcript_data['text']}"
        
        prompt = f"""
        請分析以下影片任務和內容，並以台灣社群媒體風格提供內容建議。
        
        任務資訊：
        - 任務名稱: {self.task.task_name}
        - 負責人: {self.task.person_in_charge}
        - 攝影師: {self.task.videographer}{transcript_text}
        
        請嚴格按照以下 JSON 格式回覆：
        {{
          "AI標題建議": ["吸引人的標題1", "有趣的標題2", "病毒式標題3", "創意標題4", "熱門標題5"],
          "內容摘要": "一段約80-120字的影片內容摘要，要能引起觀看興趣，突出影片亮點。",
          "標籤建議": ["#相關標籤1", "#熱門標籤2", "#台灣", "#影片", "#創作", "#生活", "#有趣", "#推薦"],
          "關鍵字": ["關鍵字1", "關鍵字2", "關鍵字3"],
          "情感分析": "正面/中性/負面",
          "內容類型": "娛樂/教育/生活/其他"
        }}
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system", 
                        "content": "你是一位專業的台灣短影音行銷專家，擅長分析影片內容並創造吸引人的標題、摘要和標籤。你了解台灣網路文化和流行趨勢。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=2000,
                top_p=0.9
            )
            
            ai_content = response.choices[0].message.content
            ai_data = json.loads(ai_content)
            
            # 更新任務數據
            self.task.ai_title_suggestions = ai_data.get("AI標題建議", [])[:5]
            self.task.ai_content_summary = ai_data.get("內容摘要", "")[:500]
            self.task.ai_tag_suggestions = ai_data.get("標籤建議", [])[:10]
            
            # 新增欄位
            self.task.keywords = ai_data.get("關鍵字", [])
            self.task.sentiment = ai_data.get("情感分析", "中性")
            self.task.content_type = ai_data.get("內容類型", "其他")
            
            logger.info("✅ 增強版 AI 內容生成成功")
            
        except Exception as e:
            logger.error(f"❌ AI 內容生成失敗: {e}")
            # 設置基本的 fallback 內容
            self._set_fallback_content()
    
    def _set_fallback_content(self):
        """設置備用內容（當 AI 失敗時）"""
        self.task.ai_title_suggestions = [
            f"精彩影片：{self.task.task_name}",
            f"必看內容 - {self.task.task_name}",
            f"最新影片分享：{self.task.task_name}"
        ]
        self.task.ai_content_summary = f"這是一部由 {self.task.videographer} 拍攝，{self.task.person_in_charge} 負責的影片：{self.task.task_name}。"
        self.task.ai_tag_suggestions = ["#影片", "#內容", "#分享", "#台灣"]
        
        logger.info("✅ 已設置備用內容")
    
    def process(self) -> Dict[str, Any]:
        """增強版處理流程"""
        start_time = datetime.now()
        logger.info("="*60)
        logger.info(f"🚀 開始執行增強版影片處理流程")
        logger.info(f"📋 任務 ID: {self.task.task_id}")
        logger.info(f"🎬 任務名稱: {self.task.task_name}")
        logger.info("="*60)
        
        transcript_data = None
        backup_paths = {}
        
        try:
            # 步驟 1: 下載影片和縮圖
            logger.info("📥 步驟 1/6: 下載影片")
            video_path, thumb_path = self._download_video()
            
            # 步驟 2: 提取影片幀（如果沒有縮圖）
            if not thumb_path:
                logger.info("🖼️ 步驟 2/6: 提取影片幀")
                thumb_path = self._extract_video_frame(video_path)
            else:
                logger.info("✅ 步驟 2/6: 已有縮圖，跳過幀提取")
            
            # 步驟 3: 備份到本地
            logger.info("📁 步驟 3/6: 備份檔案到 downloads")
            backup_paths = self._backup_to_downloads(video_path, thumb_path)
            
            # 步驟 4: 語音轉文字 (可選)
            logger.info("🎤 步驟 4/6: 語音轉文字")
            transcript_data = self._transcribe_with_whisper(video_path)
            
            # 步驟 5: 上傳到 R2（如果啟用）
            logger.info("☁️ 步驟 5/6: 上傳檔案到雲端")
            if self.r2_enabled:
                try:
                    self.task.processed_video_url = self._upload_to_r2(video_path, "videos")
                    if thumb_path:
                        self.task.processed_thumbnail_url = self._upload_to_r2(thumb_path, "thumbnails")
                except Exception as e:
                    logger.error(f"❌ R2 上傳失敗，使用本地備份: {e}")
                    self.task.processed_video_url = f"local://{backup_paths.get('video', video_path)}"
                    if thumb_path:
                        self.task.processed_thumbnail_url = f"local://{backup_paths.get('thumbnail', thumb_path)}"
            else:
                logger.info("📁 R2 未啟用，使用本地路徑")
                self.task.processed_video_url = f"local://{backup_paths.get('video', video_path)}"
                if thumb_path:
                    self.task.processed_thumbnail_url = f"local://{backup_paths.get('thumbnail', thumb_path)}"
            
            # 步驟 6: AI 分析（增強版）
            logger.info("🤖 步驟 6/6: AI 內容生成")
            self._enhanced_ai_content_with_transcript(transcript_data)
            
            # 更新最終狀態
            self.task.status = "完成"
            logger.info("🎉 增強版影片處理流程完全成功")
            
        except Exception as e:
            logger.error("❌ 處理過程中發生錯誤")
            logger.error(f"錯誤詳情: {str(e)}")
            
            self.task.status = "失敗"
            self.task.error_message = str(e)
            
            # 即使失敗也要設置備用內容
            self._set_fallback_content()
        
        finally:
            # 計算處理時間
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # 清理臨時檔案（但保留 downloads）
            self._cleanup()
            
            # 添加轉錄數據到結果
            result = asdict(self.task)
            if transcript_data:
                result['transcript'] = transcript_data
            result['backup_paths'] = backup_paths
            result['processing_time'] = duration
            
            logger.info("="*60)
            logger.info("📊 增強版處理結果摘要")
            logger.info("="*60)
            logger.info(f"⏱️ 總處理時間: {duration:.1f} 秒")
            logger.info(f"📄 任務 ID: {self.task.task_id}")
            logger.info(f"✅ 最終狀態: {self.task.status}")
            logger.info(f"📁 本地備份: {len(backup_paths)} 個檔案")
            if transcript_data:
                logger.info(f"🎤 轉錄文字: {len(transcript_data.get('text', ''))} 字元")
            logger.info("="*60)
            
            return result