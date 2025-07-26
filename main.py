#!/usr/bin/env python3
"""
影片自動化處理系統 - 主程式
完整優化版：修正 R2 和 Notion 整合問題
版本: v2.2
"""

import os
import sys
import logging
import traceback
import signal
from pathlib import Path
from datetime import datetime

# 載入 .env 檔案
def load_env_file():
    """載入 .env 檔案中的環境變數"""
    try:
        # 嘗試使用 python-dotenv
        from dotenv import load_dotenv
        env_file = Path(__file__).parent / '.env'
        if env_file.exists():
            load_dotenv(env_file)
            print(f"✅ 已載入 .env 檔案 (dotenv): {env_file}")
        else:
            print(f"⚠️ 找不到 .env 檔案: {env_file}")
    except ImportError:
        # 如果沒有 python-dotenv，使用手動解析
        env_file = Path(__file__).parent / '.env'
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and value:
                            os.environ[key] = value
            print(f"✅ 已載入 .env 檔案 (手動): {env_file}")
        else:
            print(f"⚠️ 找不到 .env 檔案: {env_file}")

# 立即載入環境變數
load_env_file()

# 確保能找到 src 模組
sys.path.insert(0, str(Path(__file__).parent))

# 設定完整的日誌配置
def setup_logging():
    """設定詳細的日誌系統"""
    # 創建日誌目錄
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 設定日誌格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 設定根日誌器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 清除現有的處理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 控制台處理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 檔案處理器
    log_file = log_dir / f"process_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # 創建主日誌器
    logger = logging.getLogger(__name__)
    logger.info(f"📝 日誌系統初始化完成 - 日誌檔案: {log_file}")
    
    return logger

# 初始化日誌
logger = setup_logging()

def signal_handler(signum, frame):
    """處理系統信號（如 Ctrl+C）"""
    signal_names = {signal.SIGINT: 'SIGINT', signal.SIGTERM: 'SIGTERM'}
    signal_name = signal_names.get(signum, f'Signal {signum}')
    logger.warning(f"⚠️ 收到信號 {signal_name}，正在安全關閉程式...")
    sys.exit(130)

def validate_environment() -> tuple[bool, list[str], list[str]]:
    """
    完整的環境變數驗證
    返回: (是否有效, 錯誤清單, 警告清單)
    """
    logger.info("🔍 開始環境變數驗證...")
    
    errors = []
    warnings = []
    
    # === 核心必要變數 ===
    core_required = {
        'NOTION_PAGE_ID': 'Notion 頁面 ID（用於更新特定頁面）',
        'TASK_NAME': '任務名稱',
        'PERSON_IN_CHARGE': '負責人',
        'VIDEOGRAPHER': '攝影師',
        'ORIGINAL_LINK': '原始影片連結',
        'OPENAI_API_KEY': 'OpenAI API 金鑰'
    }
    
    logger.info("檢查核心必要變數：")
    for var, desc in core_required.items():
        value = os.environ.get(var)
        if not value:
            errors.append(f"❌ 缺少必要變數 {var} ({desc})")
            logger.error(f"❌ {var}: 未設置")
        else:
            # 隱藏敏感資訊
            if "KEY" in var or "SECRET" in var:
                display_value = f"***...{value[-4:]}" if len(value) > 4 else "***"
            else:
                display_value = value
            logger.info(f"✅ {var}: {display_value}")
    
    # === Notion 整合配置 ===
    notion_vars = {
        'NOTION_API_KEY': 'Notion API 金鑰',
        'NOTION_DATABASE_ID': 'Notion 資料庫 ID'
    }
    
    notion_configured = True
    logger.info("檢查 Notion 整合配置：")
    for var, desc in notion_vars.items():
        value = os.environ.get(var)
        if not value:
            notion_configured = False
            warnings.append(f"⚠️ Notion 變數 {var} 未設置 ({desc})")
            logger.warning(f"⚠️ {var}: 未設置")
        else:
            display_value = f"***...{value[-4:]}" if "KEY" in var and len(value) > 4 else value
            logger.info(f"✅ {var}: {display_value}")
    
    if not notion_configured:
        warnings.append("⚠️ Notion 整合將被停用")
        logger.warning("⚠️ Notion 整合配置不完整，相關功能將被停用")
    
    # === R2 雲端儲存配置 ===
    r2_vars = {
        'R2_ACCOUNT_ID': 'R2 帳戶 ID',
        'R2_ACCESS_KEY': 'R2 存取金鑰',
        'R2_SECRET_KEY': 'R2 秘密金鑰',
        'R2_BUCKET': 'R2 儲存桶名稱',
        'R2_CUSTOM_DOMAIN': 'R2 自定義域名（可選）'
    }
    
    r2_configured = True
    logger.info("檢查 R2 雲端儲存配置：")
    for var, desc in r2_vars.items():
        value = os.environ.get(var)
        is_required = var != 'R2_CUSTOM_DOMAIN'
        
        if not value:
            if is_required:
                r2_configured = False
                warnings.append(f"⚠️ R2 變數 {var} 未設置 ({desc})")
                logger.warning(f"⚠️ {var}: 未設置")
            else:
                logger.info(f"ℹ️ {var}: 未設置（可選）")
        else:
            if "KEY" in var:
                display_value = f"***...{value[-4:]}" if len(value) > 4 else "***"
            else:
                display_value = value
            logger.info(f"✅ {var}: {display_value}")
    
    if not r2_configured:
        warnings.append("⚠️ R2 雲端儲存將被停用，檔案將保存在本地")
        logger.warning("⚠️ R2 雲端儲存配置不完整，檔案將保存在本地")
    
    # === 可選進階配置 ===
    optional_vars = {
        'OPENAI_MODEL': 'OpenAI 模型（預設: gpt-4o-mini）',
        'MAX_VIDEO_SIZE_MB': '最大影片大小限制（預設: 500MB）',
        'PROCESSING_TIMEOUT': '處理超時時間（預設: 300秒）'
    }
    
    logger.info("檢查可選配置：")
    for var, desc in optional_vars.items():
        value = os.environ.get(var)
        if value:
            logger.info(f"✅ {var}: {value}")
        else:
            logger.info(f"ℹ️ {var}: 使用預設值 ({desc})")
    
    # === 驗證 URL 格式 ===
    original_link = os.environ.get('ORIGINAL_LINK')
    if original_link and not original_link.startswith(('http://', 'https://')):
        errors.append("❌ ORIGINAL_LINK 格式不正確，必須以 http:// 或 https:// 開頭")
        logger.error("❌ ORIGINAL_LINK 格式不正確")
    
    # === 總結驗證結果 ===
    is_valid = len(errors) == 0
    
    logger.info("="*60)
    logger.info("📋 環境驗證總結")
    logger.info("="*60)
    logger.info(f"✅ 核心配置: {'完整' if not errors else '不完整'}")
    logger.info(f"🔧 Notion 整合: {'啟用' if notion_configured else '停用'}")
    logger.info(f"☁️ R2 雲端儲存: {'啟用' if r2_configured else '停用'}")
    logger.info(f"📊 驗證結果: {'通過' if is_valid else '失敗'}")
    
    if errors:
        logger.info(f"❌ 錯誤數量: {len(errors)}")
    if warnings:
        logger.info(f"⚠️ 警告數量: {len(warnings)}")
    
    logger.info("="*60)
    
    return is_valid, errors, warnings

def print_system_info():
    """顯示系統資訊"""
    logger.info("="*60)
    logger.info("🖥️ 系統資訊")
    logger.info("="*60)
    
    # Python 版本
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    logger.info(f"🐍 Python 版本: {python_version}")
    
    # 平台資訊
    import platform
    logger.info(f"💻 作業系統: {platform.system()} {platform.release()}")
    logger.info(f"🏗️ 架構: {platform.machine()}")
    
    # 記憶體資訊（如果可用）
    try:
        import psutil
        memory = psutil.virtual_memory()
        logger.info(f"💾 可用記憶體: {memory.available / (1024**3):.1f} GB / {memory.total / (1024**3):.1f} GB")
    except ImportError:
        logger.info("💾 記憶體資訊: 無法取得（未安裝 psutil）")
    
    # 工作目錄
    logger.info(f"📁 工作目錄: {os.getcwd()}")
    logger.info(f"🗓️ 啟動時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    logger.info("="*60)

def print_task_summary():
    """顯示任務摘要"""
    logger.info("="*60)
    logger.info("📋 任務摘要")
    logger.info("="*60)
    logger.info(f"🎬 任務名稱: {os.environ.get('TASK_NAME', 'N/A')}")
    logger.info(f"🔗 影片連結: {os.environ.get('ORIGINAL_LINK', 'N/A')}")
    logger.info(f"👤 負責人: {os.environ.get('PERSON_IN_CHARGE', 'N/A')}")
    logger.info(f"📸 攝影師: {os.environ.get('VIDEOGRAPHER', 'N/A')}")
    logger.info(f"📄 Notion 頁面: {os.environ.get('NOTION_PAGE_ID', 'N/A')}")
    logger.info("="*60)

def check_dependencies():
    """檢查關鍵相依套件"""
    logger.info("🔍 檢查相依套件...")
    
    required_packages = {
        'yt_dlp': '影片下載',
        'openai': 'AI 內容生成',
        'boto3': 'R2 雲端儲存',
        'requests': 'HTTP 請求'
    }
    
    missing_packages = []
    
    for package, description in required_packages.items():
        try:
            __import__(package)
            logger.info(f"✅ {package}: 已安裝 ({description})")
        except ImportError:
            missing_packages.append(f"{package} ({description})")
            logger.error(f"❌ {package}: 未安裝")
    
    if missing_packages:
        logger.error("❌ 缺少必要套件，請執行: pip install -r requirements.txt")
        logger.error(f"缺少套件: {', '.join(missing_packages)}")
        return False
    
    logger.info("✅ 所有必要套件已安裝")
    return True

def main():
    """主程式入口"""
    # 設定信號處理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    start_time = datetime.now()
    exit_code = 0
    
    try:
        logger.info("🚀 啟動影片自動化處理系統 v2.2")
        logger.info(f"⏰ 啟動時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. 顯示系統資訊
        print_system_info()
        
        # 2. 檢查相依套件
        if not check_dependencies():
            logger.error("❌ 相依套件檢查失敗")
            return 1
        
        # 3. 環境變數驗證
        is_valid, errors, warnings = validate_environment()
        
        # 顯示所有錯誤和警告
        if errors:
            logger.error("❌ 環境配置錯誤:")
            for error in errors:
                logger.error(f"   {error}")
        
        if warnings:
            logger.warning("⚠️ 環境配置警告:")
            for warning in warnings:
                logger.warning(f"   {warning}")
        
        if not is_valid:
            logger.error("❌ 環境配置驗證失敗，程式終止")
            logger.error("請確認所有必要的環境變數都已正確設置")
            return 1
        
        # 4. 顯示任務資訊
        print_task_summary()
        
        # 5. 導入和初始化處理器
        try:
            logger.info("📦 載入處理器模組...")
            from src.notion_video_processor import NotionVideoProcessor
            logger.info("✅ NotionVideoProcessor 模組載入成功")
        except ImportError as e:
            logger.error(f"❌ 無法載入 NotionVideoProcessor: {e}")
            logger.error("請確認 src/notion_video_processor.py 檔案存在且語法正確")
            return 1
        except Exception as e:
            logger.error(f"❌ 載入模組時發生錯誤: {e}")
            logger.error(traceback.format_exc())
            return 1
        
        # 6. 執行處理流程
        try:
            logger.info("🎬 初始化影片處理器...")
            processor = NotionVideoProcessor()
            
            logger.info("⚡ 開始執行影片處理流程...")
            result = processor.process()
            
        except KeyboardInterrupt:
            logger.warning("⚠️ 使用者中斷程式執行")
            return 130
        except Exception as e:
            logger.error(f"❌ 處理器執行失敗: {e}")
            logger.error("完整錯誤堆疊:")
            logger.error(traceback.format_exc())
            return 1
        
        # 7. 分析處理結果
        processing_status = result.get('status', 'Unknown')
        task_id = result.get('task_id', 'N/A')
        error_message = result.get('error_message')
        
        # 計算總處理時間
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        logger.info("="*80)
        logger.info("🎯 最終處理結果")
        logger.info("="*80)
        logger.info(f"⏱️ 總執行時間: {total_duration:.1f} 秒")
        logger.info(f"📄 任務 ID: {task_id}")
        logger.info(f"📊 處理狀態: {processing_status}")
        
        # 根據狀態設定退出碼並顯示詳細結果
        if processing_status == "完成":
            logger.info("🎉 影片處理完全成功！")
            exit_code = 0
            
            # 顯示成功結果
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
                tags = result['ai_tag_suggestions'][:8]
                logger.info(f"🏷️ 標籤建議: {' '.join(tags)}")
                if len(result['ai_tag_suggestions']) > 8:
                    logger.info(f"   ... 等共 {len(result['ai_tag_suggestions'])} 個標籤")
            
        elif processing_status == "部分完成":
            logger.warning("⚠️ 影片處理部分成功")
            exit_code = 2
            
            if error_message:
                logger.warning(f"錯誤訊息: {error_message}")
            
            # 顯示成功的部分
            if result.get('ai_title_suggestions'):
                logger.info(f"✅ AI 內容生成成功 ({len(result['ai_title_suggestions'])} 個標題)")
            if result.get('processed_video_url'):
                logger.info("✅ 影片下載成功")
            
        elif processing_status == "失敗":
            logger.error("❌ 影片處理失敗")
            exit_code = 1
            
            if error_message:
                logger.error(f"失敗原因: {error_message}")
            
        else:
            logger.warning(f"⚠️ 未知的處理狀態: {processing_status}")
            exit_code = 3
        
        # 顯示系統使用統計（如果可用）
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            logger.info(f"📈 記憶體使用: {memory_info.rss / (1024**2):.1f} MB")
            logger.info(f"⏱️ CPU 時間: {process.cpu_times().user:.2f} 秒")
        except ImportError:
            pass
        
        logger.info("="*80)
        
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
    
    finally:
        # 計算並記錄總執行時間
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        logger.info(f"🕐 程式總執行時間: {total_duration:.2f} 秒")

if __name__ == "__main__":
    # 設定 Python 路徑
    current_dir = Path(__file__).parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    
    # 執行主程式
    exit_code = main()
    sys.exit(exit_code)