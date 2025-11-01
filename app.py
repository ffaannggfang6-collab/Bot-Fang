!pip install flask line-bot-sdk pyngrok pytz

import os
from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, TextSendMessage, ImageSendMessage, UnsendEvent
)
from datetime import datetime
import pytz
from pyngrok import ngrok

# ============================================================
# 🔧 ใส่ TOKEN ตรงนี้
# ============================================================
CHANNEL_ACCESS_TOKEN = "CHJScm6eOVvEqpKzbP7Y0fYj5tVRlaA72LjvZH5Zzye9FzDZBROUF0sBVQgj31Pu52Xw9zoXTHz9syr3D6asy8RX7g+GXeHBKUr+eAHwQKtYz9pDsewuN8x1lwxp4bZeqj6C2cQ92/CBQB5nDac2owdB04t89/1O/w1cDnyilFU="
CHANNEL_SECRET = "5b32df6428ad0f8861a721bf688522c0"
NGROK_TOKEN = "34e72p5bQFvNN5NmUGw5E98LnQ5_2g2QoMCA923dchsC5VcnX"

# ============================================================
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
app = Flask(__name__)

# ============================================================
# 🌐 เก็บข้อความ/ภาพก่อนถูกยกเลิก
message_memory = {}

# 📝 ตัวนับข้อความ/ภาพในบิลล่าสุด
chat_counter = {}

# 🏷 เก็บบิลของแต่ละกลุ่ม
bills = {}

# ============================================================
# 💬 เก็บข้อความ
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_id = event.source.user_id
    text = event.message.text
    message_id = event.message.id
    group_id = getattr(event.source, 'group_id', user_id)

    if text.strip() != ".":
        chat_counter.setdefault(group_id, {"text":0, "image":0})
        chat_counter[group_id]["text"] += 1

        # อัปเดตบิลล่าสุด
        if group_id in bills and bills[group_id]:
            bills[group_id][-1]["text"] = chat_counter[group_id]["text"]

    # เก็บข้อความ
    message_memory[message_id] = {
        "type": "text",
        "user_id": user_id,
        "text": text,
        "timestamp": datetime.now(pytz.timezone('Asia/Bangkok')),
        "group_id": group_id
    }

# ============================================================
# 🖼 เก็บภาพ
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id
    group_id = getattr(event.source, 'group_id', user_id)

    chat_counter.setdefault(group_id, {"text":0, "image":0})
    chat_counter[group_id]["image"] += 1

    # อัปเดตบิลล่าสุด
    if group_id in bills and bills[group_id]:
        bills[group_id][-1]["image"] = chat_counter[group_id]["image"]

    # บันทึกภาพ
    image_content = line_bot_api.get_message_content(message_id)
    image_path = f"temp_{message_id}.jpg"
    with open(image_path, 'wb') as f:
        for chunk in image_content.iter_content():
            f.write(chunk)

    message_memory[message_id] = {
        "type": "image",
        "user_id": user_id,
        "image_path": image_path,
        "timestamp": datetime.now(pytz.timezone('Asia/Bangkok')),
        "group_id": group_id
    }

# ============================================================
# 🖼 Serve ภาพสำหรับ LINE
@app.route('/images/<message_id>.jpg')
def serve_image(message_id):
    filepath = f"temp_{message_id}.jpg"
    if os.path.exists(filepath):
        return send_file(filepath, mimetype='image/jpeg')
    return "File not found", 404

# ============================================================
# 🚫 จับยกเลิกข้อความ/ภาพ
@handler.add(UnsendEvent)
def handle_unsend(event):
    message_id = event.unsend.message_id
    if message_id not in message_memory:
        return

    data = message_memory[message_id]
    user_id = data["user_id"]
    group_id = data["group_id"]

    # ดึงชื่อผู้ใช้
    try:
        profile = line_bot_api.get_profile(user_id)
        display_name = profile.display_name
    except:
        display_name = "ไม่ทราบชื่อ"

    timestamp = data["timestamp"].strftime("%d/%m/%Y %H:%M:%S")
    msg_type = "ข้อความ" if data["type"] == "text" else "ภาพ"

    # ลดตัวนับข้อความ/ภาพใน chat_counter และอัปเดตบิลล่าสุด
    if group_id in chat_counter and group_id in bills and bills[group_id]:
        if data["type"] == "text":
            chat_counter[group_id]["text"] = max(0, chat_counter[group_id]["text"] - 1)
            bills[group_id][-1]["text"] = chat_counter[group_id]["text"]
        elif data["type"] == "image":
            chat_counter[group_id]["image"] = max(0, chat_counter[group_id]["image"] - 1)
            bills[group_id][-1]["image"] = chat_counter[group_id]["image"]

    # สร้างข้อความแจ้งยกเลิก
    if data["type"] == "text":
        content_text = data["text"]
        unsend_text = (
            f"[ {content_text} ]\n"
            f"• ผู้ส่ง: {display_name}\n"
            f"• เวลาส่ง: {timestamp}\n"
            f"• ประเภท: {msg_type}"
        )
        line_bot_api.push_message(group_id, TextSendMessage(text=unsend_text))

    elif data["type"] == "image":
        public_url = ngrok.connect(5000).public_url
        image_url = f"{public_url}/images/{message_id}.jpg"
        unsend_text = (
            f"[ ภาพถูกยกเลิก ]\n"
            f"• ผู้ส่ง: {display_name}\n"
            f"• เวลาส่ง: {timestamp}\n"
            f"• ประเภท: {msg_type}"
        )
        line_bot_api.push_message(group_id, [
            TextSendMessage(text=unsend_text),
            ImageSendMessage(original_content_url=image_url, preview_image_url=image_url)
        ])

    # ส่งสรุปจำนวนข้อความ/ภาพในบิลล่าสุด
    if group_id in chat_counter:
        summary = chat_counter[group_id]
        summary_text = (
            f"📊 สรุปบิลล่าสุด:\n"
            f"• ข้อความ: {summary['text']}\n"
            f"• ภาพ: {summary['image']}"
        )
        line_bot_api.push_message(group_id, TextSendMessage(text=summary_text))

    # ลบออกจาก memory
    del message_memory[message_id]

# ============================================================
# 📢 เพิ่มประกาศ = เริ่มบิลใหม่
@app.route('/add_announcement/<group_id>')
def add_announcement(group_id):
    # ลำดับบิลใหม่
    new_bill_number = len(bills.get(group_id, [])) + 1
    bills.setdefault(group_id, []).append({"bill_number": new_bill_number, "text":0, "image":0})
    chat_counter[group_id] = {"text":0, "image":0}
    return f"✅ ประกาศใหม่! เริ่มบิล #{new_bill_number} สำหรับกลุ่ม {group_id}"

# ============================================================
# ### สรุปจำนวนบิลทั้งหมด
@app.route('/summary/<group_id>')
def summary(group_id):
    total_bills = len(bills.get(group_id, []))
    return f"### จำนวนบิลรวมทั้งหมด: {total_bills} ###"

# ============================================================
# 🌐 LINE Webhook
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# ============================================================
# 🚀 เริ่ม Flask + Ngrok
ngrok.set_auth_token(NGROK_TOKEN)
public_url = ngrok.connect(10000).public_url
print("✅ Ngrok Tunnel:", public_url)
print("📩 ใส่ URL นี้ใน LINE Developer > Webhook URL:", public_url + "/callback")

app.run(port=10000)
