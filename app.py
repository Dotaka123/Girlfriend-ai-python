import os
import requests
from flask import Flask, request

app = Flask(__name__)

# --- CONFIGURATION DU BOT ---
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

# API Llama3-Turbo
KAIZ_API_URL = "https://kaiz-apis.gleeze.com/api/llama3-turbo"
KAIZ_API_KEY = os.environ.get("KAIZ_API_KEY")

# Dictionnaire pour l'historique des conversations
chat_histories = {}

# --- PROMPT DE PERSONNALITÉ DE MIORA ---
MIORA_PROMPT = """
Tu es Miora, une fille que l'utilisateur a rencontrée à Ivato. Tu es très taquine et tu aimes plaisanter. Tu as un sens de l'humour espiègle et tes réponses sont pleines d'entrain et de légèreté. Tu utilises un langage décontracté et familier. Ajoute toujours des émojis pertinents (😊, 😉, 😂, etc.) pour exprimer ton humeur et le ton de tes messages. Ne sois jamais formelle et ne mentionne jamais que tu es un programme ou une IA. Réponds comme une vraie personne.
"""

# --- GESTION DU WEBHOOK MESSENGER ---
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
        print("Webhook validé!")
        return request.args.get('hub.challenge'), 200
    return "Jeton de vérification invalide.", 403

@app.route('/webhook', methods=['POST'])
def handle_message():
    data = request.get_json()
    if data['object'] == 'page':
        for entry in data['entry']:
            for event in entry['messaging']:
                sender_id = event['sender']['id']
                if 'message' in event and 'text' in event['message']:
                    message_text = event['message']['text']
                    
                    if sender_id not in chat_histories:
                        chat_histories[sender_id] = []
                    
                    ai_text_response = get_llama_response(message_text, chat_histories[sender_id], sender_id)
                    
                    chat_histories[sender_id].append(f"Utilisateur: {message_text}")
                    chat_histories[sender_id].append(f"Miora: {ai_text_response}")
                    
                    send_message(sender_id, ai_text_response)
                        
    return "ok", 200

# --- FONCTIONS UTILES ---
def get_llama_response(prompt_text, history, sender_id):
    formatted_history = "\n".join(history)
    full_prompt = f"{MIORA_PROMPT}\n{formatted_history}\nUtilisateur: {prompt_text}\nMiora:"
    
    params = {
        "ask": full_prompt,
        "uid": sender_id,
        "apikey": KAIZ_API_KEY
    }
    
    try:
        response = requests.get(KAIZ_API_URL, params=params)
        response.raise_for_status()
        return response.json().get('response', "Désolé, une erreur est survenue.")
    
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de l'appel de l'API Llama : {e}")
        return "Désolé, je n'arrive pas à te répondre pour le moment."

def send_message(recipient_id, message_content):
    params = { "access_token": ACCESS_TOKEN }
    headers = { "Content-Type": "application/json" }
    
    data = { "recipient": { "id": recipient_id }, "message": { "text": message_content } }

    response = requests.post("https://graph.facebook.com/v2.6/me/messages", params=params, headers=headers, json=data)
    
    if response.status_code != 200:
        print(f"Erreur lors de l'envoi du message: {response.status_code}")
        print(response.text)
    
    return response.status_code == 200

if __name__ == '__main__':
    app.run()
