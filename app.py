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
    MessageAction
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    PostbackEvent
)
import os

app = Flask(__name__)

configuration = Configuration(access_token=os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

user_states = {}
busy_slots = {'2023-12-25T14:00'}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
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

    # 獨立關鍵字處理，無論任何狀態下都能觸發
    if text == '預約':
        user_states[user_id] = {'step': 'ask_datetime', 'data': {}}
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
        return  # 結束函數，避免進入後續邏輯

    elif text in ['ig', '作品集']:
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text='歡迎參考我的作品集：\nhttps://www.instagram.com/j.innail/')]
            )
        )
        return  # 結束函數

    elif text == '地址':
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text='工作室地址：\n捷運｜永和頂溪站1號出口 步行約3分鐘\n(詳細地址將於預約成功後提供)')]
            )
        )
        return  # 結束函數

    # 檢查用戶是否在預約流程中
    current_state = user_states.get(user_id)

    if current_state:
        step = current_state['step']

        if step == 'ask_service':
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
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text='您好！請問需要什麼服務？可以輸入「預約」、「IG」、「地址」')]
            )
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    api_client = ApiClient(configuration)
    line_bot_api = MessagingApi(api_client)
    postback_data = event.postback.data

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
