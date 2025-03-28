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
            # 從環境變量中的JSON字符串創建臨時憑證
            service_account_info = json.loads(google_creds_json)
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            calendar_service = build('calendar', 'v3', credentials=credentials)
            GOOGLE_CALENDAR_AVAILABLE = True
            logging.info("Google Calendar API 從環境變量JSON初始化成功")
        else:
            # 嘗試從文件路徑獲取憑證作為備選
            creds_file_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_file_path:
                credentials = service_account.Credentials.from_service_account_file(
                    creds_file_path,
                    scopes=['https://www.googleapis.com/auth/calendar']
                )
                calendar_service = build('calendar', 'v3', credentials=credentials)
                GOOGLE_CALENDAR_AVAILABLE = True
                logging.info("Google Calendar API 從憑證文件初始化成功")
            else:
                logging.warning("未找到Google Calendar憑證，無法初始化API")
                GOOGLE_CALENDAR_AVAILABLE = False
    except Exception as e:
        logging.warning(f"Google Calendar API 初始化失敗: {str(e)}")
        GOOGLE_CALENDAR_AVAILABLE = False
except ImportError:
    logging.warning("Google Calendar API 依賴未安裝，將使用模擬數據")

app = Flask(__name__)

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局異常處理
@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"全局異常: {str(e)}")
    return "伺服器錯誤，請稍後再試", 500

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
    # 設置一個空的處理器，避免系統崩潰
    line_bot_api = None
    handler = WebhookHandler("dummy_secret")

# 美甲師資料 (實際應用建議使用資料庫)
manicurists = {
    '1': {
        'name': '王綺綺',
        'title': '闆娘',
        'bio': '台灣🇹🇼TNA指甲彩繪技能職類丙級🪪日本🇯🇵pregel 1級🪪日本🇯🇵pregel 2級🪪美甲美學｜足部香氛SPA｜',
        'image_url': 'https://example.com/images/wang_qiqi.jpg',  # 替換為真實照片URL
        'calendar': {}  # 用來儲存美甲師的預約行事曆
    },
    '2': {
        'name': '李明美',
        'title': '資深美甲師',
        'bio': '擅長各種風格設計，提供客製化服務。專精日系美甲、法式美甲、寶石裝飾。',
        'image_url': 'https://example.com/images/li_mingmei.jpg',  # 替換為真實照片URL
        'calendar': {}  # 用來儲存美甲師的預約行事曆
    },
    '3': {
        'name': '陳曉婷',
        'title': '美甲師',
        'bio': '擁有多年美甲經驗，提供專業手足護理和美甲服務。擅長手繪藝術及繁複設計。',
        'image_url': 'https://example.com/images/chen_xiaoting.jpg',  # 替換為真實照片URL
        'calendar': {}  # 用來儲存美甲師的預約行事曆
    }
}

# 服務項目
services = {
    "美甲服務": ["基本美甲", "凝膠美甲", "卸甲服務", "手足護理", "光療美甲", "指甲彩繪"]
}

# 營業時間
business_hours = {
    "start": 10,  # 上午 10 點
    "end": 20,    # 晚上 8 點
    "interval": 60 # 每個時段間隔(分鐘)
}

# 儲存預約資訊 (實際應用建議使用資料庫)
bookings = {}

@app.route("/", methods=['GET'])
def health_check():
    """提供簡單的健康檢查端點，確認服務器是否正常運行"""
    logger.info("收到健康檢查請求")
    status = {
        "status": "ok",
        "line_bot": "initialized" if line_bot_api else "error"
    }
    return json.dumps(status)

@app.route("/test", methods=['GET'])
def test_bot():
    """測試LINE Bot API是否正常工作"""
    logger.info("收到測試請求")
    try:
        # 獲取機器人資訊以測試連接
        bot_info = line_bot_api.get_bot_info()
        return json.dumps({
            "status": "ok",
            "bot_name": bot_info.display_name,
            "bot_user_id": bot_info.user_id
        })
    except Exception as e:
        logger.error(f"測試LINE Bot API失敗: {str(e)}")
        return json.dumps({
            "status": "error",
            "message": str(e)
        }), 500

@app.route("/callback", methods=['POST'])
def callback():
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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        text = event.message.text.strip().lower()
        user_id = event.source.user_id
        logger.info(f"收到來自用戶 {user_id} 的消息: {text}")
        
        # 基本回覆測試
        if text == "測試":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="機器人正常運作中！")
            )
            return

        # 原有功能
        if text == "預約" or text == "預約服務":
            try:
                # 直接顯示美甲服務選項，不顯示服務類別
                service_items = services["美甲服務"]
                
                # 最多只能顯示4個按鈕，因此需要分組顯示
                buttons_template = ButtonsTemplate(
                    title='美甲服務預約',
                    text='請選擇您需要的服務',
                    actions=[
                        PostbackTemplateAction(
                            label=service,
                            data=f"service_{service}"
                        ) for service in service_items[:4]  # 最多顯示4個
                    ]
                )
                
                template_message = TemplateSendMessage(
                    alt_text='美甲服務選擇',
                    template=buttons_template
                )
                
                # 如果服務項目多於4個，顯示查看更多按鈕
                if len(service_items) > 4:
                    additional_buttons = ButtonsTemplate(
                        title='更多美甲服務',
                        text='其他美甲服務選項',
                        actions=[
                            PostbackTemplateAction(
                                label=service,
                                data=f"service_{service}"
                            ) for service in service_items[4:min(8, len(service_items))]
                        ]
                    )
                    additional_message = TemplateSendMessage(
                        alt_text='更多美甲服務',
                        template=additional_buttons
                    )
                    
                    # 發送兩個模板消息
                    line_bot_api.reply_message(
                        event.reply_token,
                        [template_message, additional_message]
                    )
                    return
                
                line_bot_api.reply_message(event.reply_token, template_message)
                return
            except Exception as e:
                logger.error(f"預約服務顯示錯誤: {str(e)}")
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="抱歉，服務選項顯示出現問題，請稍後再試。")
                )
                return
        
        elif text == "美甲師":
            # 顯示所有美甲師資訊
            messages = []
            
            # 添加介紹文字
            intro_message = TextSendMessage(text="以下是我們的美甲師團隊：")
            messages.append(intro_message)
            
            # 為每位美甲師添加詳細資訊和照片
            for manicurist_id, manicurist in manicurists.items():
                if manicurist_id == '1':  # 特別介紹王綺綺闆娘
                    description = (
                        f"【{manicurist['name']} 闆娘】\n\n"
                        f"{manicurist['bio']}\n\n"
                        "闆娘擁有多年美甲經驗，專精於日式美甲設計和健康管理。"
                        "作為台灣國家認證的TNA指甲彩繪師和日本pregel雙認證技師，"
                        "不僅提供時尚精美的設計，更注重指甲的健康和保養。\n\n"
                        "擅長各種複雜設計和客製化服務，深受顧客喜愛。"
                    )
                else:
                    description = f"【{manicurist['name']} {manicurist['title']}】\n\n{manicurist['bio']}"
                
                text_message = TextSendMessage(text=description)
                image_message = ImageSendMessage(
                    original_content_url=manicurist['image_url'],
                    preview_image_url=manicurist['image_url']
                )
                
                messages.append(text_message)
                messages.append(image_message)
            
            # 添加預約提示
            messages.append(TextSendMessage(text="若要預約，請輸入「預約」開始預約流程"))
            
            line_bot_api.reply_message(event.reply_token, messages)
        
        elif text == "地址":
            # 顯示地址資訊
            location_message = LocationSendMessage(
                title='美甲工作室',
                address='新北市永和區頂溪站1號出口附近',
                latitude=25.011841,
                longitude=121.514514
            )
            line_bot_api.reply_message(
                event.reply_token,
                location_message
            )
        
        elif text in ["ig", "作品集"]:
            # 顯示作品集連結
            message = "歡迎參考我的作品集：\nhttps://www.instagram.com/j.innail/"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=message)
            )

        elif text == "查詢預約":
            # 查詢用戶預約
            if user_id in bookings:
                booking_info = bookings[user_id]
                
                # 獲取美甲師職稱
                manicurist_title = ""
                if 'manicurist_id' in booking_info:
                    manicurist_id = booking_info['manicurist_id']
                    if manicurist_id == '1':
                        manicurist_title = "闆娘"
                    elif manicurist_id in manicurists:
                        manicurist_title = manicurists[manicurist_id]['title']
                
                message = (
                    f"📋 您的預約資訊:\n\n"
                    f"✨ 美甲師: {booking_info.get('manicurist_name', '未選擇')} {manicurist_title}\n"
                    f"💅 服務: {booking_info.get('category', '未選擇')} - {booking_info.get('service', '未選擇')}\n"
                    f"📅 日期: {booking_info.get('date', '未選擇')}\n"
                    f"🕒 時間: {booking_info.get('time', '未選擇')}\n\n"
                    f"如需變更，請輸入「取消預約」後重新預約。"
                )
                
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=message)
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="❓ 您目前沒有預約。")
                )
        
        elif text == "取消預約":
            # 取消用戶預約
            if user_id in bookings:
                # 從美甲師行事曆中移除預約
                if 'manicurist_id' in bookings[user_id]:
                    manicurist_id = bookings[user_id]['manicurist_id']
                    date = bookings[user_id].get('date')
                    time = bookings[user_id].get('time')
                    if date and time:
                        datetime_str = f"{date} {time}"
                        if datetime_str in manicurists[manicurist_id]['calendar']:
                            del manicurists[manicurist_id]['calendar'][datetime_str]
                        
                        # 從Google日曆中刪除預約
                        calendar_deleted = delete_event_from_calendar(date, time)
                        if calendar_deleted:
                            logger.info(f"已從Google日曆刪除預約: 日期={date}, 時間={time}")
                        else:
                            logger.warning(f"無法從Google日曆刪除預約，但本地預約已刪除: 日期={date}, 時間={time}")
                
                # 刪除預約記錄
                del bookings[user_id]
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="✅ 您的預約已成功取消。")
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="❓ 您目前沒有預約。")
                )
        
        else:
            # 預設回覆
            message = "您好！我是美甲預約助手，可以幫您:\n1. 輸入「預約」開始預約\n2. 輸入「美甲師」查看美甲師資訊\n3. 輸入「地址」查看我們的位置\n4. 輸入「作品集」或「IG」查看作品\n5. 輸入「查詢預約」查看您的預約\n6. 輸入「取消預約」取消現有預約\n7. 輸入「測試」檢查機器人是否正常運作"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=message)
            )
    except InvalidSignatureError:
        logger.error("無效的簽名")
        raise
    except LineBotApiError as e:
        logger.error(f"LINE API 錯誤: {str(e)}")
        # 不需回覆，因為 LINE API 已經出錯
    except Exception as e:
        logger.error(f"處理消息時出錯: {str(e)}")
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="抱歉，系統暫時無法處理您的請求，請稍後再試。")
            )
        except Exception as reply_error:
            logger.error(f"無法發送錯誤回覆: {str(reply_error)}")

@handler.add(PostbackEvent)
def handle_postback(event):
    try:
        data = event.postback.data
        user_id = event.source.user_id
        logger.info(f"收到來自用戶 {user_id} 的 postback: {data}")
        
        # 直接處理服務項目選擇，不需要處理服務類別選擇
        if data.startswith("service_"):
            try:
                service = data.replace("service_", "")
                
                # 儲存用戶選擇的服務
                if user_id not in bookings:
                    bookings[user_id] = {}
                
                # 直接設定服務類別為"美甲服務"
                bookings[user_id]['category'] = "美甲服務"
                bookings[user_id]['service'] = service
                
                # 提供日期選擇
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
            
            # 儲存選擇的日期
            bookings[user_id]['date'] = selected_date
            
            # 提供時間選擇
            available_times = []
            for hour in range(business_hours['start'], business_hours['end']):
                for minute in [0, 30]:  # 假設每30分鐘一個時段
                    time_str = f"{hour:02d}:{minute:02d}"
                    available_times.append(time_str)
            
            # 由於 LINE 按鈕模板限制，最多只能顯示 4 個按鈕
            # 這裡分為早上、下午和晚上三個時段
            morning_times = [t for t in available_times if int(t.split(':')[0]) < 12]
            afternoon_times = [t for t in available_times if 12 <= int(t.split(':')[0]) < 17]
            evening_times = [t for t in available_times if int(t.split(':')[0]) >= 17]
            
            # 建立時段選擇
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
            period = parts[1]  # morning, afternoon, evening
            selected_date = parts[2]
            
            # 根據時段提供具體時間選擇
            available_times = []
            for hour in range(business_hours['start'], business_hours['end']):
                for minute in [0, 30]:  # 假設每30分鐘一個時段
                    time_str = f"{hour:02d}:{minute:02d}"
                    available_times.append(time_str)
            
            if period == "morning":
                display_times = [t for t in available_times if int(t.split(':')[0]) < 12]
                period_text = "上午"
            elif period == "afternoon":
                display_times = [t for t in available_times if 12 <= int(t.split(':')[0]) < 17]
                period_text = "下午"
            else:  # evening
                display_times = [t for t in available_times if int(t.split(':')[0]) >= 17]
                period_text = "晚上"
            
            # 最多只顯示4個時間選項
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
            
            # 確保日期已保存
            if selected_date:
                bookings[user_id]['date'] = selected_date
            else:
                # 如果沒有日期，返回錯誤
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="發生錯誤，請重新選擇預約日期。")
                )
                return
            
            # 儲存選擇的時間
            bookings[user_id]['time'] = selected_time
            
            # 顯示可用的美甲師選擇
            datetime_str = f"{selected_date} {selected_time}"
            
            # 使用Google行事曆檢查是否有衝突
            is_busy = check_google_calendar(selected_date, selected_time)
            if is_busy:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"❌ 很抱歉，美甲師在 {datetime_str} 這個時間已有行程，請選擇其他時間預約。")
                )
                return
            
            # 檢查哪些美甲師在該時間可用
            available_manicurists = []
            for manicurist_id, manicurist in manicurists.items():
                if datetime_str not in manicurist['calendar']:
                    available_manicurists.append(manicurist_id)
            
            if not available_manicurists:
                # 所有美甲師都不可用
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"❌ 很抱歉，{datetime_str} 這個時間所有美甲師都有預約了。\n\n請選擇其他時間或日期預約。")
                )
                return
            
            # 顯示可用的美甲師
            send_available_manicurists(event.reply_token, available_manicurists, datetime_str)
        
        # 處理美甲師選擇
        elif data.startswith("select_manicurist_"):
            try:
                parts = data.split("_")
                logger.info(f"美甲師選擇資料拆分: {parts}")
                
                manicurist_id = parts[2]  # 獲取美甲師ID
                logger.info(f"選擇的美甲師ID: {manicurist_id}")
                
                # 檢查美甲師ID是否有效
                if manicurist_id not in manicurists:
                    logger.error(f"無效的美甲師ID: {manicurist_id}")
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="抱歉，您選擇的美甲師不存在，請重新開始預約流程。")
                    )
                    return
                    
                logger.info(f"美甲師信息: {manicurists[manicurist_id]}")
                
                date_time = '_'.join(parts[3:]) if len(parts) > 3 else ""  # 獲取日期時間信息
                logger.info(f"選擇的日期時間: {date_time}")
                
                # 解析日期和時間
                if date_time and " " in date_time:
                    date_str, time_str = date_time.split(" ", 1)
                    # 再次使用Google行事曆檢查是否有衝突
                    is_busy = check_google_calendar(date_str, time_str)
                    if is_busy:
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(text=f"❌ 很抱歉，美甲師在 {date_time} 這個時間已有行程，請選擇其他時間預約。")
                        )
                        return
                else:
                    # 如果無法解析日期和時間，則從用戶預約數據中獲取
                    date_str = bookings[user_id].get('date')
                    time_str = bookings[user_id].get('time')
                    if date_str and time_str:
                        # 再次檢查是否有衝突
                        is_busy = check_google_calendar(date_str, time_str)
                        if is_busy:
                            line_bot_api.reply_message(
                                event.reply_token,
                                TextSendMessage(text=f"❌ 很抱歉，美甲師在 {date_str} {time_str} 這個時間已有行程，請選擇其他時間預約。")
                            )
                            return
                        # 更新日期時間字符串，用於後續檢查
                        date_time = f"{date_str} {time_str}"
                    else:
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(text="抱歉，無法確定您要預約的時間。請重新開始預約流程。")
                        )
                        return
                
                # 檢查美甲師是否仍然可用
                if date_time and date_time in manicurists[manicurist_id]['calendar']:
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=f"❌ 很抱歉，該美甲師剛剛被預約了這個時段，請重新選擇時間或其他美甲師。")
                    )
                    return
                    
                # 儲存用戶選擇的美甲師
                bookings[user_id]['manicurist_id'] = manicurist_id
                bookings[user_id]['manicurist_name'] = manicurists[manicurist_id]['name']
                
                # 更新美甲師行事曆
                selected_date = bookings[user_id]['date']
                selected_time = bookings[user_id]['time']
                datetime_str = f"{selected_date} {selected_time}"
                manicurists[manicurist_id]['calendar'][datetime_str] = user_id
                
                # 顯示職稱
                title = "闆娘" if manicurist_id == '1' else manicurists[manicurist_id]['title']
                
                # 完成預約
                booking_info = bookings[user_id]
                
                # 將預約添加到Google日曆
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
            except KeyError as ke:
                logger.error(f"處理美甲師選擇時發生 KeyError: {str(ke)}")
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="抱歉，無法完成預約，請確保您已選擇服務、日期和時間後再選擇美甲師。")
                )
            except Exception as e:
                logger.error(f"處理美甲師選擇時出錯: {str(e)}")
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="抱歉，處理您的美甲師選擇時出現問題，請重新開始預約流程。")
                )
        else:
            # 未知的 postback 數據
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

# 顯示可用美甲師供客戶選擇
def send_available_manicurists(reply_token, available_manicurist_ids, datetime_str):
    try:
        if not available_manicurist_ids:
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=f"❌ 很抱歉，{datetime_str} 這個時間所有美甲師都有預約了。\n\n請選擇其他時間或日期預約。")
            )
            return
            
        columns = []
        for manicurist_id in available_manicurist_ids:
            if manicurist_id not in manicurists:
                logger.warning(f"無效的美甲師ID: {manicurist_id}")
                continue
                
            manicurist = manicurists[manicurist_id]
            
            # 確保王綺綺顯示為闆娘
            display_title = '闆娘' if manicurist_id == '1' else manicurist['title']
            title = f"{manicurist['name']} {display_title}"
            text = manicurist['bio'][:60] + "..." if len(manicurist['bio']) > 60 else manicurist['bio']
            
            columns.append(
                CarouselColumn(
                    thumbnail_image_url=manicurist['image_url'],
                    title=title,
                    text=text,
                    actions=[
                        PostbackTemplateAction(
                            label=f"選擇 {manicurist['name']}",
                            data=f"select_manicurist_{manicurist_id}_{datetime_str}"
                        )
                    ]
                )
            )
        
        if not columns:
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=f"❌ 很抱歉，無法顯示美甲師資訊，請重新開始預約流程。")
            )
            return
            
        carousel_template = CarouselTemplate(columns=columns)
        template_message = TemplateSendMessage(
            alt_text='請選擇美甲師',
            template=carousel_template
        )
        
        # 修改消息，添加表情符號美化顯示
        line_bot_api.reply_message(
            reply_token,
            [
                TextSendMessage(text=f"✅ 您選擇的時間是: {datetime_str}\n\n請從以下美甲師中選擇一位為您服務："),
                template_message
            ]
        )
    except Exception as e:
        logger.error(f"顯示美甲師選項時出錯: {str(e)}")
        try:
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="抱歉，顯示美甲師選項時出現問題，請重新開始預約流程。")
            )
        except Exception as reply_error:
            logger.error(f"無法發送錯誤回覆: {str(reply_error)}")

# 美甲師詳細資訊顯示函數
def send_manicurist_detail(reply_token, manicurist_id):
    try:
        if manicurist_id not in manicurists:
            logger.error(f"請求顯示不存在的美甲師: {manicurist_id}")
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="抱歉，找不到該美甲師的資訊。")
            )
            return
            
        manicurist = manicurists[manicurist_id]
        
        # 為王綺綺闆娘添加更詳細的介紹
        if manicurist_id == '1':  # 王綺綺是ID為1的闆娘
            description = (
                f"【{manicurist['name']} 闆娘】\n\n"
                f"{manicurist['bio']}\n\n"
                "闆娘擁有多年美甲經驗，專精於日式美甲設計和健康管理。"
                "作為台灣國家認證的TNA指甲彩繪師和日本pregel雙認證技師，"
                "不僅提供時尚精美的設計，更注重指甲的健康和保養。\n\n"
                "擅長各種複雜設計和客製化服務，深受顧客喜愛。"
            )
        else:
            description = f"【{manicurist['name']} {manicurist['title']}】\n\n{manicurist['bio']}"
        
        # 準備圖片和文字訊息
        image_message = ImageSendMessage(
            original_content_url=manicurist['image_url'],
            preview_image_url=manicurist['image_url']
        )
        
        # 發送訊息
        line_bot_api.reply_message(
            reply_token,
            [
                TextSendMessage(text=description),
                image_message
            ]
        )
    except KeyError as ke:
        logger.error(f"美甲師資料缺少欄位: {str(ke)}")
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="抱歉，美甲師資料不完整，無法顯示。")
        )
    except Exception as e:
        logger.error(f"顯示美甲師詳細資訊時出錯: {str(e)}")
        try:
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="抱歉，顯示美甲師資訊時出現問題。")
            )
        except Exception as reply_error:
            logger.error(f"無法發送錯誤回覆: {str(reply_error)}")

# 檢查Google行事曆是否有衝突
def check_google_calendar(date_str, time_str):
    """檢查指定日期和時間是否在Google日曆中有衝突
    
    Args:
        date_str: 日期字符串，格式為'YYYY-MM-DD'
        time_str: 時間字符串，格式為'HH:MM'
        
    Returns:
        bool: 如果有衝突返回True，否則返回False
    """
    try:
        # 記錄檢查的日期和時間，方便調試
        logger.info(f"檢查日期時間是否有衝突: {date_str} {time_str}")
        
        # 檢查是否可使用Google API
        if not GOOGLE_CALENDAR_AVAILABLE:
            logger.warning("Google Calendar API 不可用，使用硬編碼的測試數據")
            # 硬編碼的特殊日期（模擬）
            special_dates = ["2025-03-29", "2025-03-30", "2025-04-04", "2025-04-05"]
            special_times = {
                "2025-04-04": ["10:00", "10:30"],
                "2025-04-05": ["10:00", "10:30", "11:00"]
            }
            
            # 檢查日期是否在特殊日期列表中
            if date_str in special_dates:
                # 如果是全天事件（如3/29, 3/30），直接返回有衝突
                if date_str in ["2025-03-29", "2025-03-30"]:
                    logger.info(f"日期 {date_str} 是全天事件，有衝突")
                    return True
                
                # 檢查時間是否在特殊時間列表中
                if date_str in special_times and time_str in special_times[date_str]:
                    logger.info(f"日期時間 {date_str} {time_str} 有衝突")
                    return True
            
            # 沒有衝突
            logger.info(f"日期時間 {date_str} {time_str} 沒有衝突")
            return False
        
        # 獲取環境變數中的憑證檔案路徑
        credential_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        calendar_id = os.environ.get('GOOGLE_CALENDAR_ID')
        
        # 如果沒有設定憑證，則使用硬編碼的預設值
        if not credential_path or not calendar_id:
            logger.warning("Google Calendar 憑證或日曆ID未設定，使用硬編碼的測試數據")
            special_dates = ["2025-03-29", "2025-03-30", "2025-04-04", "2025-04-05"]
            special_times = {
                "2025-04-04": ["10:00", "10:30"],
                "2025-04-05": ["10:00", "10:30", "11:00"]
            }
            
            is_conflict = (date_str in ["2025-03-29", "2025-03-30"]) or \
                         (date_str in special_times and time_str in special_times[date_str])
            
            if is_conflict:
                logger.info(f"硬編碼數據顯示日期時間 {date_str} {time_str} 有衝突")
            else:
                logger.info(f"硬編碼數據顯示日期時間 {date_str} {time_str} 沒有衝突")
                
            return is_conflict
        
        # 使用服務帳戶憑證
        credentials = service_account.Credentials.from_service_account_file(
            credential_path, 
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
        
        # 構建服務
        service = build('calendar', 'v3', credentials=credentials)
        
        # 計算時間範圍
        start_time = f"{date_str}T{time_str}:00+08:00"  # 台灣時區
        end_time = datetime.fromisoformat(f"{date_str}T{time_str}:00")
        end_time = end_time + timedelta(minutes=30)  # 預約時間為30分鐘
        end_time = end_time.isoformat() + "+08:00"
        
        logger.info(f"檢查Google日曆從 {start_time} 到 {end_time}")
        
        # 查詢行事曆
        events_result = service.events().list(
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
        # 發生錯誤時，假設沒有衝突以允許預約進行
        # 注意：在生產環境中可能需要調整此行為以更好地處理錯誤
        return False

# 添加日曆事件
def add_event_to_calendar(user_id, booking_data):
    """將預約添加到Google日曆
    
    Args:
        user_id: 用戶ID
        booking_data: 預約數據，包含服務、日期、時間、美甲師等信息
        
    Returns:
        bool: 是否成功添加事件
    """
    if not GOOGLE_CALENDAR_AVAILABLE or calendar_service is None:
        logger.error("Google Calendar API 不可用，無法新增事件")
        return False
    
    try:
        # 解析預約時間
        date_str = booking_data.get('date')
        time_str = booking_data.get('time')
        if not date_str or not time_str:
            logger.error("預約數據中缺少日期或時間")
            return False
        
        # 構建開始時間和結束時間
        start_datetime = f"{date_str}T{time_str}:00+08:00"  # 台灣時區
        # 預設預約時間為30分鐘
        end_time = datetime.fromisoformat(f"{date_str}T{time_str}:00")
        end_time = end_time + timedelta(minutes=30)
        end_datetime = end_time.isoformat() + "+08:00"
        
        # 提取美甲師信息
        manicurist_name = booking_data.get('manicurist_name', '未指定')
        manicurist_id = booking_data.get('manicurist_id', '未指定')
        
        # 構建事件數據
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
    """從Google日曆中刪除指定日期和時間的事件
    
    Args:
        date_str: 日期字符串，格式為'YYYY-MM-DD'
        time_str: 時間字符串，格式為'HH:MM'
        
    Returns:
        bool: 是否成功刪除事件
    """
    if not GOOGLE_CALENDAR_AVAILABLE or calendar_service is None:
        logger.error("Google Calendar API 不可用，無法刪除事件")
        return False
    
    try:
        # 構建時間範圍
        start_time = f"{date_str}T{time_str}:00+08:00"  # 台灣時區
        end_time = datetime.fromisoformat(f"{date_str}T{time_str}:00")
        end_time = end_time + timedelta(minutes=30)  # 預約時間為30分鐘
        end_time = end_time.isoformat() + "+08:00"
        
        calendar_id = os.environ.get('GOOGLE_CALENDAR_ID', 'primary')
        
        # 查詢該時間範圍內的事件
        events_result = calendar_service.events().list(
            calendarId=calendar_id,
            timeMin=start_time,
            timeMax=end_time,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        deleted_count = 0
        
        # 刪除找到的事件
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
    # 預約流程說明：
    # 1. 用戶直接選擇美甲服務項目
    # 2. 用戶選擇預約日期
    # 3. 用戶選擇時段（上午/下午/晚上）
    # 4. 用戶選擇具體時間
    # 5. 用戶選擇美甲師 (最後一步)
    # 6. 確認預約
    
    # Google行事曆集成說明：
    # 需要設置以下環境變量之一：
    # - GOOGLE_APPLICATION_CREDENTIALS_JSON: Google服務帳戶憑證的JSON內容
    # 或者
    # - GOOGLE_APPLICATION_CREDENTIALS: 指向服務帳戶JSON文件的路徑
    # 以及：
    # - GOOGLE_CALENDAR_ID: 要檢查的Google行事曆ID
    # 如果未設置這些環境變量，系統將使用硬編碼的測試數據
    
    logger.info("美甲預約機器人開始啟動...")
    
    try:
        # 檢查Google行事曆環境變量
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
            logger.warning("未設置Google行事曆環境變量，將使用硬編碼的測試數據")
            if not google_calendar_id:
                logger.warning("缺少 GOOGLE_CALENDAR_ID 環境變量")
            if not (google_credentials_json or google_credentials_file):
                logger.warning("缺少 GOOGLE_APPLICATION_CREDENTIALS_JSON 或 GOOGLE_APPLICATION_CREDENTIALS 環境變量")
        
        # 使用環境變數獲取配置
        channel_secret_value = os.environ.get('LINE_CHANNEL_SECRET')
        channel_access_token_value = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
        
        # 檢查是否設定了必要的環境變量
        if not channel_secret_value:
            logger.warning("警告: 未設定 LINE_CHANNEL_SECRET 環境變量，將使用配置文件中的值")
            channel_secret_value = '3d4224a4cb32b140610545e6d155cc0d'  # 這只是示例值，建議使用環境變量
            
        if not channel_access_token_value:
            logger.warning("警告: 未設定 LINE_CHANNEL_ACCESS_TOKEN 環境變量，將使用配置文件中的值")
            # 防止直接在源代碼中暴露完整的TOKEN，只顯示前10個字符
            channel_access_token_value = 'YCffcEj/7aUw33XPEtfVMuKf1l5i5ztIHLibGTy2zGuyNgLf1RXJCqA8dVhbMp8Yxbwsr1CP6EfJID8htKS/Q3io/WSfp/gtDcaRfDT/TNErwymfiIdGWdLROcBkTfRN7hXFqHVrDQ+WgkkMGFWc3AdB04t89/1O/w1cDnyilFU='
            logger.warning(f"使用默認TOKEN (前綴: {channel_access_token_value[:10]}...)")
        else:
            logger.info(f"使用環境變量的 LINE_CHANNEL_ACCESS_TOKEN (前綴: {channel_access_token_value[:10]}...)")
        
        # 重新初始化 LINE Bot API，確保使用正確的值
        line_bot_api = LineBotApi(channel_access_token_value)
        handler = WebhookHandler(channel_secret_value)
        
        # 測試LINE Bot配置
        try:
            bot_info = line_bot_api.get_bot_info()
            logger.info(f"機器人成功連接: {bot_info.display_name} (ID: {bot_info.user_id})")
        except LineBotApiError as e:
            logger.error(f"機器人配置錯誤: {str(e)}")
            logger.warning("請檢查您的 Channel Secret 和 Access Token 是否正確")
        
        # 檢查是否已設置正確的Google日曆憑證
        if GOOGLE_CALENDAR_AVAILABLE:
            logger.info("Google日曆API已成功初始化並可用")
        else:
            logger.warning("Google日曆API未初始化或不可用，預約系統將使用模擬數據進行行程衝突檢查")
        
        # 在雲端環境下啟動
        if os.environ.get('PORT'):
            port = int(os.environ.get('PORT', 5000))
            logger.info(f"在雲端環境啟動，監聽端口 {port}")
            app.run(host='0.0.0.0', port=port)
        else:
            # 在本地環境下啟動
            logger.info("在本地環境啟動，監聽端口 5000")
            app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        logger.error(f"啟動過程中發生錯誤: {str(e)}")
        logger.error("程序將退出")
        sys.exit(1)