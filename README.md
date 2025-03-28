# LINE 美甲預約機器人

這是一個使用LINE Bot SDK建立的美甲預約機器人，可以讓客戶輕鬆預約美甲服務。

## 功能

- 查看美甲師資訊
- 選擇美甲服務
- 選擇預約日期和時間
- 選擇美甲師
- 確認預約
- 查詢/取消預約

## Google行事曆集成

此機器人可以與Google行事曆集成，以便根據美甲師的實際行程來接受或拒絕預約。

### 設置步驟

1. 創建Google Cloud項目並啟用Google Calendar API
2. 創建服務帳戶並下載JSON憑證文件
3. 設置以下環境變量：
   - `GOOGLE_APPLICATION_CREDENTIALS`: 指向服務帳戶JSON文件的路徑
   - `GOOGLE_CALENDAR_ID`: 要檢查的Google行事曆ID（通常是行事曆的email地址）

### 未設置Google行事曆環境變量時的行為

如果未設置Google行事曆環境變量，系統將使用硬編碼的測試數據：
- 2025-03-29: 全天忙碌
- 2025-03-30: 全天忙碌
- 2025-04-04: 上午10:00和10:30忙碌

## 部署

### 環境變量

- `LINE_CHANNEL_SECRET`: LINE Channel的Secret
- `LINE_CHANNEL_ACCESS_TOKEN`: LINE Channel的Access Token
- `PORT`: 伺服器端口 (默認為5000)
- `GOOGLE_APPLICATION_CREDENTIALS`: Google服務帳戶憑證文件路徑
- `GOOGLE_CALENDAR_ID`: Google行事曆ID

### 安裝依賴

```bash
pip install -r requirements.txt
```

### 啟動伺服器

```bash
python app.py
```

或使用gunicorn (生產環境):

```bash
gunicorn app:app
``` 
