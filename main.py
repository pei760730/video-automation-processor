"""
影片自動化處理系統 - 主程式
完整優化版：穩定可靠的完整工作流，整合 Notion 更新功能
"""

import os
import sys
import logging
import traceback
from pathlib import Path
from datetime import datetime

# 確保能找到 src 模組
sys.path.insert(0, str(Path(__file__).parent))

# 設定詳細日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('process.log', mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

def validate_environment() -> bool:
    """驗證環境變數配置"""
    logger.info("🔍 驗證環境配置...")
    
    # 必要環境變數
    required_vars = {
        'NOTION_PAGE_ID': '用來更新 Notion 特定頁面的 ID',
        'TASK_NAME': '任務名稱',
        'PERSON_IN_CHARGE': '負責人',
        'VIDEOGRAPHER': '攝影師',
        'ORIGINAL_LINK': '原始影片連結',
        'OPENAI_API_KEY': 'OpenAI API 金鑰'
    }
    
    # 可選環境變數
    optional_vars = {
        # Notion 整合
        'NOTION_API_KEY': 'Notion API 金鑰',
        'NOTION_DATABASE_ID': 'Notion 資料庫 ID',
        
        # R2 雲端儲存
        'R2_ACCOUNT_ID': 'R2 帳戶 ID',
        'R2_ACCESS_KEY': 'R2 存取金鑰',
        'R2_SECRET_KEY': 'R2 秘密金鑰',
        'R2_BUCKET': 'R2 儲存桶名稱',
        'R2_CUSTOM_DOMAIN': 'R2 自定義域名'
    }
    
    # 檢查必要變數
    missing_required = []
    for var, desc in required_vars.items():
        value = os.environ.get(var)
        if not value:
            missing_required.append(f"{var} ({desc})")
            logger.error(f"❌ 缺少必要環境變數: {var}")
        else:
            display_value = "***" if "KEY" in var else value
            logger.info(f"✅ {var}: {display_value}")
    
    # 檢查可選變數
    missing_notion = []
    missing_r2 = []
    
    for var, desc in optional_vars.items():
        value = os.environ.get(var)
        if not value:
            if var.startswith('NOTION_'):
                missing_notion.append(f"{var} ({desc})")
            elif var.startswith('R2_'):
                missing_r2.append(f"{var} ({desc})")
        else:
            display_value = "***" if "KEY" in var or "SECRET" in var else value
            logger.info(f"✅ {var}: {display_value}")
    
    # 記錄缺少的可選配置
    if missing_notion:
        logger.warning("⚠️ Notion 整合未完整配置，將跳過 Notion 頁面更新")
        for missing in missing_notion:
            logger.warning(f"   - 缺少: {missing}")
    
    if missing_r2:
        logger.warning("⚠️ R2 雲端儲存未完整配置，檔案將保存在本地")
        for missing in missing_r2:
            logger.warning(f"   - 缺少: {missing}")
    
    if missing_required:
        logger.error("❌ 環境配置驗證失敗")
        return False
    
    logger.info("✅ 環境配置驗證通過")
    return True

def print_task_summary():
    """顯示任務摘要"""
    logger.info("="*60)
    logger.info("📋 任務摘要")
    logger.info("="*60)
    logger.info(f"🎬 任務名稱: {os.environ.get('TASK_NAME')}")
    logger.info(f"🔗 影片連結: {os.environ.get('ORIGINAL_LINK')}")
    logger.info(f"👤 負責人: {os.environ.get('PERSON_IN_CHARGE')}")
    logger.info(f"📸 攝影師: {os.environ.get('VIDEOGRAPHER')}")
    logger.info(f"📄 Notion 頁面 ID: {os.environ.get('NOTION_PAGE_ID')}")
    logger.info(f"🗓️ 開始時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)

def print_system_capabilities():
    """顯示系統能力狀態"""
    logger.info("⚙️ 系統功能狀態:")
    
    # 核心功能
    logger.info("   ✅ 影片下載 (yt-dlp)")
    logger.info("   ✅ AI 內容生成 (OpenAI)")
    
    # 可選功能
    notion_api_key = os.environ.get('NOTION_API_KEY')
    notion_db_id = os.environ.get('NOTION_DATABASE_ID')
    if notion_api_key and notion_db_id:
        logger.info("   ✅ Notion 整合")
    else:
        logger.info("   ⚠️ Notion 整合 (已停用)")
    
    r2_account = os.environ.get('R2_ACCOUNT_ID')
    r2_access = os.environ.get('R2_ACCESS_KEY')
    r2_secret = os.environ.get('R2_SECRET_KEY')
    r2_bucket = os.environ.get('R2_BUCKET')
    if all([r2_account, r2_access, r2_secret, r2_bucket]):
        logger.info("   ✅ R2 雲端儲存")
    else:
        logger.info("   ⚠️ R2 雲端儲存 (已停用)")

def main():
    """主程式入口"""
    start_time = datetime.now()
    exit_code = 0
    
    try:
        logger.info("🚀 啟動影片自動化處理系統 v2.1")
        
        # 1. 環境驗證
        if not validate_environment():
            logger.error("❌ 環境配置不完整，程式終止")
            return 1
        
        # 2. 顯示系統狀態
        print_system_capabilities()
        
        # 3. 顯示任務資訊
        print_task_summary()
        
        # 4. 導入處理器
        try:
            from src.notion_video_processor import NotionVideoProcessor
            logger.info("✅ NotionVideoProcessor 模組載入成功")
        except ImportError as e:
            logger.error(f"❌ 無法載入 NotionVideoProcessor: {e}")
            logger.error("請確認 src/notion_video_processor.py 檔案存在且語法正確")
            return 1
        
        # 5. 初始化並執行處理器
        try:
            logger.info("🎬 初始化影片處理器...")
            processor = NotionVideoProcessor()
            
            logger.info("⚡ 開始執行影片處理流程...")
            result = processor.process()
            
        except Exception as e:
            logger.error(f"❌ 處理器執行失敗: {e}")
            logger.error(traceback.format_exc())
            return 1
        
        # 6. 分析處理結果
        processing_status = result.get('status', 'Unknown')
        task_id = result.get('task_id', 'N/A')
        
        logger.info("="*60)
        logger.info("🎯 最終處理結果")
        logger.info("="*60)
        
        # 計算總處理時間
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        logger.info(f"⏱️ 總執行時間: {total_duration:.1f} 秒")
        logger.info(f"📄 任務 ID: {task_id}")
        logger.info(f"📊 處理狀態: {processing_status}")
        
        # 根據狀態顯示詳細結果
        if processing_status == "完成":
            logger.info("🎉 影片處理完全成功！")
            
            # 顯示處理結果
            if result.get('processed_video_url'):
                video_url = result['processed_video_url']
                if video_url.startswith('http'):
                    logger.info(f"🎥 影片連結: {video_url}")
                else:
                    logger.info(f"🎥 影片檔案: {video_url}")
            
            if result.get('processed_thumbnail_url'):
                thumb_url = result['processed_thumbnail_url']
                if thumb_url.startswith('http'):
                    logger.info(f"🖼️ 縮圖連結: {thumb_url}")
                else:
                    logger.info(f"🖼️ 縮圖檔案: {thumb_url}")
            
            if result.get('ai_content_summary'):
                summary = result['ai_content_summary']
                logger.info(f"📝 AI 摘要: {summary[:100]}{'...' if len(summary) > 100 else ''}")
            
            if result.get('ai_title_suggestions'):
                titles = result['ai_title_suggestions']
                logger.info(f"💡 標題建議數量: {len(titles)}")
                for i, title in enumerate(titles[:3], 1):
                    logger.info(f"   {i}. {title}")
                if len(titles) > 3:
                    logger.info(f"   ... 等共 {len(titles)} 個標題")
            
            if result.get('ai_tag_suggestions'):
                tags = result['ai_tag_suggestions'][:8]  # 顯示前8個標籤
                logger.info(f"🏷️ 標籤建議: {' '.join(tags)}")
                if len(result['ai_tag_suggestions']) > 8:
                    logger.info(f"   ... 等共 {len(result['ai_tag_suggestions'])} 個標籤")
            
            exit_code = 0
            
        elif processing_status == "部分完成":
            logger.warning("⚠️ 影片處理部分成功")
            error_msg = result.get('error_message', '未知錯誤')
            logger.warning(f"錯誤訊息: {error_msg}")
            
            # 仍然顯示成功的部分
            if result.get('ai_title_suggestions'):
                logger.info(f"✅ AI 內容生成成功 ({len(result['ai_title_suggestions'])} 個標題)")
            if result.get('processed_video_url'):
                logger.info("✅ 影片下載成功")
            
            exit_code = 2
            
        elif processing_status == "失敗":
            logger.error("❌ 影片處理失敗")
            error_msg = result.get('error_message', '未知錯誤')
            logger.error(f"失敗原因: {error_msg}")
            exit_code = 1
            
        else:
            logger.warning(f"⚠️ 未知的處理狀態: {processing_status}")
            exit_code = 3
        
        logger.info("="*60)
        
        if exit_code == 0:
            logger.info("🎊 影片自動化處理系統執行完畢")
        else:
            logger.warning(f"⚠️ 系統執行完畢，退出碼: {exit_code}")
        
        return exit_code
        
    except KeyboardInterrupt:
        logger.warning("⚠️ 使用者中斷程式執行")
        return 130
    
    except Exception as e:
        logger.error(f"❌ 系統發生未預期錯誤: {e}")
        logger.error(f"錯誤類型: {type(e).__name__}")
        logger.error("完整錯誤堆疊:")
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)