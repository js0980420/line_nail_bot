from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate, DatetimePickerTemplateAction,
    PostbackEvent, PostbackTemplateAction
)
import os
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# 從環境變數取得設定
channel_secret = os.environ.get('LINE_CHANNEL_SECRET', '您的 Channel Secret')
channel_access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '您的 Channel Access Token')

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

# 儲存預約資訊 (實際應用建議使用資料庫)
bookings = {}

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
    text = event.message.text
    user_id = event.source.user_id

    if text == "預約服務":
        # 顯示服務類別選單
        service_categories = list(services.keys())
        buttons_template = ButtonsTemplate(
            title='美容服務預約',
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
    
    elif text == "查詢預約":
        # 查詢用戶預約
        if user_id in bookings:
            booking_info = bookings[user_id]
            message = f"您的預約資訊:\n服務: {booking_info['service']}\n日期: {booking_info['date']}\n時間: {booking_info['time']}"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=message)
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="您目前沒有預約。")
            )
    
    elif text == "取消預約":
        # 取消用戶預約
        if user_id in bookings:
            del bookings[user_id]
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="您的預約已取消。")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="您目前沒有預約。")
            )
    
    else:
        # 預設回覆
        message = "您好！我是美容預約助手，可以幫您:\n1. 輸入「預約服務」開始預約\n2. 輸入「查詢預約」查看您的預約\n3. 輸入「取消預約」取消現有預約"
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
        
        # 顯示此類別下的服務項目
        service_items = services[category]
        buttons_template = ButtonsTemplate(
            title=f'{category}服務',
            text='請選擇具體服務項目',
            actions=[
                PostbackTemplateAction(
                    label=service,
                    data=f"service_{category}_{service}"
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
        _, category, service = data.split("_", 2)
        
        # 儲存用戶選擇的服務
        if user_id not in bookings:
            bookings[user_id] = {}
        
        bookings[user_id]['category'] = category
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
            text=f'您選擇了: {category} - {service}\n請選擇預約日期',
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
        
        # 儲存選擇的時間
        bookings[user_id]['time'] = selected_time
        
        # 完成預約
        booking_info = bookings[user_id]
        confirmation_message = f"您的預約已確認!\n\n服務: {booking_info['category']} - {booking_info['service']}\n日期: {booking_info['date']}\n時間: {booking_info['time']}\n\n如需變更，請輸入「取消預約」後重新預約。"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=confirmation_message)
        )

if __name__ == "__main__":
    channel_secret = '3d4224a4cb32b140610545e6d155cc0d'
    channel_access_token = 'YCffcEj/7aUw33XPEtfVMuKf1l5i5ztIHLibGTy2zGuyNgLf1RXJCqA8dVhbMp8Yxbwsr1CP6EfJID8htKS/Q3io/WSfp/gtDcaRfDT/TNErwymfiIdGWdLROcBkTfRN7hXFqHVrDQ+WgkkMGFWc3AdB04t89/1O/w1cDnyilFU='
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)