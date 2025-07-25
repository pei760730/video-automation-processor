# 短影音自動化處理系統 v2.1

基於NOTION標題結構優化的短影音自動化處理系統，支援影片下載、AI內容生成、雲端儲存等功能。

## 🚀 系統特色

### ✨ 核心功能
- **自動影片下載**: 支援多平台影片下載 (YouTube, TikTok, Instagram 等)
- **AI內容生成**: 使用 OpenAI GPT-4 生成標題、標籤、內容摘要
- **雲端儲存**: 自動上傳至 Cloudflare R2 儲存
- **Webhook回調**: 完成後自動通知 n8n 工作流程
- **結構化日誌**: 使用 structlog 提供詳細的處理日誌

### 🔧 系統優化
- **設定管理**: 統一的設定檔案管理系統
- **錯誤處理**: 完善的重試機制和錯誤捕獲
- **資料結構**: 使用 dataclass 確保資料一致性
- **效能優化**: 並行處理和資源管理
- **安全性**: 環境變數和秘鑰管理

## 📋 系統需求

### Python 版本
- Python 3.11 或更高版本

### 系統相依套件
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg libavcodec-extra libmagic1 mediainfo

# macOS
brew install ffmpeg libmagic mediainfo

# Windows
# 請下載 FFmpeg 並加入 PATH
```

### Python 套件
```bash
pip install -r requirements.txt
```

## ⚙️ 環境設定

### 必要環境變數

#### 任務基本資訊
```bash
VIDEO_URL=https://example.com/video          # 影片URL
TASK_NAME=我的短影音任務                      # 任務名稱
RESPONSIBLE_PERSON=張三                       # 負責人
PHOTOGRAPHER=李四                            # 攝影師
SHOOT_DATE=2025-01-15                        # 拍攝日期
GSHEET_ROW_INDEX=5                           # Google Sheets 行索引
```

#### API 設定
```bash
OPENAI_API_KEY=sk-xxx...                     # OpenAI API 金鑰
```

#### Cloudflare R2 設定
```bash
R2_ACCOUNT_ID=your_account_id                # R2 帳戶ID
R2_ACCESS_KEY=your_access_key                # R2 存取金鑰
R2_SECRET_KEY=your_secret_key                # R2 秘密金鑰
R2_BUCKET=your_bucket_name                   # R2 儲存桶名稱
R2_CUSTOM_DOMAIN=cdn.example.com             # R2 自訂網域 (可選)
```

#### Webhook 設定
```bash
N8N_WEBHOOK_URL=https://n8n.example.com/webhook/xxx  # n8n Webhook URL
N8N_WEBHOOK_SECRET=your_secret                        # Webhook 秘鑰 (可選)
```

### 可選環境變數

#### 進階設定
```bash
OPENAI_MODEL=gpt-4o-mini                     # OpenAI 模型 (預設: gpt-4o-mini)
MAX_FILE_SIZE=104857600                      # 最大檔案大小 (位元組, 預設