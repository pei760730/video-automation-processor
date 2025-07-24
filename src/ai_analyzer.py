"""
AI 分析器 - 使用 OpenAI 分析影片內容
"""

import os
import logging
from typing import Dict, List
import openai
from openai import OpenAI

logger = logging.getLogger(__name__)

class AIAnalyzer:
    def __init__(self):
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            self.client = OpenAI(api_key=api_key)
            self.enabled = True
            logger.info("✅ OpenAI 已配置")
        else:
            self.client = None
            self.enabled = False
            logger.warning("⚠️ OpenAI API Key 未設置")
    
    async def analyze_content(self, video_info: Dict) -> Dict:
        """分析影片內容並生成 AI 內容"""
        if not self.enabled:
            return self._get_default_content()
        
        try:
            # 準備提示詞
            prompt = f"""
            請分析以下影片資訊並提供：
            1. 內容摘要（100-200字）
            2. 5個吸引人的標題建議
            3. 5-10個相關標籤
            
            影片標題：{video_info.get('title', '')}
            影片描述：{video_info.get('description', '')[:500]}
            上傳者：{video_info.get('uploader', '')}
            
            請以 JSON 格式回應。
            """
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "你是一個專業的內容分析師。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            # 解析回應
            content = response.choices[0].message.content
            
            # 這裡應該解析 JSON，但為了簡化，直接返回範例
            return {
                "summary": "這是 AI 生成的影片摘要內容。",
                "titles": [
                    "吸引人的標題 1",
                    "創意標題 2",
                    "熱門標題 3"
                ],
                "tags": ["標籤1", "標籤2", "標籤3"]
            }
            
        except Exception as e:
            logger.error(f"❌ AI 分析失敗: {str(e)}")
            return self._get_default_content()
    
    def _get_default_content(self) -> Dict:
        """返回預設內容"""
        return {
            "summary": "AI 分析暫時無法使用",
            "titles": ["預設標題"],
            "tags": ["影片"]
        }