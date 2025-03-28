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

app = Flask(__name__)

# 從環境變數取得設定
channel_secret = os.environ.get('LINE_CHANNEL_SECRET', '您的 Channel Secret')
channel_access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '您的 Channel Access Token')

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

# 儲存預約資訊 (實際應用建議使用資料庫)
bookings = {}

# 美甲師資料 (實際應用建議使用資料庫)
manicurists = {
    '1': {
        'name': '王綺綺',
        'title': '店長',
        'bio': '台灣🇹🇼TNA指甲彩繪技能職類丙級🪪日本🇯🇵pregel 1級🪪日本🇯🇵pregel 2級🪪美甲美學｜足部香氛SPA｜',
        'image_url': 'https://example.com/images/wang_qiqi.jpg',  # 替換為真實照片URL
    },
    '2': {
        'name': '李明美',
        'title': '資深美甲師',
        'bio': '擅長各種風格設計，提供客製化服務。專精日系美甲、法式美甲、寶石裝飾。',
        'image_url': 'https://example.com/images/li_mingmei.jpg',  # 替換為真實照片URL
    },
    '3': {
        'name': '陳曉婷',
        'title': '美甲師',
        'bio': '擁有多年美甲經驗，提供專業手足護理和美甲服務。擅長手繪藝術及繁複設計。',
        'image_url': 'https://example.com/images/chen_xiaoting.jpg',  # 替換為真實照片URL
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
        # 新版流程：先選擇美甲師
        send_manicurist_selection(event.reply_token)
    
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
                    f"【{manicurist['name']} {manicurist['title']}】\n\n"
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
        message = "您好！我是美甲預約助手，可以幫您:\n1. 輸入「預約」開始預約\n2. 輸入「美甲師」查看美甲師資訊\n3. 輸入「地址」查看我們的位置\n4. 輸入「作品集」或「IG」查看作品\n5. 輸入「查詢預約」查看您的預約\n6. 輸入「取消預約」取消現有預約"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=message)
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    user_id = event.source.user_id
    
    # 處理美甲師選擇
    if data.startswith("select_manicurist_"):
        manicurist_id = data.replace("select_manicurist_", "")
        manicurist = manicurists[manicurist_id]
        
        # 儲存用戶選擇的美甲師
        if user_id not in bookings:
            bookings[user_id] = {}
        
        bookings[user_id]['manicurist_id'] = manicurist_id
        bookings[user_id]['manicurist_name'] = manicurist['name']
        
        # 顯示美甲師詳細介紹和照片
        send_manicurist_detail(event.reply_token, manicurist_id)
    
    # 重新選擇美甲師
    elif data == "restart_selection":
        send_manicurist_selection(event.reply_token)
        
    # 處理服務類別選擇
    elif data.startswith("category_"):
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
        
    # 服务选择后的预约流程
    elif data.startswith("start_booking_"):
        manicurist_id = data.replace("start_booking_", "")
        
        # 显示服务类别选单
        service_categories = list(services.keys())
        buttons_template = ButtonsTemplate(
            title='美容服務預約',
            text=f'已選擇美甲師: {manicurists[manicurist_id]["name"]}\n請選擇服務類別',
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

# 新增美甲師選擇的函數
def send_manicurist_selection(reply_token):
    columns = []
    for manicurist_id, manicurist in manicurists.items():
        title = f"{manicurist['name']} {manicurist['title']}"
        text = manicurist['bio'][:60] + "..." if len(manicurist['bio']) > 60 else manicurist['bio']
        
        columns.append(
            CarouselColumn(
                thumbnail_image_url=manicurist['image_url'],
                title=title,
                text=text,
                actions=[
                    PostbackTemplateAction(
                        label=f"選擇 {manicurist['name']}",
                        data=f"select_manicurist_{manicurist_id}"
                    )
                ]
            )
        )
    
    carousel_template = CarouselTemplate(columns=columns)
    template_message = TemplateSendMessage(
        alt_text='請選擇美甲師',
        template=carousel_template
    )
    
    line_bot_api.reply_message(
        reply_token,
        [
            TextSendMessage(text="請選擇您想預約的美甲師："),
            template_message
        ]
    )

# 新增顯示美甲師詳細資訊的函數
def send_manicurist_detail(reply_token, manicurist_id):
    manicurist = manicurists[manicurist_id]
    
    # 為王綺綺店長添加更詳細的介紹
    if manicurist_id == '1':  # 王綺綺是ID為1的店長
        description = (
            f"【{manicurist['name']} {manicurist['title']}】\n\n"
            f"{manicurist['bio']}\n\n"
            "王店長擁有多年美甲經驗，專精於日式美甲設計和健康管理。"
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
    
    # 建立選擇按鈕
    buttons_template = ButtonsTemplate(
        title=f"{manicurist['name']} {manicurist['title']}",
        text="您滿意這位美甲師嗎？",
        actions=[
            PostbackTemplateAction(
                label="開始預約",
                data=f"start_booking_{manicurist_id}"
            ),
            PostbackTemplateAction(
                label="選擇其他美甲師",
                data="restart_selection"
            )
        ]
    )
    
    template_message = TemplateSendMessage(
        alt_text='確認美甲師選擇',
        template=buttons_template
    )
    
    # 發送訊息
    line_bot_api.reply_message(
        reply_token,
        [
            TextSendMessage(text=description),
            image_message,
            template_message
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
