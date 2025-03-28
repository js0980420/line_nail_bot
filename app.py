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
import logging
from datetime import datetime, timedelta

app = Flask(__name__)

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

@app.route("/callback", methods=['POST'])
def callback():
    try:
        # 取得 X-Line-Signature header 值
        signature = request.headers['X-Line-Signature']

        # 取得請求內容
        body = request.get_data(as_text=True)
        logger.info("Request body: " + body)

        # 處理 webhook
        try:
            handler.handle(body, signature)
        except InvalidSignatureError:
            logger.error("無效的簽名")
            abort(400)
        except Exception as e:
            logger.error(f"處理webhook時發生錯誤: {e}")
            # 不中斷請求，返回 OK
            
        return 'OK'
    except Exception as e:
        logger.error(f"回呼函數發生錯誤: {e}")
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
                
                # 添加查看更多按鈕
                additional_message = None
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
                if additional_message:
                    line_bot_api.reply_message(
                        event.reply_token,
                        [template_message, additional_message]
                    )
                    return
            
            line_bot_api.reply_message(event.reply_token, template_message)
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
    except Exception as e:
        logger.error(f"處理消息時發生錯誤: {e}")
        try:
            # 傳送錯誤通知給用戶
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="很抱歉，系統發生錯誤，請稍後再試。")
            )
        except Exception as inner_e:
            logger.error(f"傳送錯誤通知時發生錯誤: {inner_e}")

@handler.add(PostbackEvent)
def handle_postback(event):
    try:
        data = event.postback.data
        user_id = event.source.user_id
        logger.info(f"收到來自用戶 {user_id} 的 postback: {data}")
        
        # 直接處理服務項目選擇，不需要處理服務類別選擇
        if data.startswith("service_"):
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
            parts = data.split("_")
            manicurist_id = parts[2]  # 獲取美甲師ID
            date_time = parts[3] if len(parts) > 3 else ""  # 獲取日期時間信息
            
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
        else:
            # 未知的 postback 數據
            logger.warning(f"收到未知的 postback 數據: {data}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="抱歉，無法處理您的請求。請重新開始預約流程。")
            )

    except Exception as e:
        logger.error(f"處理 postback 時發生錯誤: {e}")
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="很抱歉，處理您的選擇時發生錯誤，請重新開始。")
            )
        except Exception as inner_e:
            logger.error(f"傳送錯誤通知時發生錯誤: {inner_e}")

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
                        data=f"select_manicurist_id_{manicurist_id}_{datetime_str}"
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
    
    # 預約流程說明：
    # 1. 用戶直接選擇美甲服務項目
    # 2. 用戶選擇預約日期
    # 3. 用戶選擇時段（上午/下午/晚上）
    # 4. 用戶選擇具體時間
    # 5. 用戶選擇美甲師 (最後一步)
    # 6. 確認預約
    
    logger.info("美甲預約機器人開始啟動...")
    
    # 使用環境變數或默認值
    channel_secret_value = os.environ.get('LINE_CHANNEL_SECRET', '3d4224a4cb32b140610545e6d155cc0d')
    channel_access_token_value = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', 'YCffcEj/7aUw33XPEtfVMuKf1l5i5ztIHLibGTy2zGuyNgLf1RXJCqA8dVhbMp8Yxbwsr1CP6EfJID8htKS/Q3io/WSfp/gtDcaRfDT/TNErwymfiIdGWdLROcBkTfRN7hXFqHVrDQ+WgkkMGFWc3AdB04t89/1O/w1cDnyilFU=')
    
    # 如果系統環境變數中設定了值，則使用環境變數，否則使用默認值
    if os.environ.get('LINE_CHANNEL_SECRET'):
        logger.info("使用環境變數中的 LINE_CHANNEL_SECRET")
    else:
        logger.info("使用默認的 LINE_CHANNEL_SECRET")
        
    if os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'):
        logger.info("使用環境變數中的 LINE_CHANNEL_ACCESS_TOKEN")
    else:
        logger.info("使用默認的 LINE_CHANNEL_ACCESS_TOKEN")
    
    # 重新初始化 LINE Bot API，確保使用正確的值
    line_bot_api = LineBotApi(channel_access_token_value)
    handler = WebhookHandler(channel_secret_value)
    
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"啟動服務器，監聽端口 {port}")
    app.run(host='0.0.0.0', port=port)
