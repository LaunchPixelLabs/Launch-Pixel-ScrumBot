import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# Callback function to be registered by the Discord bot
whatsapp_callback = None

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "launchpixel_token")

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Handles the Meta/WhatsApp Webhook verification challenge."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode and token:
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            print("🟢 [WhatsApp Webhook] Webhook verified successfully!")
            return challenge, 200
        else:
            print("🔴 [WhatsApp Webhook] Verification failed: Token mismatch.")
            return "Forbidden", 403
    return "Missing parameters", 400

@app.route('/webhook', methods=['POST'])
def receive_message():
    """Receives webhook notifications when a WhatsApp message is received."""
    data = request.json
    print(f"📨 [WhatsApp Webhook] Received webhook payload: {data}")

    try:
        if data.get('object') == 'whatsapp_business_account':
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    messages = value.get('messages', [])
                    contacts = value.get('contacts', [])
                    
                    if messages:
                        message = messages[0]
                        sender_phone = message.get('from', 'Unknown')
                        msg_type = message.get('type', 'text')
                        
                        # Find sender display name
                        sender_name = sender_phone
                        if contacts:
                            sender_name = contacts[0].get('profile', {}).get('name', sender_phone)
                        
                        body = ""
                        if msg_type == 'text':
                            body = message.get('text', {}).get('body', '')
                        elif msg_type == 'button':
                            body = message.get('button', {}).get('text', '[Button Click]')
                        else:
                            body = f"[{msg_type.capitalize()} Media Message]"
                            
                        # If a callback is registered, send the message to Discord
                        if whatsapp_callback:
                            whatsapp_callback(sender_name, sender_phone, body)
                            
            return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"⚠️ [WhatsApp Webhook] Error parsing webhook payload: {e}")
        
    return jsonify({"status": "ignored"}), 200

def run_server(port=5000):
    """Utility function to run the Flask webhook server."""
    # We disable the reloader so it doesn't double-start when run inside a thread
    app.run(host='0.0.0.0', port=port, use_reloader=False)
