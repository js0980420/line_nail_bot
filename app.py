import os
import sys
import logging
from datetime import datetime, timedelta
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate, PostbackEvent,
    PostbackTemplateAction, DatetimePickerTemplateAction,
    CarouselTemplate, CarouselColumn, ImageSendMessage,
    LocationSendMessage, FollowEvent
)
import json
import requests
import werkzeug.exceptions  # 引入 werkzeug.exceptions

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 嘗試導入Google行事曆所需的庫，如果不存在則捕獲異常
GOOGLE_CALENDAR_AVAILABLE = False
calendar_service = None
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    import dateutil.parser
    import io
    
    # 初始化Google Calendar服務
    try:
        # 嘗試從JSON環境變量獲取憑證
        google_creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if google_creds_json:
            logger.info("找到 GOOGLE_APPLICATION_CREDENTIALS_JSON 環境變量")
            try:
                service_account_info = json.loads(google_creds_json)
                credentials = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=['https://www.googleapis.com/auth/calendar']
                )
                calendar_service = build('calendar', 'v3', credentials=credentials)
                GOOGLE_CALENDAR_AVAILABLE = True
                logger.info("Google Calendar API 從環境變量JSON初始化成功")
            except json.JSONDecodeError as e:
                logger.error(f"GOOGLE_APPLICATION_CREDENTIALS_JSON 格式錯誤: {str(e)}")
                GOOGLE_CALENDAR_AVAILABLE = False
        else:
            # 嘗試從文件路徑獲取憑證作為備選
            creds_file_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_file_path:
                logger.info(f"找到 GOOGLE_APPLICATION_CREDENTIALS 環境變量: {creds_file_path}")
                credentials = service_account.Credentials.from_service_account_file(
                    creds_file_path,
                    scopes=['https://www.googleapis.com/auth/calendar']
                )
                calendar_service = build('calendar', 'v3', credentials=credentials)
                GOOGLE_CALENDAR_AVAILABLE = True
                logger.info("Google Calendar API 從憑證文件初始化成功")
            else:
                logger.warning("未找到Google Calendar憑證，無法初始化API")
                GOOGLE_CALENDAR_AVAILABLE = False
    except Exception as e:
        logger.error(f"Google Calendar API 初始化失敗: {str(e)}")
        GOOGLE_CALENDAR_AVAILABLE = False
except ImportError:
    logger.error("Google Calendar API 依賴未安裝，無法初始化API")
    GOOGLE_CALENDAR_AVAILABLE = False

app = Flask(__name__)

# 處理 404 錯誤
@app.errorhandler(404)
def handle_404(e):
    logger.warning(f"404 錯誤: {str(e)}，請求路徑: {request.path}")
    return "Not Found", 404
    
# 全局異常處理（只處理其他異常）
@app.errorhandler(Exception)
def handle_exception(e):
    # 避免重複處理 404 錯誤
    if isinstance(e, werkzeug.exceptions.NotFound):
        return handle_404(e)
    logger.error(f"全局異常: {str(e)}，請求路徑: {request.path}")
    return "伺服器錯誤，請稍後再試", 500

# 修復健康檢查路由，支援 HEAD 和 GET 請求
@app.route("/", methods=['GET', 'HEAD'])
def health_check():
    """提供簡單的健康檢查端點，確認服務器是否正常運行"""
    logger.info("收到健康檢查請求")
    status = {
        "status": "ok",
        "line_bot": "initialized" if line_bot_api else "error"
    }
    return json.dumps(status), 200

# 從環境變數取得設定
channel_secret = os.environ.get('LINE_CHANNEL_SECRET', '您的 Channel Secret')
channel_access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '您的 Channel Access Token')

logger.info(f"Channel secret: {'已設定' if channel_secret else '未設定'}")
logger.info(f"Channel token: {'已設定' if channel_access_token else '未設定'}")

# 初始化LINE Bot API
try:
    line_bot_api = LineBotApi(channel_access_token)
    handler = WebhookHandler(channel_secret)
    logger.info("LINE Bot API 已成功初始化")
except Exception as e:
    logger.error(f"初始化LINE Bot API時發生錯誤: {e}")
    line_bot_api = None
    handler = WebhookHandler("dummy_secret")

# 美甲師資料 (實際應用建議使用資料庫)
manicurists = {
    '1': {
        'name': '王綺綺',
        'title': '闆娘',
        'bio': '台灣🇹🇼TNA指甲彩繪技能職類丙級🪪日本🇯🇵pregel 1級🪪日本🇯🇵pregel 2級🪪美甲美學｜足部香氛SPA｜',
        'image_url': 'https://example.com/images/wang_qiqi.jpg',
        'calendar': {}
    },
    '2': {
        'name': '李明美',
        'title': '資深美甲師',
        'bio': '擅長各種風格設計，提供客製化服務。專精日系美甲、法式美甲、寶石裝飾。',
        'image_url': 'https://example.com/images/li_mingmei.jpg',
        'calendar': {}
    },
    '3': {
        'name': '陳曉婷',
        'title': '美甲師',
        'bio': '擁有多年美甲經驗，提供專業手足護理和美甲服務。擅長手繪藝術及繁複設計。',
        'image_url': 'https://example.com/images/chen_xiaoting.jpg',
        'calendar': {}
    }
}

# 服務項目
services = {
    "美甲服務": ["基本美甲", "凝膠美甲", "卸甲服務", "手足護理", "光療美甲", "指甲彩繪"]
}

# 營業時間
business_hours = {
    "start": 10,
    "end": 20,
    "interval": 60
}

# 儲存預約資訊 (實際應用建議使用資料庫)
bookings = {}

@app.route("/callback", methods=['POST'], strict_slashes=False)
def callback():
    logger.info(f"收到 /callback 請求，方法: {request.method}, 路徑: {request.path}, 頭部: {request.headers}")
    try:
        # 取得 X-Line-Signature header 值
        signature = request.headers['X-Line-Signature']

        # 取得請求內容
        body = request.get_data(as_text=True)
        logger.info(f"收到webhook請求: {body[:100]}...")  # 只記錄前100個字符避免日誌過大

        # 處理 webhook
        try:
            handler.handle(body, signature)
        except InvalidSignatureError:
            logger.error("無效的簽名")
            abort(400)
        except Exception as e:
            logger.error(f"處理webhook時發生錯誤: {str(e)}")
            # 不中斷請求，返回 OK
            
        return 'OK'
    except Exception as e:
        logger.error(f"回呼函數發生錯誤: {str(e)}")
        return 'Error', 500

# 檢查Google行事曆是否有衝突
def check_google_calendar(date_str, time_str):
    """檢查指定日期和時間是否在Google日曆中有衝突
    
    Args:
        date_str: 日期字符串，格式為'YYYY-MM-DD'
        time_str: 時間字符串，格式為'HH:MM'
        
    Returns:
        bool: 如果有衝突返回True，否則返回False
        如果查詢失敗，拋出異常
    """
    try:
        logger.info(f"檢查日期時間是否有衝突: {date_str} {time_str}")
        
        # 檢查是否可使用Google API
        if not GOOGLE_CALENDAR_AVAILABLE or calendar_service is None:
            logger.error("Google Calendar API 不可用，無法檢查行事曆")
            raise Exception("Google Calendar API 不可用，無法檢查行事曆")
        
        calendar_id = os.environ.get('GOOGLE_CALENDAR_ID')
        if not calendar_id:
            logger.error("未設置 GOOGLE_CALENDAR_ID 環境變量")
            raise Exception("未設置 GOOGLE_CALENDAR_ID 環境變量")
        
        # 計算時間範圍
        start_time = f"{date_str}T{time_str}:00+08:00"  # 台灣時區
        end_time = datetime.fromisoformat(f"{date_str}T{time_str}:00")
        end_time = end_time + timedelta(minutes=30)  # 預約時間為30分鐘
        end_time = end_time.isoformat() + "+08:00"
        
        logger.info(f"檢查Google日曆從 {start_time} 到 {end_time}")
        
        # 查詢行事曆
        events_result = calendar_service.events().list(
            calendarId=calendar_id,
            timeMin=start_time,
            timeMax=end_time,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # 如果有任何事件，則表示有衝突
        if events:
            event_info = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                event_info.append(f"{event['summary']} at {start}")
            logger.info(f"在 {date_str} {time_str} 找到衝突: {', '.join(event_info)}")
            return True
        
        logger.info(f"Google日曆查詢顯示日期時間 {date_str} {time_str} 沒有衝突")
        return False
    except Exception as e:
        logger.error(f"檢查Google行事曆時出錯: {str(e)}")
        raise Exception(f"行事曆查詢失敗，請聯絡工程師修改: {str(e)}")

# 處理文字消息
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    try:
        text = event.message.text
        user_id = event.source.user_id
        logger.info(f"收到來自用戶 {user_id} 的文字消息: {text}")
        
        # 檢查是否正在處理中
        if user_id in bookings and 'processing' in bookings[user_id] and bookings[user_id]['processing']:
            logger.info(f"用戶 {user_id} 的請求正在處理中，忽略重複請求")
            return
        
        # 處理預約相關的文字命令
        if text == "預約" or text == "我要預約" or text == "美甲預約":
            # 設置處理中標記
            if user_id not in bookings:
                bookings[user_id] = {}
            bookings[user_id]['processing'] = True
            
            # 顯示服務選項
            carousel_template = CarouselTemplate(
                columns=[
                    CarouselColumn(
                        thumbnail_image_url="https://example.com/nail_art1.jpg",
                        title="基礎美甲服務",
                        text="選擇您想要的基礎美甲服務",
                        actions=[
                            PostbackTemplateAction(
                                label="基礎凝膠",
                                data="service_基礎凝膠"
                            ),
                            PostbackTemplateAction(
                                label="基礎保養",
                                data="service_基礎保養"
                            ),
                            PostbackTemplateAction(
                                label="卸甲服務",
                                data="service_卸甲服務"
                            )
                        ]
                    ),
                    CarouselColumn(
                        thumbnail_image_url="https://example.com/nail_art2.jpg",
                        title="進階美甲服務",
                        text="選擇您想要的進階美甲服務",
                        actions=[
                            PostbackTemplateAction(
                                label="法式凝膠",
                                data="service_法式凝膠"
                            ),
                            PostbackTemplateAction(
                                label="漸層凝膠",
                                data="service_漸層凝膠"
                            ),
                            PostbackTemplateAction(
                                label="鑽飾設計",
                                data="service_鑽飾設計"
                            )
                        ]
                    )
                ]
            )
            
            template_message = TemplateSendMessage(
                alt_text='美甲服務選擇',
                template=carousel_template
            )
            
            line_bot_api.reply_message(event.reply_token, template_message)
            
            # 重置處理中標記
            bookings[user_id]['processing'] = False
        
        # 處理取消預約的請求
        elif text == "取消預約" or text == "我要取消預約":
            # 設置處理中標記
            if user_id not in bookings:
                bookings[user_id] = {}
            bookings[user_id]['processing'] = True
            
            if user_id in bookings and 'date' in bookings[user_id] and 'time' in bookings[user_id]:
                booking_info = bookings[user_id]
                date_str = booking_info['date']
                time_str = booking_info['time']
                
                # 嘗試從Google日曆刪除事件
                if GOOGLE_CALENDAR_AVAILABLE:
                    try:
                        delete_result = delete_event_from_calendar(date_str, time_str)
                        if delete_result:
                            logger.info(f"已從Google日曆刪除預約: {date_str} {time_str}")
                        else:
                            logger.warning(f"無法從Google日曆刪除預約: {date_str} {time_str}")
                    except Exception as e:
                        logger.error(f"刪除Google日曆事件時出錯: {str(e)}")
                
                # 從美甲師的日曆中移除預約
                if 'manicurist_id' in booking_info:
                    manicurist_id = booking_info['manicurist_id']
                    datetime_str = f"{date_str} {time_str}"
                    if manicurist_id in manicurists and datetime_str in manicurists[manicurist_id]['calendar']:
                        del manicurists[manicurist_id]['calendar'][datetime_str]
                
                # 清除預約信息
                del bookings[user_id]
                
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="您的預約已成功取消。期待您的下次光臨！")
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="您目前沒有完整的預約信息。如需預約，請輸入「預約」。")
                )
            
            # 重置處理中標記
            bookings[user_id]['processing'] = False
        
        # 處理查詢預約的請求
        elif text == "查詢預約" or text == "我的預約":
            # 設置處理中標記
            if user_id not in bookings:
                bookings[user_id] = {}
            bookings[user_id]['processing'] = True
            
            if user_id in bookings and 'date' in bookings[user_id] and 'time' in bookings[user_id]:
                booking_info = bookings[user_id]
                manicurist_name = booking_info.get('manicurist_name', '未指定')
                manicurist_id = booking_info.get('manicurist_id', '未指定')
                title = "闆娘" if manicurist_id == '1' else manicurists.get(manicurist_id, {}).get('title', '')
                
                confirmation_message = (
                    f"🔍 您的預約信息如下:\n\n"
                    f"✨ 美甲師: {manicurist_name} {title}\n"
                    f"💅 服務: {booking_info.get('category', '')} - {booking_info.get('service', '未指定')}\n"
                    f"📅 日期: {booking_info['date']}\n"
                    f"🕒 時間: {booking_info['time']}\n\n"
                    f"如需變更，請輸入「取消預約」後重新預約。"
                )
                
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=confirmation_message)
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="您目前沒有預約。如需預約，請輸入「預約」。")
                )
            
            # 重置處理中標記
            bookings[user_id]['processing'] = False
        
        # 處理其他文字消息
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="您好！如需預約美甲服務，請輸入「預約」。\n如需查詢預約，請輸入「查詢預約」。\n如需取消預約，請輸入「取消預約」。")
            )
    
    except Exception as e:
        logger.error(f"處理文字消息時發生錯誤: {str(e)}")
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="很抱歉，處理您的訊息時發生錯誤，請稍後再試。")
            )
        except Exception as inner_e:
            logger.error(f"回覆錯誤訊息時發生異常: {str(inner_e)}")

# 添加定時任務功能，用於發送預約提醒
def send_appointment_reminder():
    """
    檢查即將到來的預約並發送提醒
    此函數應該由定時任務調用，例如每小時執行一次
    """
    if not GOOGLE_CALENDAR_AVAILABLE or calendar_service is None:
        logger.error("Google Calendar API 不可用，無法檢查即將到來的預約")
        return
    
    try:
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        start_time = now.isoformat() + "Z"
        end_time = tomorrow.isoformat() + "Z"
        
        calendar_id = os.environ.get('GOOGLE_CALENDAR_ID', 'primary')
        
        events_result = calendar_service.events().list(
            calendarId=calendar_id,
            timeMin=start_time,
            timeMax=end_time,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        for event in events:
            try:
                # 從事件描述中提取用戶ID
                description = event.get('description', '')
                user_id_match = None
                for line in description.split('\n'):
                    if line.startswith('客戶 ID:'):
                        user_id_match = line.replace('客戶 ID:', '').strip()
                        break
                
                if not user_id_match:
                    continue
                
                # 獲取事件開始時間
                start_time = event['start'].get('dateTime')
                if not start_time:
                    continue
                
                # 解析事件時間
                event_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                
                # 計算事件距離現在的時間
                time_diff = event_time - now
                hours_remaining = time_diff.total_seconds() / 3600
                
                # 如果事件在2小時內，發送提醒
                if 0 < hours_remaining <= 2:
                    service_name = event.get('summary', '美甲服務')
                    event_time_str = event_time.strftime('%Y-%m-%d %H:%M')
                    
                    reminder_message = (
                        f"⏰ 預約提醒 ⏰\n\n"
                        f"您的{service_name}預約將在約 {int(hours_remaining)} 小時後開始。\n"
                        f"預約時間: {event_time_str}\n\n"
                        f"期待為您提供專業的美甲服務！"
                    )
                    
                    try:
                        line_bot_api.push_message(
                            user_id_match,
                            TextSendMessage(text=reminder_message)
                        )
                        logger.info(f"已發送預約提醒給用戶 {user_id_match}, 預約時間: {event_time_str}")
                    except Exception as e:
                        logger.error(f"發送提醒給用戶 {user_id_match} 時出錯: {str(e)}")
            
            except Exception as e:
                logger.error(f"處理事件提醒時出錯: {str(e)}")
    
    except Exception as e:
        logger.error(f"檢查即將到來的預約時出錯: {str(e)}")

# 其他函數（保持不變）
# 添加日曆事件
def add_event_to_calendar(user_id, booking_data):
    if not GOOGLE_CALENDAR_AVAILABLE or calendar_service is None:
        logger.error("Google Calendar API 不可用，無法新增事件")
        return False
    
    try:
        date_str = booking_data.get('date')
        time_str = booking_data.get('time')
        if not date_str or not time_str:
            logger.error("預約數據中缺少日期或時間")
            return False
        
        start_datetime = f"{date_str}T{time_str}:00+08:00"
        end_time = datetime.fromisoformat(f"{date_str}T{time_str}:00")
        end_time = end_time + timedelta(minutes=30)
        end_datetime = end_time.isoformat() + "+08:00"
        
        manicurist_name = booking_data.get('manicurist_name', '未指定')
        manicurist_id = booking_data.get('manicurist_id', '未指定')
        
        event = {
            'summary': f"{booking_data.get('service', '美甲服務')} 預約 - {manicurist_name}",
            'location': '新北市永和區頂溪站1號出口附近',
            'description': (
                f"客戶 ID: {user_id}\n"
                f"服務: {booking_data.get('service', '未指定')}\n"
                f"美甲師: {manicurist_name} (ID: {manicurist_id})"
            ),
            'start': {
                'dateTime': start_datetime,
                'timeZone': 'Asia/Taipei',
            },
            'end': {
                'dateTime': end_datetime,
                'timeZone': 'Asia/Taipei',
            },
            'reminders': {
                'useDefault': True,
            },
        }
        
        # 獲取日曆ID，如果環境變量未設置，則使用 'primary'
        calendar_id = os.environ.get('GOOGLE_CALENDAR_ID', 'primary')
        
        # 嘗試插入事件前先記錄詳細信息
        logger.info(f"嘗試將事件添加到日曆 {calendar_id}，事件摘要: {event['summary']}")
        
        try:
            # 首先檢查服務帳戶是否有權限訪問該日曆
            calendar_service.calendars().get(calendarId=calendar_id).execute()
            logger.info(f"成功訪問日曆 {calendar_id}")
        except Exception as cal_error:
            logger.error(f"無法訪問日曆 {calendar_id}: {str(cal_error)}")
            
            # 如果指定的日曆無法訪問，嘗試使用服務帳戶的主日曆
            if calendar_id != 'primary':
                logger.info("嘗試使用服務帳戶的主日曆作為備選")
                calendar_id = 'primary'
        
        # 插入事件
        event = calendar_service.events().insert(calendarId=calendar_id, body=event).execute()
        logger.info(f"成功新增日曆事件: ID={event.get('id')}, 標題={event.get('summary')}")
        return True
    except Exception as e:
        logger.error(f"新增日曆事件失敗: {str(e)}")
        return False

# 從Google日曆刪除事件
def delete_event_from_calendar(date_str, time_str):
    if not GOOGLE_CALENDAR_AVAILABLE or calendar_service is None:
        logger.error("Google Calendar API 不可用，無法刪除事件")
        return False
    
    try:
        start_time = f"{date_str}T{time_str}:00+08:00"
        end_time = datetime.fromisoformat(f"{date_str}T{time_str}:00")
        end_time = end_time + timedelta(minutes=30)
        end_time = end_time.isoformat() + "+08:00"
        
        calendar_id = os.environ.get('GOOGLE_CALENDAR_ID', 'primary')
        
        events_result = calendar_service.events().list(
            calendarId=calendar_id,
            timeMin=start_time,
            timeMax=end_time,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        deleted_count = 0
        
        for event in events:
            event_id = event['id']
            calendar_service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            logger.info(f"已從Google日曆刪除事件: ID={event_id}, 標題={event.get('summary')}")
            deleted_count += 1
        
        return deleted_count > 0
    except Exception as e:
        logger.error(f"刪除Google日曆事件失敗: {str(e)}")
        return False

# 處理好友加入事件
@handler.add(FollowEvent)
def handle_follow(event):
    try:
        user_id = event.source.user_id
        logger.info(f"新用戶加入: {user_id}")
        
        # 發送歡迎訊息和服務選項
        welcome_message = (
            "👋 歡迎加入美甲預約系統！\n\n"
            "我們提供以下服務：\n"
            "💅 預約 - 立即預約美甲服務\n"
            "🔍 查詢預約 - 查看您的預約資訊\n"
            "❌ 取消預約 - 取消現有預約\n\n"
            "請選擇您需要的服務！"
        )
        
        # 顯示服務選項
        carousel_template = CarouselTemplate(
            columns=[
                CarouselColumn(
                    thumbnail_image_url="https://example.com/nail_art1.jpg",
                    title="基礎美甲服務",
                    text="選擇您想要的基礎美甲服務",
                    actions=[
                        PostbackTemplateAction(
                            label="基礎凝膠",
                            data="service_基礎凝膠"
                        ),
                        PostbackTemplateAction(
                            label="基礎保養",
                            data="service_基礎保養"
                        ),
                        PostbackTemplateAction(
                            label="卸甲服務",
                            data="service_卸甲服務"
                        )
                    ]
                ),
                CarouselColumn(
                    thumbnail_image_url="https://example.com/nail_art2.jpg",
                    title="進階美甲服務",
                    text="選擇您想要的進階美甲服務",
                    actions=[
                        PostbackTemplateAction(
                            label="法式凝膠",
                            data="service_法式凝膠"
                        ),
                        PostbackTemplateAction(
                            label="漸層凝膠",
                            data="service_漸層凝膠"
                        ),
                        PostbackTemplateAction(
                            label="鑽飾設計",
                            data="service_鑽飾設計"
                        )
                    ]
                )
            ]
        )
        
        template_message = TemplateSendMessage(
            alt_text='美甲服務選擇',
            template=carousel_template
        )
        
        # 先發送歡迎訊息
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=welcome_message)
        )
        
        # 然後發送服務選項
        line_bot_api.push_message(
            user_id,
            template_message
        )
        
    except Exception as e:
        logger.error(f"處理好友加入事件時發生錯誤: {str(e)}")

if __name__ == "__main__":
    logger.info("美甲預約機器人開始啟動...")
    
    try:
        # 載入 .env 檔案中的環境變數
        try:
            from dotenv import load_dotenv
            load_dotenv()
            logger.info("已載入 .env 檔案中的環境變數")
        except Exception as e:
            logger.warning(f"載入 .env 檔案失敗: {str(e)}")
        
        google_credentials_json = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        google_credentials_file = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        google_calendar_id = os.environ.get('GOOGLE_CALENDAR_ID')
        
        if google_credentials_json and google_calendar_id:
            logger.info("Google行事曆集成已設置(JSON方式)")
            logger.info(f"使用憑證JSON環境變量 (長度: {len(google_credentials_json)} 字符)")
            logger.info(f"使用行事曆ID: {google_calendar_id}")
        elif google_credentials_file and google_calendar_id:
            logger.info("Google行事曆集成已設置(文件方式)")
            logger.info(f"使用憑證文件: {google_credentials_file}")
            logger.info(f"使用行事曆ID: {google_calendar_id}")
        else:
            logger.warning("未設置Google行事曆環境變量")
            if not google_calendar_id:
                logger.warning("缺少 GOOGLE_CALENDAR_ID 環境變量")
            if not (google_credentials_json or google_credentials_file):
                logger.warning("缺少 GOOGLE_APPLICATION_CREDENTIALS_JSON 或 GOOGLE_APPLICATION_CREDENTIALS 環境變量")
        
        channel_secret_value = os.environ.get('LINE_CHANNEL_SECRET')
        channel_access_token_value = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
        
        if not channel_secret_value:
            logger.warning("警告: 未設定 LINE_CHANNEL_SECRET 環境變量")
            channel_secret_value = '3d4224a4cb32b140610545e6d155cc0d'
        
        if not channel_access_token_value:
            logger.warning("警告: 未設定 LINE_CHANNEL_ACCESS_TOKEN 環境變量")
            channel_access_token_value = 'YCffcEj/7aUw33XPEtfVMuKf1l5i5ztIHLibGTy2zGuyNgLf1RXJCqA8dVhbMp8Yxbwsr1CP6EfJID8htKS/Q3io/WSfp/gtDcaRfDT/TNErwymfiIdGWdLROcBkTfRN7hXFqHVrDQ+WgkkMGFWc3AdB04t89/1O/w1cDnyilFU='
        
        line_bot_api = LineBotApi(channel_access_token_value)
        handler = WebhookHandler(channel_secret_value)
        
        try:
            bot_info = line_bot_api.get_bot_info()
            logger.info(f"機器人成功連接: {bot_info.display_name} (ID: {bot_info.user_id})")
        except LineBotApiError as e:
            logger.error(f"機器人配置錯誤: {str(e)}")
            logger.warning("請檢查您的 Channel Secret 和 Access Token 是否正確")
        
        if GOOGLE_CALENDAR_AVAILABLE:
            logger.info("Google日曆API已成功初始化並可用")
            # 在啟動時執行一次提醒檢查
            try:
                send_appointment_reminder()
                logger.info("已執行預約提醒檢查")
            except Exception as e:
                logger.error(f"執行預約提醒檢查時出錯: {str(e)}")
        else:
            logger.error("Google日曆API未初始化或不可用，預約系統將無法檢查行事曆")
        
        if os.environ.get('PORT'):
            port = int(os.environ.get('PORT', 5000))
            logger.info(f"在雲端環境啟動，監聽端口 {port}")
            app.run(host='0.0.0.0', port=port)
        else:
            logger.info("在本地環境啟動，監聽端口 5000")
            app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        logger.error(f"啟動過程中發生錯誤: {str(e)}")
        sys.exit(1)
