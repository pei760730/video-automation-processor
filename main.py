# 檔案路徑: main.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
短影音自動化處理系統 - 主程式
優化版本 v2.1
"""

import sys
import json
import structlog
from src.video_processor import VideoProcessor # 從 src 資料夾匯入 VideoProcessor

# 取得在 video_processor.py 中設定的 logger
logger = structlog.get_logger(__name__)

def main():
    """主函數"""
    try:
        logger.info("短影音自動化處理系統啟動", version="v2.1")
        
        processor = VideoProcessor()
        result = processor.process_video_task()
        
        # 輸出結果給 GitHub Actions
        # 注意：::set-output 已被棄用，建議使用環境文件
        # GITHUB_OUTPUT 是一個文件路徑
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.getenv('GITHUB_OUTPUT'), 'a') as f:
                f.write(f"result={json.dumps(result, ensure_ascii=False)}\n")
        else:
             print(f"::set-output name=result::{json.dumps(result, ensure_ascii=False)}") # 舊版相容
        
        print("✅ 影片處理任務執行成功!")
        
        # 輸出關鍵資訊
        task_data = result.get('task_data', {})
        processing_stats = result.get('processing_stats', {})
        ai_content = result.get('ai_content', {})
        
        print(f"📋 任務名稱: {task_data.get('任務名稱', 'Unknown')}")
        print(f"⏱️ 處理時間: {processing_stats.get('processing_time', 'Unknown')}")
        print(f"📁 檔案大小: {processing_stats.get('video_size', 'Unknown')}")
        print(f"🎯 AI標題: {ai_content.get('標題建議', ['無'])[0]}")
        
    except Exception as e:
        logger.error("程式執行失敗", error=str(e))
        # GITHUB_STEP_SUMMARY 是一個文件路徑，可用來產生 Markdown 格式的摘要
        if os.getenv('GITHUB_STEP_SUMMARY'):
            with open(os.getenv('GITHUB_STEP_SUMMARY'), 'a') as f:
                f.write(f"## ❌ 處理失敗\n")
                f.write(f"**錯誤訊息:** `{str(e)}`\n")
        else:
            print(f"::error title=Processing Failed::{str(e)}") # 舊版相容

        sys.exit(1)

if __name__ == "__main__":
    main()