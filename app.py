from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    TemplateMessage,
    ButtonsTemplate,
    DatetimePickerAction,
    QuickReply,
    QuickReplyItem,
    MessageAction,
    CarouselTemplate,
    CarouselColumn,
    LocationMessage # 引入 LocationMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    PostbackEvent
)
import os
import logging

app = Flask(__name__)

# 設定日誌記錄
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 從環境變數中獲取 LINE Channel Access Token 和 Secret
# 如果環境變數未設定，則使用預設值 (這應該僅用於開發/測試，絕對不要在生產環境中使用)
channel_access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
channel_secret = os.environ.get('LINE_CHANNEL_SECRET')

if not channel_access_token:
    logger.warning("LINE_CHANNEL_ACCESS_TOKEN is not set in environment variables.")
    #  在生產環境中，如果遺失令牌，程式應該停止。
    #  為了使這個範例即使在沒有設定環境變數的情況下也能運行，我們將其設置為一個空字符串。
    channel_access_token = ""  
if not channel_secret:
    logger.warning("LINE_CHANNEL_SECRET is not set in environment variables.")
    #  在生產環境中，如果遺失密鑰，程式應該停止。
    #  為了使這個範例即使在沒有設定環境變數的情況下也能運行，我們將其設置為一個空字符串。
    channel_secret = ""  

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

# 使用全域變數儲存使用者狀態
user_states = {}
busy_slots = set()

# 美甲師資料 (可以放在資料庫或外部檔案)
manicurists = {
    '1': {
        'name': '王綺綺',
        'bio': '台灣🇹🇼TNA指甲彩繪技能職類丙級🪪日本🇯🇵pregel 1級🪪日本🇯🇯pregel 2級🪪美甲美學｜足部香氛SPA｜',
        'image_url': 'https://your-image-url-1.com',  # 替換成實際的圖片URL
    },
    '2': {
        'name': '李明美',
        'bio': '資深美甲師，擅長各種風格設計，提供客製化服務。',
        'image_url': 'https://your-image-url-2.com',  # 替換成實際的圖片URL
    },
    '3': {
        'name': '陳曉婷',
        'bio': '擁有多年美甲經驗，提供專業手足護理和美甲服務。',
        'image_url': 'https://your-image-url-3.com',  # 替換成實際的圖片URL
    },
}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)  # 使用 app.logger
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/secret.")
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip().lower()
    api_client = ApiClient(configuration)
    line_bot_api = MessagingApi(api_client)

    logger.info(f"User ID: {user_id}, Received message: {text}")  # 記錄收到的訊息

    # 獨立關鍵字處理
    if text == '預約':
        logger.info(f"User ID: {user_id}, Action: '預約'")
        user_states[user_id] = {'step': 'ask_manicurist', 'data': {}}  # 先詢問美甲師
        send_manicurist_selection(line_bot_api, event.reply_token)
        return

    elif text in ['ig', '作品集']:
        logger.info(f"User ID: {user_id}, Action: 'IG/作品集'")
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text='歡迎參考我的作品集：\nhttps://www.instagram.com/j.innail/')]
            )
        )
        return

    elif text == '地址':
        logger.info(f"User ID: {user_id}, Action: '地址'")
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[
                    LocationMessage(title='頂溪站1號出口', address='新北市永和區', latitude=25.011841, longitude=121.514514) # 加上地圖
                ]
            )
        )
        return
    
    elif text == '美甲師':
        logger.info(f"User ID: {user_id}, Action: '美甲師'")
        send_manicurist_info(line_bot_api, event.reply_token)
        return

    # 檢查用戶是否在預約流程中
    current_state = user_states.get(user_id)
    logger.info(f"User ID: {user_id}, Current state: {current_state}")  # 記錄用戶當前狀態

    if current_state:
        step = current_state['step']

        if step == 'ask_manicurist':
            logger.info(f"User ID: {user_id}, Step: 'ask_manicurist'")
            if text in [m['name'].lower() for m in manicurists.values()]:
                selected_manicurist_name = text
                selected_manicurist_id = None
                for key, value in manicurists.items():
                    if value['name'].lower() == selected_manicurist_name:
                        selected_manicurist_id = key
                        break
                current_state['data']['manicurist_id'] = selected_manicurist_id
                current_state['data']['manicurist_name'] = selected_manicurist_name
                current_state['step'] = 'ask_datetime'
                datetime_picker = TemplateMessage(
                    alt_text='請選擇預約日期與時間',
                    template=ButtonsTemplate(
                        title='預約服務',
                        text='請選擇您希望預約的日期與時間',
                        actions=[
                            DatetimePickerAction(
                                label='選擇日期時間',
                                data='action=booking_datetime',
                                mode='datetime',
                            )
                        ]
                    )
                )
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[datetime_picker]
                    )
                )
            else:
                send_manicurist_selection(line_bot_api, event.reply_token, "請選擇有效的美甲師名稱")

        elif step == 'ask_service':
            logger.info(f"User ID: {user_id}, Step: 'ask_service'")
            if text in ['手部', '足部']:
                current_state['data']['service'] = text
                current_state['step'] = 'ask_removal'
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[
                            TextMessage(
                                text='好的，請問需要卸甲嗎？',
                                quick_reply=QuickReply(
                                    items=[
                                        QuickReplyItem(action=MessageAction(label='是', text='是')),
                                        QuickReplyItem(action=MessageAction(label='否', text='否')),
                                    ]
                                )
                            )
                        ]
                    )
                )
            else:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text='請選擇 手部 或 足部 喔！')]
                    )
                )

        elif step == 'ask_removal':
            logger.info(f"User ID: {user_id}, Step: 'ask_removal'")
            if text == '是':
                current_state['data']['removal'] = True
                current_state['step'] = 'ask_removal_count'
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text='請問需要卸幾隻呢？請輸入數字')]
                    )
                )
            elif text == '否':
                current_state['data']['removal'] = False
                current_state['step'] = 'ask_extension'
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[
                            TextMessage(
                                text='好的，那請問需要延甲嗎？',
                                quick_reply=QuickReply(
                                    items=[
                                        QuickReplyItem(action=MessageAction(label='是', text='是')),
                                        QuickReplyItem(action=MessageAction(label='否', text='否')),
                                    ]
                                )
                            )
                        ]
                    )
                )
            else:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text='請回答 是 或 否 喔！')]
                    )
                )

        elif step == 'ask_removal_count':
            logger.info(f"User ID: {user_id}, Step: 'ask_removal_count'")
            try:
                count = int(text)
                if count > 0:
                    current_state['data']['removal_count'] = count
                    current_state['step'] = 'ask_extension'
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[
                                TextMessage(
                                    text='好的，那請問需要延甲嗎？',
                                    quick_reply=QuickReply(
                                        items=[
                                            QuickReplyItem(action=MessageAction(label='是', text='是')),
                                            QuickReplyItem(action=MessageAction(label='否', text='否')),
                                        ]
                                    )
                                )
                            ]
                        )
                    )
                else:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text='請輸入有效的數量（大於0的數字）')]
                        )
                    )
            except ValueError:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text='請輸入數字喔！')]
                    )
                )

        elif step == 'ask_extension':
            logger.info(f"User ID: {user_id}, Step: 'ask_extension'")
            if text == '是':
                current_state['data']['extension'] = True
                current_state['step'] = 'ask_extension_count'
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text='請問需要延幾隻呢？請輸入數字')]
                    )
                )
            elif text == '否':
                current_state['data']['extension'] = False
                current_state['step'] = 'confirm'
                send_confirmation_message(line_bot_api, event.reply_token, user_id)
            else:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text='請回答 是 或 否 喔！')]
                    )
                )

        elif step == 'ask_extension_count':
            logger.info(f"User ID: {user_id}, Step: 'ask_extension_count'")
            try:
                count = int(text)
                if count > 0:
                    current_state['data']['extension_count'] = count
                    current_state['step'] = 'confirm'
                    send_confirmation_message(line_bot_api, event.reply_token, user_id)
                else:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text='請輸入有效的數量（大於0的數字）')]
                        )
                    )
            except ValueError:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text='請輸入數字喔！')]
                    )
                )

    # 如果沒有狀態且非獨立關鍵字，提供預設回覆
    else:
        logger.info(f"User ID: {user_id}, No state, sending default reply")
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text='您好！請問需要什麼服務？可以輸入「預約」、「IG」、「地址」、「美甲師」')]
            )
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    api_client = ApiClient(configuration)
    line_bot_api = MessagingApi(api_client)
    postback_data = event.postback.data

    logger.info(f"User ID: {user_id}, Postback data: {postback_data}")  # 記錄 Postback 事件

    if postback_data == 'action=booking_datetime':
        selected_datetime_str = event.postback.params['datetime']
        if selected_datetime_str in busy_slots:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f"抱歉，{selected_datetime_str} 這個時段已被預約，請重新選擇。")]
                )
            )
            if user_id in user_states:
                del user_states[user_id]
        else:
            current_state = user_states.get(user_id)
            if current_state and current_state['step'] == 'ask_datetime':
                current_state['data']['datetime'] = selected_datetime_str
                current_state['step'] = 'ask_service'
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[
                            TextMessage(
                                text=f"您選擇的時間是：{selected_datetime_str}\n請問您想預約哪個項目？",
                                quick_reply=QuickReply(
                                    items=[
                                        QuickReplyItem(action=MessageAction(label='手部', text='手部')),
                                        QuickReplyItem(action=MessageAction(label='足部', text='足部')),
                                    ]
                                )
                            )
                        ]
                    )
                )
            else:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="發生錯誤，請重新輸入「預約」開始流程。")]
                    )
                )
                if user_id in user_states:
                    del user_states[user_id]

def send_confirmation_message(line_bot_api, reply_token, user_id):
    state = user_states.get(user_id)
    if not state or state['step'] != 'confirm':
        return

    data = state['data']
    summary = f"好的，已為您登記預約：\n\n" \
              f"美甲師：{data.get('manicurist_name', '未選擇')}\n" \
              f"日期時間：{data.get('datetime', '未選擇')}\n" \
              f"項目：{data.get('service', '未選擇')}\n" \
              f"卸甲：{'是 (' + str(data.get('removal_count', '')) + '隻)' if data.get('removal') else '否'}\n" \
              f"延甲：{'是 (' + str(data.get('extension_count', '')) + '隻)' if data.get('extension') else '否'}\n\n" \
              f"後續將傳送詳細地址與注意事項給您，謝謝！"

    booked_time = data.get('datetime')
    if booked_time:
        busy_slots.add(booked_time)
        print(f"--- Booking Saved ---")
        print(f"User ID: {user_id}")
        print(f"Data: {data}")
        print(f"Busy Slots Now: {busy_slots}")
        print(f"---------------------")

    line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=summary)]
        )
    )
    del user_states[user_id]

def send_manicurist_selection(line_bot_api, reply_token, message="請選擇您想要預約的美甲師："):
    columns = []
    for manicurist_id, manicurist in manicurists.items():
        columns.append(
            CarouselColumn(
                thumbnail_image_url=manicurist['image_url'],
                title=manicurist['name'],
                text=manicurist['bio'][:60] + "...",  # 限制bio長度
                actions=[
                    MessageAction(label='選擇美甲師', text=manicurist['name']),
                ]
            )
        )
    carousel_template = CarouselTemplate(columns=columns)
    line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[
                TextMessage(text=message),
                TemplateMessage(alt_text='請選擇美甲師', template=carousel_template)
            ]
        )
    )

def send_manicurist_info(line_bot_api, reply_token):
    messages = []
    for manicurist_id, manicurist in manicurists.items():
        text_message = TextMessage(text=f"{manicurist['name']}\n{manicurist['bio']}")
        image_message = ImageSendMessage(original_content_url=manicurist['image_url'], preview_image_url=manicurist['image_url'])
        messages.extend([text_message, image_message])
    line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=messages))

if __name__ == "__main__":
    app.run()
