from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate, DatetimePickerTemplateAction,
    PostbackEvent, PostbackTemplateAction, LocationSendMessage,
    CarouselTemplate, CarouselColumn, MessageAction, ImageSendMessage
)
import os
import json
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2 import service_account
import pytz

app = Flask(__name__)

# 從環境變數取得設定
channel_secret = os.environ.get('LINE_CHANNEL_SECRET', '您的 Channel Secret')
channel_access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '您的 Channel Access Token')

# Google Calendar API 設定
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
GOOGLE_CALENDAR_ID = os.environ.get('GOOGLE_CALENDAR_ID', 'primary')  # 預設使用主行事曆

# 設定時區為台灣時區
TW_TIMEZONE = pytz.timezone('Asia/Taipei')

# 初始化 Google Calendar 服務
def get_calendar_service():
    try:
        # 使用服務帳戶存取Google Calendar
        credentials_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if credentials_json:
            credentials_info = json.loads(credentials_json)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            service = build('calendar', 'v3', credentials=credentials)
            return service
        else:
            print("無法獲取Google行事曆憑證，請確認環境變數設置正確")
            return None
    except Exception as e:
        print(f"初始化Google Calendar失敗：{e}")
        return None

# 檢查指定時間是否有衝突
def check_calendar_conflict(date_str, time_str):
    service = get_calendar_service()
    if not service:
        return False  # 若無法連接服務，預設為無衝突
        
    # 將日期和時間轉換為RFC3339格式
    start_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    start_datetime = TW_TIMEZONE.localize(start_datetime)
    
    # 假設每次預約為1小時
    end_datetime = start_datetime + timedelta(hours=1)
    
    # 轉換為ISO格式
    start_iso = start_datetime.isoformat()
    end_iso = end_datetime.isoformat()
    
    try:
        # 查詢該時段是否有事件
        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=start_iso,
            timeMax=end_iso,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        return len(events) > 0  # 若有事件則有衝突
    except Exception as e:
        print(f"查詢行事曆失敗：{e}")
        return False  # 若查詢失敗，預設為無衝突

# 新增預約到Google行事曆
def add_booking_to_calendar(booking_info):
    service = get_calendar_service()
    if not service:
        return False
        
    try:
        date_str = booking_info['date']
        time_str = booking_info['time']
        manicurist_name = booking_info.get('manicurist_name', '')
        service_name = f"{booking_info.get('category', '')} - {booking_info.get('service', '')}"
        
        # 將日期和時間轉換為RFC3339格式
        start_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        start_datetime = TW_TIMEZONE.localize(start_datetime)
        
        # 假設每次預約為1小時
        end_datetime = start_datetime + timedelta(hours=1)
        
        # 建立事件
        event = {
            'summary': f'美甲預約：{service_name}',
            'description': f'客戶預約美甲服務\n美甲師：{manicurist_name}\n服務項目：{service_name}',
            'start': {
                'dateTime': start_datetime.isoformat(),
                'timeZone': 'Asia/Taipei',
            },
            'end': {
                'dateTime': end_datetime.isoformat(),
                'timeZone': 'Asia/Taipei',
            },
        }
        
        # 新增事件到行事曆
        event = service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
        print(f'預約已新增到行事曆: {event.get("htmlLink")}')
        return True
    except Exception as e:
        print(f"新增預約到行事曆失敗：{e}")
        return False

# 從Google行事曆中刪除預約
def remove_booking_from_calendar(booking_info):
    service = get_calendar_service()
    if not service:
        return False
        
    try:
        date_str = booking_info['date']
        time_str = booking_info['time']
        
        # 將日期和時間轉換為RFC3339格式
        start_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        start_datetime = TW_TIMEZONE.localize(start_datetime)
        
        # 假設每次預約為1小時
        end_datetime = start_datetime + timedelta(hours=1)
        
        # 轉換為ISO格式
        start_iso = start_datetime.isoformat()
        end_iso = end_datetime.isoformat()
        
        # 查詢該時段的事件
        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=start_iso,
            timeMax=end_iso,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # 尋找符合的預約並刪除
        for event in events:
            if '美甲預約' in event.get('summary', ''):
                service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=event['id']).execute()
                print(f'已從行事曆刪除預約: {event.get("summary")}')
                return True
                
        return False  # 未找到相符的預約
    except Exception as e:
        print(f"從行事曆刪除預約失敗：{e}")
        return False

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

# 儲存預約資訊 (實際應用建議使用資料庫)
bookings = {}

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
    "臉部護理": ["基礎護理", "深層清潔", "抗衰老護理", "亮白護理"],
    "美甲服務": ["基本美甲", "凝膠美甲", "卸甲服務"],
    "美髮服務": ["剪髮", "染髮", "燙髮", "護髮"]
}

# 營業時間
business_hours = {
    "start": 10,  # 上午 10 點
    "end": 20,    # 晚上 8 點
    "interval": 60 # 每個時段間隔(分鐘)
}

@app.route("/callback", methods=['POST'])
def callback():
    # 取得 X-Line-Signature header 值
    signature = request.headers['X-Line-Signature']

    # 取得請求內容
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # 處理 webhook
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip().lower()
    user_id = event.source.user_id

    if text == "預約" or text == "預約服務":
        # 修改流程：先選擇服務類別，最後選擇美甲師
        # 显示服务类别选单
        service_categories = list(services.keys())
        buttons_template = ButtonsTemplate(
            title='美甲服務預約',
            text='請選擇服務類別',
            actions=[
                PostbackTemplateAction(
                    label=category,
                    data=f"category_{category}"
                ) for category in service_categories
            ]
        )
        template_message = TemplateSendMessage(
            alt_text='服務類別選擇',
            template=buttons_template
        )
        line_bot_api.reply_message(event.reply_token, template_message)
    
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
            # 從Google行事曆中刪除預約
            remove_booking_from_calendar(bookings[user_id])
            
            # 從美甲師行事曆中移除預約
            if 'manicurist_id' in bookings[user_id]:
                manicurist_id = bookings[user_id]['manicurist_id']
                date = bookings[user_id].get('date')
                time = bookings[user_id].get('time')
                if date and time:
                    datetime_str = f"{date} {time}"
                    if datetime_str in manicurists[manicurist_id]['calendar']:
                        del manicurists[manicurist_id]['calendar'][datetime_str]
            
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
        message = "您好！我是美甲預約助手，可以幫您:\n1. 輸入「預約」開始預約\n2. 輸入「美甲師」查看美甲師資訊\n3. 輸入「地址」查看我們的位置\n4. 輸入「作品集」或「IG」查看作品\n5. 輸入「查詢預約」查看您的預約\n6. 輸入「取消預約」取消現有預約"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=message)
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    user_id = event.source.user_id
    
    # 處理服務類別選擇
    if data.startswith("category_"):
        category = data.replace("category_", "")
        
        # 儲存用戶選擇的類別
        if user_id not in bookings:
            bookings[user_id] = {}
        
        bookings[user_id]['category'] = category
        
        # 顯示此類別下的服務項目
        service_items = services[category]
        buttons_template = ButtonsTemplate(
            title=f'{category}服務',
            text='請選擇具體服務項目',
            actions=[
                PostbackTemplateAction(
                    label=service,
                    data=f"service_{service}"
                ) for service in service_items
            ]
        )
        template_message = TemplateSendMessage(
            alt_text='服務項目選擇',
            template=buttons_template
        )
        line_bot_api.reply_message(event.reply_token, template_message)
    
    # 處理服務項目選擇
    elif data.startswith("service_"):
        service = data.replace("service_", "")
        
        # 儲存用戶選擇的服務
        if user_id not in bookings:
            bookings[user_id] = {}
        
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
            text=f'您選擇了: {bookings[user_id].get("category", "")} - {service}\n請選擇預約日期',
            actions=[date_picker]
        )
        
        template_message = TemplateSendMessage(
            alt_text='日期選擇',
            template=buttons_template
        )
        
        line_bot_api.reply_message(event.reply_token, template_message)
    
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
        # 這裡簡化為只顯示部分時間段
        display_times = available_times[:4]  # 實際應用中可能需要分頁或其他解決方案
        
        buttons_template = ButtonsTemplate(
            title='選擇預約時間',
            text=f'預約日期: {selected_date}\n請選擇時間段',
            actions=[
                PostbackTemplateAction(
                    label=time_str,
                    data=f"time_{time_str}"
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
        selected_time = data.replace("time_", "")
        selected_date = bookings[user_id]['date']
        
        # 檢查Google行事曆是否有衝突
        has_conflict = check_calendar_conflict(selected_date, selected_time)
        
        if has_conflict:
            # 如果有衝突，通知客戶選擇其他時間
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"❌ 很抱歉，{selected_date} {selected_time} 這個時間已經有預約了。\n\n請選擇其他時間或日期預約。")
            )
            # 重新提供日期選擇
            return
        
        # 儲存選擇的時間
        bookings[user_id]['time'] = selected_time
        
        # 顯示可用的美甲師選擇
        datetime_str = f"{selected_date} {selected_time}"
        
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
            # 重新提供時間選擇
            return
        
        # 顯示可用的美甲師
        send_available_manicurists(event.reply_token, available_manicurists, datetime_str)
    
    # 處理美甲師選擇
    elif data.startswith("select_manicurist_"):
        parts = data.split("_")
        manicurist_id = parts[1]
        date_time = "_".join(parts[2:])  # 確保正確獲取日期時間信息
        
        # 檢查美甲師是否仍然可用
        if date_time in manicurists[manicurist_id]['calendar']:
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
        
        # 將預約添加到Google行事曆
        calendar_success = add_booking_to_calendar(booking_info)
        
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

# 顯示可用美甲師供客戶選擇
def send_available_manicurists(reply_token, available_manicurist_ids, datetime_str):
    columns = []
    for manicurist_id in available_manicurist_ids:
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

# 美甲師詳細資訊顯示函數
def send_manicurist_detail(reply_token, manicurist_id):
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

if __name__ == "__main__":
    # 注意：要更新美甲師照片，只需修改上面的manicurists字典中的image_url鏈接
    # 例如：修改 manicurists['1']['image_url'] = '新的照片URL'
    # 這樣可以隨時更新美甲師照片，而不需要修改程式碼其他部分
    
    channel_secret = '3d4224a4cb32b140610545e6d155cc0d'
    channel_access_token = 'YCffcEj/7aUw33XPEtfVMuKf1l5i5ztIHLibGTy2zGuyNgLf1RXJCqA8dVhbMp8Yxbwsr1CP6EfJID8htKS/Q3io/WSfp/gtDcaRfDT/TNErwymfiIdGWdLROcBkTfRN7hXFqHVrDQ+WgkkMGFWc3AdB04t89/1O/w1cDnyilFU='
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
