#!/bin/bash
# 確保所有依賴都正確安裝
pip install --upgrade pip
pip install -r requirements.txt

# 清理pip緩存以節省空間
pip cache purge

# 確保Google API相關庫被正確安裝
pip install google-api-python-client google-auth google-auth-httplib2 google-auth-oauthlib python-dateutil --upgrade

# 顯示已安裝的包，用於調試
pip list

# 從環境變量創建Google服務帳戶憑證文件（如果提供）
if [ -n "$GOOGLE_APPLICATION_CREDENTIALS_JSON" ]; then
  echo "從環境變量創建Google服務帳戶憑證文件"
  echo "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > google-credentials.json
  export GOOGLE_APPLICATION_CREDENTIALS="./google-credentials.json"
  echo "已設置 GOOGLE_APPLICATION_CREDENTIALS=$GOOGLE_APPLICATION_CREDENTIALS"
else
  echo "未提供GOOGLE_APPLICATION_CREDENTIALS_JSON環境變量"
fi

# 顯示所有相關環境變量的狀態（不顯示實際值，僅顯示是否設置）
echo "環境變量狀態："
echo "GOOGLE_CALENDAR_ID: $(if [ -n "$GOOGLE_CALENDAR_ID" ]; then echo "已設置"; else echo "未設置"; fi)"
echo "GOOGLE_APPLICATION_CREDENTIALS: $(if [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then echo "已設置"; else echo "未設置"; fi)"
echo "LINE_CHANNEL_SECRET: $(if [ -n "$LINE_CHANNEL_SECRET" ]; then echo "已設置"; else echo "未設置"; fi)"
echo "LINE_CHANNEL_ACCESS_TOKEN: $(if [ -n "$LINE_CHANNEL_ACCESS_TOKEN" ]; then echo "已設置"; else echo "未設置"; fi)"

# 啟動服務
exec gunicorn app:app --log-file -
