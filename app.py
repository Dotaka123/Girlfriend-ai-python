import os
import time
import requests
from flask import Flask, request, jsonify, send_file
from elevenlabs.client import ElevenLabs
from elevenlabs import save

app = Flask(__name__)

# --- CONFIGURATION DU BOT ---
# REMPLACEZ par vos propres tokens
ACCESS_TOKEN = 'EAAI12hLrtqEBPgFd7L84yfZBaek8mFpb1aR38eW01Wftg4IHvJmE1LsQLjpUZCELoUskJnVKuvZBd07YLQwxjg3QG8reY1HHc7SKbUbgJv2zWCqRV3xFmeL8p0ZAsJVsNJfARW39OCPlAaZC05vzyUyqoxN26pRuAVBv2ynFG9666JgkJiFrHkEyVOyt9XcOo5pm6FAZDZD'
VERIFY_TOKEN = 'tata'

# API Llama3-Turbo
KAIZ_API_URL = "https://kaiz-apis.gleeze.com/api/llama3-turbo"
KAIZ_API_KEY = "5250a98c-2a4c-49f2-990c-ae628ee71d4f"

# API ElevenLabs
ELEVENLABS_API_KEY = "sk_4197e46b54fe3ec1c884eb24b0408659942a7d2d545df10d"
ELEVENLABS_CLIENT = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# ID de la voix de Miora
MIORA_VOICE_ID = "BewlJwjEWiFLWoXrbGMf"

# Dictionnaire pour l'historique des conversations
chat_histories = {}

# Dossier temporaire pour les fichiers audio
AUDIO_FOLDER = "temp_audio"
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
                # Vérification de l'expéditeur: ignore les messages de la page elle-même
                sender_id = event['sender']['id']
                if sender_id == entry['id']: # entry['id'] est l'ID de la page
                    print("Message provenant de la page ignoré.")
                    continue

                # Traite uniquement les messages qui contiennent du texte
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
                        send_message(sender_id, audio_filepath, message_type="audio", file_path_to_delete=audio_filepath)
                        
    return "ok", 200

# --- ENDPOINT POUR SERVIR LES FICHIERS AUDIO ---
@app.route('/audio/<filename>')
def serve_audio(filename):
    return send_file(os.path.join(AUDIO_FOLDER, filename), mimetype='audio/mpeg')

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
        
        return os.path.join(AUDIO_FOLDER, filename)
    
    except Exception as e:
        print(f"Erreur lors de la conversion du texte en audio: {e}")
        return None

def send_message(recipient_id, message_content, message_type="text", file_path_to_delete=None):
    params = { "access_token": ACCESS_TOKEN }
    headers = { "Content-Type": "application/json" }
    
    is_successful = False
    
    if message_type == "audio":
        ngrok_url = os.environ.get('NGROK_URL')
        if not ngrok_url:
            print("Erreur: La variable d'environnement NGROK_URL n'est pas définie.")
            return
        
        filename = os.path.basename(message_content)
        public_audio_url = f"{ngrok_url.rstrip('/')}/audio/{filename}"

        print(f"URL audio envoyée à Facebook: {public_audio_url}")

        data = {
            "recipient": { "id": recipient_id },
            "message": {
                "attachment": {
                    "type": "audio",
                    "payload": {
                        "url": public_audio_url,
                        "is_reusable": True
                    }
                }
            }
        }
    elif message_type == "image":
        data = {
            "recipient": { "id": recipient_id },
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {
                        "url": message_content,
                        "is_reusable": True
                    }
                }
            }
        }
    else:
        data = { "recipient": { "id": recipient_id }, "message": { "text": message_content } }

    response = requests.post("https://graph.facebook.com/v2.6/me/messages", params=params, headers=headers, json=data)
    if response.status_code == 200:
        is_successful = True
    else:
        print(f"Erreur lors de l'envoi du message: {response.status_code}")
        print(response.text)
        is_successful = False

    if is_successful and file_path_to_delete and os.path.exists(file_path_to_delete):
        try:
            print(f"En attente de 10 secondes avant de supprimer le fichier...")
            time.sleep(10)
            os.remove(file_path_to_delete)
            print(f"Fichier supprimé: {file_path_to_delete}")
        except OSError as e:
            print(f"Erreur lors de la suppression du fichier: {e}")
    elif not is_successful and file_path_to_delete and os.path.exists(file_path_to_delete):
        print(f"L'envoi a échoué. Le fichier {file_path_to_delete} n'a pas été supprimé.")

    return is_successful

# --- LANCEMENT DE L'APPLICATION ---
if __name__ == '__main__':
    os.environ['NGROK_URL'] = "https://a5862c8e8903.ngrok-free.app" 
    app.run(port=5000)
