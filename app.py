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
    PostbackAction, # 需要處理 Postback 事件
    QuickReply,
    QuickReplyItem,
    MessageAction
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    PostbackEvent # 需要處理 Postback 事件
)
import os
import datetime # 用於處理日期時間

app = Flask(__name__)

# 從環境變數取得你的 Channel Access Token 和 Channel Secret
configuration = Configuration(access_token=os.environ['LINE_CHANNEL_ACCESS_TOKEN'])
handler = WebhookHandler(os.environ['LINE_CHANNEL_SECRET'])

# --- 狀態管理 (簡易範例，建議用資料庫) ---
# 使用字典來儲存每個用戶的預約狀態
# 格式: user_states[user_id] = {'step': 'ask_datetime', 'data': {}}
user_states = {}
# --- 美甲師行程 (極簡範例，建議用資料庫或 Google Calendar API) ---
# 假設 '2023-12-25T14:00' 這個時段已被預約
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

# --- 處理文字訊息 ---
@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip().lower() # 轉小寫並去除前後空白方便比對
    api_client = ApiClient(configuration)
    line_bot_api = MessagingApi(api_client)

    # 檢查用戶是否正在預約流程中
    current_state = user_states.get(user_id)

    if current_state:
        # --- 處理預約流程中的回覆 ---
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
                # 提示用戶選擇有效選項
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
                 current_state['step'] = 'ask_extension' # 跳到詢問延甲
                 # ... (發送詢問延甲的 QuickReply) ...
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
                 line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text='請回答 是 或 否 喔！')]))


        elif step == 'ask_removal_count':
            try:
                count = int(text)
                if count > 0:
                    current_state['data']['removal_count'] = count
                    current_state['step'] = 'ask_extension'
                    # ... (發送詢問延甲的 QuickReply) ...
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
                    line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text='請輸入有效的數量（大於0的數字）')]))
            except ValueError:
                line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text='請輸入數字喔！')]))

        elif step == 'ask_extension':
            # ... 類似 ask_removal 的邏輯 ...
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
                 current_state['step'] = 'confirm' # 跳到確認步驟
                 # ... (組合預約資訊並發送確認訊息) ...
                 send_confirmation_message(line_bot_api, event.reply_token, user_id)
            else:
                 line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text='請回答 是 或 否 喔！')]))


        elif step == 'ask_extension_count':
             # ... 類似 ask_removal_count 的邏輯 ...
            try:
                count = int(text)
                if count > 0:
                    current_state['data']['extension_count'] = count
                    current_state['step'] = 'confirm'
                    # ... (組合預約資訊並發送確認訊息) ...
                    send_confirmation_message(line_bot_api, event.reply_token, user_id)
                else:
                    line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text='請輸入有效的數量（大於0的數字）')]))
            except ValueError:
                line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text='請輸入數字喔！')]))

        # ... 其他步驟的處理 ...

    else:
        # --- 處理一般關鍵字 ---
        if text == '預約':
            # 進入預約流程，要求選擇日期時間
            user_states[user_id] = {'step': 'ask_datetime', 'data': {}} # 初始化狀態
            datetime_picker = TemplateMessage(
                alt_text='請選擇預約日期與時間',
                template=ButtonsTemplate(
                    title='預約服務',
                    text='請選擇您希望預約的日期與時間',
                    actions=[
                        DatetimePickerAction(
                            label='選擇日期時間',
                            data='action=booking_datetime', # Postback 資料
                            mode='datetime', # 選擇日期+時間
                            # initial='2023-12-25T10:00', # 可選：預設時間
                            # min='2023-12-01T00:00',   # 可選：最早可選時間
                            # max='2024-12-31T23:59'    # 可選：最晚可選時間
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

        elif text in ['ig', '作品集']:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text='歡迎參考我的作品集：\nhttps://www.instagram.com/j.innail/')]
                )
            )

        elif text == '地址':
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text='工作室地址：\n捷運｜永和頂溪站1號出口 步行約3分鐘\n(詳細地址將於預約成功後提供)')] # 可以在預約成功後再給詳細地址
                )
            )
        # 可以加入其他關鍵字或預設回覆
        # else:
        #     line_bot_api.reply_message(
        #         ReplyMessageRequest(
        #             reply_token=event.reply_token,
        #             messages=[TextMessage(text='您好！請問需要什麼服務？可以輸入「預約」、「IG」、「地址」')]
        #         )
        #     )

# --- 處理 Postback 事件 (來自 DatetimePickerAction) ---
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    api_client = ApiClient(configuration)
    line_bot_api = MessagingApi(api_client)
    postback_data = event.postback.data

    # 簡單判斷是否為日期時間選擇的 Postback
    if postback_data == 'action=booking_datetime':
        selected_datetime_str = event.postback.params['datetime']
        # --- 檢查時間是否已被預約 (核心邏輯) ---
        if selected_datetime_str in busy_slots:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f"抱歉，{selected_datetime_str} 這個時段已被預約，請重新選擇。")]
                )
            )
            # 可以選擇再次發送 DatetimePicker 或提示用戶重新輸入「預約」
            # 這裡我們先不重送，讓用戶自己再觸發
            if user_id in user_states: # 清除剛才的狀態，因為時間選擇失敗
                del user_states[user_id]

        else:
            # 時間可以預約，進入下一步：詢問項目
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
                 # 如果狀態不對，可能用戶操作太快或有誤，給個提示
                 line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="發生錯誤，請重新輸入「預約」開始流程。")]
                    )
                 )
                 if user_id in user_states:
                     del user_states[user_id] # 清除錯誤狀態


# --- 發送最終確認訊息並儲存預約 (範例) ---
def send_confirmation_message(line_bot_api, reply_token, user_id):
    state = user_states.get(user_id)
    if not state or state['step'] != 'confirm':
        # 狀態錯誤
        return

    data = state['data']
    # 組合訊息字串
    summary = f"好的，已為您登記預約：\n\n" \
              f"日期時間：{data.get('datetime', '未選擇')}\n" \
              f"項目：{data.get('service', '未選擇')}\n" \
              f"卸甲：{'是 (' + str(data.get('removal_count', '')) + '隻)' if data.get('removal') else '否'}\n" \
              f"延甲：{'是 (' + str(data.get('extension_count', '')) + '隻)' if data.get('extension') else '否'}\n\n" \
              f"後續將傳送詳細地址與注意事項給您，謝謝！"

    # --- 儲存預約紀錄 (重要！) ---
    # 在這裡你需要將 data 中的資訊存到你的資料庫或 Google Calendar
    # 同時，將這個時段加入 busy_slots (如果是用簡易範例)
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
    # 清除用戶狀態，完成預約流程
    del user_states[user_id]


# --- 主程式入口 ---
if __name__ == "__main__":
    # 確保你有設定環境變數 PORT，Render 會用到
    port = int(os.environ.get('PORT', 5000))
    # 注意：debug=True 不應在生產環境(Render)中使用，部署時應設為 False
    # Render 會使用 Gunicorn 等 WSGI 伺服器來跑，不需要 app.run() 的 debug 模式
    # app.run(host='0.0.0.0', port=port, debug=False)
    # 對於 Render，通常不需要寫 app.run()，Gunicorn 會直接找 app 物件
    pass # 在 Render 上通常由 Gunicorn 啟動，這裡保留空白或移除 app.run
