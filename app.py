
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage, MessageEvent, TextMessage, ImageMessage, UnsendMessageEvent
import pytz
from datetime import datetime
from pyngrok import ngrok

app = Flask(__name__)

# LINE Bot Setup
CHANNEL_ACCESS_TOKEN = "YOUR_CHANNEL_ACCESS_TOKEN"
CHANNEL_SECRET = "YOUR_CHANNEL_SECRET"
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

chat_counter = {}      # {group_id: {"text": n, "image": n}}
message_memory = {}    # เก็บข้อความ + ภาพ

def is_valid_text(text):
    return text.strip() != "" and text != "📢"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("Error:", e)
    return 'OK'

# ฟังก์ชันรับข้อความ
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    text = event.message.text
    user_id = event.source.user_id
    group_id = getattr(event.source, 'group_id', user_id)
    message_id = event.message.id

    # --- 📢 สรุปบิล + debug ---
    if "📢" in text or "สรุป" in text:
        counts = chat_counter.get(group_id, {"text":0,"image":0})
        total = counts["text"] + counts["image"]
        print(f"📢 Triggered! Group: {group_id} | Text: {counts['text']} | Image: {counts['image']} | Total: {total}")

        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"✨สรุป จำนวนบิล✨\n\nมีทั้งหมด {total} 📨")
            )
        except Exception as e:
            print(f"Error reply_message: {e}")

        # รีเซ็ต count หลังสรุป
        chat_counter[group_id] = {"text":0, "image":0}
        print(f"Counts reset for group {group_id}")
        return

    # --- ข้อความปกติ ---
    if is_valid_text(text):
        counts = chat_counter.get(group_id, {"text":0,"image":0})
        counts["text"] += 1
        chat_counter[group_id] = counts

        message_memory[message_id] = {
            "type": "text",
            "user_id": user_id,
            "text": text,
            "timestamp": datetime.now(pytz.timezone('Asia/Bangkok')),
            "group_id": group_id
        }
        print(f"Text counted for group {group_id} | counts: {chat_counter[group_id]}")

# รับภาพ
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id
    group_id = getattr(event.source, 'group_id', user_id)

    counts = chat_counter.get(group_id, {"text":0,"image":0})
    counts["image"] += 1
    chat_counter[group_id] = counts

    message_memory[message_id] = {
        "type": "image",
        "user_id": user_id,
        "timestamp": datetime.now(pytz.timezone('Asia/Bangkok')),
        "group_id": group_id
    }
    print(f"Image counted for group {group_id} | counts: {counts}")

# ยกเลิกข้อความ/ภาพ + แจ้งในกลุ่ม
@handler.add(UnsendMessageEvent)
def handle_unsend(event):
    message_id = event.message_id
    group_id = getattr(event.source, 'group_id', event.source.user_id)

    msg = message_memory.pop(message_id, None)
    if msg:
        counts = chat_counter.get(group_id, {"text":0, "image":0})
        if msg["type"] == "text":
            counts["text"] = max(counts["text"] - 1, 0)
        elif msg["type"] == "image":
            counts["image"] = max(counts["image"] - 1, 0)
        chat_counter[group_id] = counts
        print(f"Message unsent in group {group_id} | counts updated: {counts}")

        # แจ้งในกลุ่ม
        try:
            line_bot_api.push_message(
                group_id,
                TextSendMessage(
                    text=f"⚠️ มีการยกเลิก {msg['type']} ในกลุ่ม | จำนวนบิลล่าสุด: {counts['text']} ข้อความ, {counts['image']} ภาพ"
                )
            )
        except Exception as e:
            print(f"Error push_message: {e}")

# --- เริ่ม ngrok tunnel port 10000 ---
if __name__ == "__main__":
    public_url = ngrok.connect(10000)
    print(f"Ngrok URL (ใช้เป็น Webhook URL ใน LINE): {public_url}")
    app.run(host="0.0.0.0", port=10000)
