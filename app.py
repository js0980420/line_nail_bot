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
    LocationSendMessage
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

@app.route("/", methods=['GET', 'HEAD'])
def health_check():
    """提供簡單的健康檢查端點，確認服務器是否正常運行"""
    logger.info("收到健康檢查請求")
    status = {
        "status": "ok",
        "line_bot": "initialized" if line_bot_api else "error"
    }
    return json.dumps(status)

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

# 處理 Postback 事件（保持不變）
@handler.add(PostbackEvent)
def handle_postback(event):
    try:
        data = event.postback.data
        user_id = event.source.user_id
        logger.info(f"收到來自用戶 {user_id} 的 postback: {data}")
        
        # 處理服務項目選擇
        if data.startswith("service_"):
            try:
                service = data.replace("service_", "")
                
                if user_id not in bookings:
                    bookings[user_id] = {}
                
                bookings[user_id]['category'] = "美甲服務"
                bookings[user_id]['service'] = service
                
                date_picker = DatetimePickerTemplateAction(
                    label='選擇日期',
                    data='action=date_picker',
                    mode='date',
                    initial=datetime.now().strftime('%Y-%m-%d'),
                    min=datetime.now().strftime('%Y-%m-%d'),
                    max=(datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
                )
                
                buttons_template = ButtonsTemplate(
                    title='選擇預約日期',
                    text=f'您選擇了: 美甲服務 - {service}\n請選擇預約日期',
                    actions=[date_picker]
                )
                
                template_message = TemplateSendMessage(
                    alt_text='日期選擇',
                    template=buttons_template
                )
                
                line_bot_api.reply_message(event.reply_token, template_message)
            except Exception as e:
                logger.error(f"處理服務選擇時出錯: {str(e)}")
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="抱歉，處理您的服務選擇時出現問題，請重新開始預約流程。")
                )
        
        # 處理日期選擇
        elif data == 'action=date_picker':
            selected_date = event.postback.params['date']
            
            bookings[user_id]['date'] = selected_date
            
            available_times = []
            for hour in range(business_hours['start'], business_hours['end']):
                for minute in [0, 30]:
                    time_str = f"{hour:02d}:{minute:02d}"
                    available_times.append(time_str)
            
            morning_times = [t for t in available_times if int(t.split(':')[0]) < 12]
            afternoon_times = [t for t in available_times if 12 <= int(t.split(':')[0]) < 17]
            evening_times = [t for t in available_times if int(t.split(':')[0]) >= 17]
            
            buttons_template = ButtonsTemplate(
                title='選擇時段',
                text=f'預約日期: {selected_date}\n請選擇大致時段',
                actions=[
                    PostbackTemplateAction(
                        label='上午 (10:00-12:00)',
                        data=f"timeperiod_morning_{selected_date}"
                    ),
                    PostbackTemplateAction(
                        label='下午 (12:00-17:00)',
                        data=f"timeperiod_afternoon_{selected_date}"
                    ),
                    PostbackTemplateAction(
                        label='晚上 (17:00-20:00)',
                        data=f"timeperiod_evening_{selected_date}"
                    )
                ]
            )
            
            template_message = TemplateSendMessage(
                alt_text='時段選擇',
                template=buttons_template
            )
            
            line_bot_api.reply_message(event.reply_token, template_message)
        
        # 處理時段選擇
        elif data.startswith("timeperiod_"):
            parts = data.split("_")
            period = parts[1]
            selected_date = parts[2]
            
            available_times = []
            for hour in range(business_hours['start'], business_hours['end']):
                for minute in [0, 30]:
                    time_str = f"{hour:02d}:{minute:02d}"
                    available_times.append(time_str)
            
            if period == "morning":
                display_times = [t for t in available_times if int(t.split(':')[0]) < 12]
                period_text = "上午"
            elif period == "afternoon":
                display_times = [t for t in available_times if 12 <= int(t.split(':')[0]) < 17]
                period_text = "下午"
            else:
                display_times = [t for t in available_times if int(t.split(':')[0]) >= 17]
                period_text = "晚上"
            
            display_times = display_times[:4]
            
            buttons_template = ButtonsTemplate(
                title=f'選擇{period_text}預約時間',
                text=f'預約日期: {selected_date}\n請選擇具體時間',
                actions=[
                    PostbackTemplateAction(
                        label=time_str,
                        data=f"time_{time_str}_{selected_date}"
                    ) for time_str in display_times
                ]
            )
            
            template_message = TemplateSendMessage(
                alt_text='時間選擇',
                template=buttons_template
            )
            
            line_bot_api.reply_message(event.reply_token, template_message)
        
        # 處理時間選擇
        elif data.startswith("time_"):
            parts = data.split("_")
            selected_time = parts[1]
            selected_date = parts[2] if len(parts) > 2 else bookings[user_id].get('date')
            
            if selected_date:
                bookings[user_id]['date'] = selected_date
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="發生錯誤，請重新選擇預約日期。")
                )
                return
            
            bookings[user_id]['time'] = selected_time
            
            datetime_str = f"{selected_date} {selected_time}"
            
            # 使用Google行事曆檢查是否有衝突
            try:
                is_busy = check_google_calendar(selected_date, selected_time)
                if is_busy:
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=f"❌ 很抱歉，美甲師在 {datetime_str} 這個時間已有行程，請選擇其他時間預約。")
                    )
                    return
            except Exception as e:
                logger.error(f"行事曆檢查失敗: {str(e)}")
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="行事曆查詢失敗，請聯絡工程師修改")
                )
                return
            
            # 檢查哪些美甲師在該時間可用
            available_manicurists = []
            for manicurist_id, manicurist in manicurists.items():
                if datetime_str not in manicurist['calendar']:
                    available_manicurists.append(manicurist_id)
            
            if not available_manicurists:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"❌ 很抱歉，{datetime_str} 這個時間所有美甲師都有預約了。\n\n請選擇其他時間或日期預約。")
                )
                return
            
            send_available_manicurists(event.reply_token, available_manicurists, datetime_str)
        
        # 處理美甲師選擇
        elif data.startswith("select_manicurist_"):
            try:
                parts = data.split("_")
                manicurist_id = parts[2]
                
                if manicurist_id not in manicurists:
                    logger.error(f"無效的美甲師ID: {manicurist_id}")
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="抱歉，您選擇的美甲師不存在，請重新開始預約流程。")
                    )
                    return
                
                date_time = '_'.join(parts[3:]) if len(parts) > 3 else ""
                
                if date_time and " " in date_time:
                    date_str, time_str = date_time.split(" ", 1)
                    try:
                        is_busy = check_google_calendar(date_str, time_str)
                        if is_busy:
                            line_bot_api.reply_message(
                                event.reply_token,
                                TextSendMessage(text=f"❌ 很抱歉，美甲師在 {date_time} 這個時間已有行程，請選擇其他時間預約。")
                            )
                            return
                    except Exception as e:
                        logger.error(f"行事曆檢查失敗: {str(e)}")
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(text="行事曆查詢失敗，請聯絡工程師修改")
                        )
                        return
                else:
                    date_str = bookings[user_id].get('date')
                    time_str = bookings[user_id].get('time')
                    if date_str and time_str:
                        try:
                            is_busy = check_google_calendar(date_str, time_str)
                            if is_busy:
                                line_bot_api.reply_message(
                                    event.reply_token,
                                    TextSendMessage(text=f"❌ 很抱歉，美甲師在 {date_str} {time_str} 這個時間已有行程，請選擇其他時間預約。")
                                )
                                return
                        except Exception as e:
                            logger.error(f"行事曆檢查失敗: {str(e)}")
                            line_bot_api.reply_message(
                                event.reply_token,
                                TextSendMessage(text="行事曆查詢失敗，請聯絡工程師修改")
                            )
                            return
                        date_time = f"{date_str} {time_str}"
                    else:
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(text="抱歉，無法確定您要預約的時間。請重新開始預約流程。")
                        )
                        return
                
                if date_time and date_time in manicurists[manicurist_id]['calendar']:
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=f"❌ 很抱歉，該美甲師剛剛被預約了這個時段，請重新選擇時間或其他美甲師。")
                    )
                    return
                
                bookings[user_id]['manicurist_id'] = manicurist_id
                bookings[user_id]['manicurist_name'] = manicurists[manicurist_id]['name']
                
                selected_date = bookings[user_id]['date']
                selected_time = bookings[user_id]['time']
                datetime_str = f"{selected_date} {selected_time}"
                manicurists[manicurist_id]['calendar'][datetime_str] = user_id
                
                title = "闆娘" if manicurist_id == '1' else manicurists[manicurist_id]['title']
                
                booking_info = bookings[user_id]
                
                calendar_result = add_event_to_calendar(user_id, booking_info)
                if calendar_result:
                    logger.info(f"已將預約添加到Google日曆: {booking_info}")
                else:
                    logger.warning(f"無法將預約添加到Google日曆，但預約仍然有效: {booking_info}")
                
                confirmation_message = (
                    f"🎊 您的預約已確認! 🎊\n\n"
                    f"✨ 美甲師: {booking_info['manicurist_name']} {title}\n"
                    f"💅 服務: {booking_info.get('category', '')} - {booking_info['service']}\n"
                    f"📅 日期: {booking_info['date']}\n"
                    f"🕒 時間: {booking_info['time']}\n\n"
                    f"如需變更，請輸入「取消預約」後重新預約。\n"
                    f"期待為您提供專業的美甲服務！"
                )
                
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=confirmation_message)
                )
            except Exception as e:
                logger.error(f"處理美甲師選擇時出錯: {str(e)}")
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="抱歉，處理您的美甲師選擇時出現問題，請重新開始預約流程。")
                )
        else:
            logger.warning(f"收到未知的 postback 數據: {data}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="抱歉，無法處理您的請求。請重新開始預約流程。")
            )

    except Exception as e:
        logger.error(f"處理 postback 時發生錯誤: {str(e)}")
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="很抱歉，處理您的選擇時發生錯誤，請重新開始。")
            )
        except Exception as inner_e:
            logger.error(f"傳送錯誤通知時發生錯誤: {str(inner_e)}")

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
        
        calendar_id = os.environ.get('GOOGLE_CALENDAR_ID', 'primary')
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

if __name__ == "__main__":
    logger.info("美甲預約機器人開始啟動...")
    
    try:
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
