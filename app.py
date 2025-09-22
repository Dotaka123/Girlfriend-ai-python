import os
import time
import requests
from flask import Flask, request
from elevenlabs.client import ElevenLabs
from elevenlabs import save

app = Flask(__name__)

# --- CONFIGURATION DU BOT ---
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")

# API Llama3-Turbo
KAIZ_API_URL = "https://kaiz-apis.gleeze.com/api/llama3-turbo"
KAIZ_API_KEY = os.environ.get("KAIZ_API_KEY")

# API ElevenLabs
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
ELEVENLABS_CLIENT = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# ID de la voix de Miora
MIORA_VOICE_ID = "BewlJwjEWiFLWoXrbGMf"

# Dictionnaire pour l'historique des conversations
chat_histories = {}

# Dossier pour les fichiers audio sur Render (sera un dossier temporaire)
AUDIO_FOLDER = "/tmp"
if not os.path.exists(AUDIO_FOLDER):
    os.makedirs(AUDIO_FOLDER)

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
                    
                    audio_filepath = text_to_audio(ai_text_response)
                    
                    chat_histories[sender_id].append(f"Utilisateur: {message_text}")
                    chat_histories[sender_id].append(f"Miora: {ai_text_response}")
                    
                    send_message(sender_id, ai_text_response, message_type="text")
                    if audio_filepath:
                        # Comme les fichiers Render sont temporaires, on les envoie directement
                        send_message(sender_id, audio_filepath, message_type="audio", file_path_to_delete=audio_filepath)
                        
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

def text_to_audio(text_to_convert):
    try:
        audio_stream = ELEVENLABS_CLIENT.text_to_speech.convert(
            text=text_to_convert,
            voice_id=MIORA_VOICE_ID,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        
        filename = f"audio_{os.urandom(8).hex()}.mp3"
        filepath = os.path.join(AUDIO_FOLDER, filename)
        save(audio_stream, filepath)
        
        print(f"Fichier audio créé: {filepath}")
        
        return filepath
    
    except Exception as e:
        print(f"Erreur lors de la conversion du texte en audio: {e}")
        return None

def send_message(recipient_id, message_content, message_type="text", file_path_to_delete=None):
    params = { "access_token": ACCESS_TOKEN }
    
    if message_type == "audio":
        headers = { "Content-Type": "application/json" }
        
        # Sur Render, le serveur web gère l'accès aux fichiers statiques,
        # mais la meilleure pratique est d'utiliser le partage de fichiers
        # si possible, ou d'envoyer le fichier directement.
        # Ici, on suppose que l'URL publique sera gérée par Render
        # et que nous enverrons le lien à Facebook.
        
        # IMPORTANT: Vous devrez peut-être ajuster cette partie pour servir
        # les fichiers audio via une route Flask dédiée sur Render.
        # Par exemple, une route /audio/<filename> qui retourne le fichier.
        # Pour le moment, nous laissons la logique d'envoi.
        data = {
            "recipient": { "id": recipient_id },
            "message": {
                "attachment": {
                    "type": "audio",
                    "payload": {
                        "url": "https://votre-app-render.onrender.com/audio/" + os.path.basename(message_content),
                        "is_reusable": True
                    }
                }
            }
        }
    else:
        headers = { "Content-Type": "application/json" }
        data = { "recipient": { "id": recipient_id }, "message": { "text": message_content } }

    response = requests.post("https://graph.facebook.com/v2.6/me/messages", params=params, headers=headers, json=data)
    
    if response.status_code != 200:
        print(f"Erreur lors de l'envoi du message: {response.status_code}")
        print(response.text)

    # Clean-up du fichier audio généré
    if file_path_to_delete and os.path.exists(file_path_to_delete):
        try:
            print(f"Suppression du fichier temporaire: {file_path_to_delete}")
            os.remove(file_path_to_delete)
        except OSError as e:
            print(f"Erreur lors de la suppression du fichier: {e}")
    
    return response.status_code == 200

if __name__ == '__main__':
    app.run()
