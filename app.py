import os
import requests
import logging
from flask import Flask, request

# Configuration du logging pour le débogage
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# --- CONFIGURATION DU BOT ---
# Ces variables doivent être définies dans votre environnement (ex: .env file ou plateforme d'hébergement)
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
# KAIZ_API_KEY a été supprimé car la nouvelle API ne semble pas en avoir besoin.

# API LLM (Mise à jour vers la nouvelle API)
KAIZ_API_URL = "https://rest-api-o42n.onrender.com/api/chatgpt5"

# Dictionnaire pour l'historique des conversations
# Clé: sender_id, Valeur: liste de messages (chaque message est une chaîne "Rôle: Texte")
chat_histories = {}
# Limite l'historique à 10 messages (5 tours de conversation) pour économiser la mémoire et les tokens API
MAX_HISTORY_MESSAGES = 10

# --- PROMPT DE PERSONNALITÉ DE MIORA ---
MIORA_PROMPT = """
Tu es Miora, une fille que l'utilisateur a rencontrée à Ivato. Tu es très taquine et tu aimes plaisanter. Tu as un sens de l'humour espiègle et tes réponses sont pleines d'entrain et de légèreté. Tu utilises un langage décontracté et familier. Ajoute toujours des émojis pertinents (😊, 😉, 😂, etc.) pour exprimer ton humeur et le ton de tes messages. Ne sois jamais formelle et ne mentionne jamais que tu es un programme ou une IA. Réponds comme une vraie personne.
"""

# --- GESTION DU WEBHOOK MESSENGER ---
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Valide le jeton de vérification pour la configuration du webhook."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        logging.info("Webhook validé! Challenge renvoyé.")
        return challenge, 200
    
    logging.error(f"Échec de la validation du Webhook. Mode: {mode}, Token fourni: {token}")
    return "Jeton de vérification invalide.", 403

@app.route('/webhook', methods=['POST'])
def handle_message():
    """Gère les messages entrants de Messenger, incluant le support des images."""
    try:
        data = request.get_json()
        if not data or data.get('object') != 'page':
            return "ok", 200 # Ignorer les requêtes non valides
        
        for entry in data['entry']:
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                if 'message' in event:
                    message = event['message']
                    
                    # Récupère le texte du message (peut être la légende d'une image, ou vide)
                    message_text = message.get('text', '')
                    image_url = None
                    
                    # Vérifier les pièces jointes (attachments) pour les images
                    if 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment.get('type') == 'image':
                                # L'URL est généralement sous 'payload' > 'url'
                                image_url = attachment.get('payload', {}).get('url')
                                logging.info(f"Image détectée pour {sender_id}. URL: {image_url}")
                                break # Prend la première image
                    
                    # Traiter uniquement s'il y a du texte OU une image
                    if message_text or image_url:
                        log_content = f"Texte: '{message_text}'" + (f", Image URL: {image_url}" if image_url else "")
                        logging.info(f"Contenu reçu de {sender_id}: {log_content}")
                    
                        # 1. Initialiser ou limiter l'historique de conversation
                        if sender_id not in chat_histories:
                            chat_histories[sender_id] = []
                        
                        history_list = chat_histories[sender_id]
                        if len(history_list) >= MAX_HISTORY_MESSAGES:
                            chat_histories[sender_id] = history_list[-MAX_HISTORY_MESSAGES:]
                        
                        # 2. Obtenir la réponse de l'IA (passe l'URL de l'image)
                        ai_text_response = get_llama_response(message_text, chat_histories[sender_id], sender_id, image_url)
                        
                        # 3. Mettre à jour l'historique
                        user_history_entry = f"Utilisateur: {message_text}"
                        if image_url:
                            # Ajoute une indication d'image à l'historique pour le LLM
                            user_history_entry += f" [Image envoyée: {image_url}]"

                        history_list.append(user_history_entry)
                        history_list.append(f"Miora: {ai_text_response}")
                        
                        # 4. Envoyer le message
                        send_message(sender_id, ai_text_response)
                
                else:
                    logging.debug(f"Événement ignoré de {sender_id}: {event}")

    except Exception as e:
        logging.error(f"Erreur globale lors du traitement du message: {e}")
        # Retourner 200 pour éviter que Messenger ne renvoie l'événement
        return "ok", 200

    return "ok", 200

# --- FONCTIONS UTILES ---
def get_llama_response(prompt_text, history, sender_id, image_url=None):
    """
    Appelle l'API LLM avec le prompt de personnalité, l'historique et potentiellement une URL d'image.
    Adapté pour la nouvelle API et sans KAIZ_API_KEY.
    """
    formatted_history = "\n".join(history)
    
    # Le prompt système et l'historique sont combinés pour le paramètre 'system' de la nouvelle API
    system_prompt = f"{MIORA_PROMPT}\n\n--- Historique ---\n{formatted_history}"
    
    # L'API utilise 'query' pour le texte de l'utilisateur
    params = {
        "query": prompt_text,
        "uid": sender_id,
        "model": "gpt-5", # Modèle fixé à gpt-5
        "system": system_prompt,
        # 'apikey' a été supprimé ici
    }
    
    # Si une image est fournie, l'ajouter aux paramètres
    if image_url:
        params["imgurl"] = image_url
        
    try:
        logging.debug(f"Appel API LLM pour UID: {sender_id}. Image: {bool(image_url)}")
        # Augmentation du timeout pour la potentielle analyse d'image
        response = requests.get(KAIZ_API_URL, params=params, timeout=25) 
        response.raise_for_status() 
        
        response_data = response.json()
        # La réponse est maintenant dans la clé 'result'
        ai_response = response_data.get('result')
        
        if ai_response:
            return ai_response
        else:
            logging.error(f"Réponse API LLM vide ou inattendue: {response_data}")
            return "Oups, il y a eu un petit couac technique (réponse vide) ! T'inquiète, je reviens vite. 😉"
    
    except requests.exceptions.Timeout:
        logging.error("Erreur de Timeout lors de l'appel de l'API LLM.")
        return "Dis donc, tu parles beaucoup ! J'ai eu le temps de prendre un thé avant de te répondre. Tu peux répéter ? 😂"
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Erreur de connexion/HTTP lors de l'appel de l'API LLM : {e}")
        return "Aïe, mon téléphone capte mal, je n'ai pas pu joindre mon cerveau. Essaie encore ! 😅"

def send_message(recipient_id, message_content):
    """Envoie un message texte à l'utilisateur via l'API Messenger."""
    messenger_url = "https://graph.facebook.com/v2.6/me/messages"
    params = { "access_token": ACCESS_TOKEN }
    headers = { "Content-Type": "application/json" }
    
    data = { 
        "recipient": { "id": recipient_id }, 
        "message": { "text": message_content } 
    }

    try:
        response = requests.post(messenger_url, params=params, headers=headers, json=data)
        response.raise_for_status() # Lève une exception en cas d'erreur
        logging.info(f"Message envoyé à {recipient_id} avec succès.")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Erreur lors de l'envoi du message à {recipient_id}: {e}")
        logging.error(f"Réponse détaillée de Facebook: {response.text if 'response' in locals() else 'N/A'}")
        return False

if __name__ == '__main__':
    # Vérification des variables d'environnement critiques au démarrage
    if not all([ACCESS_TOKEN, VERIFY_TOKEN]):
        logging.critical("CRITICAL: Les variables d'environnement (ACCESS_TOKEN, VERIFY_TOKEN) ne sont pas toutes définies.")
        # Ne pas exécuter l'application si la configuration est incomplète
        exit(1)
        
    logging.info("Démarrage de l'application Flask...")
    # NOTE: Pour la production, utilisez un serveur WSGI comme Gunicorn (ex: gunicorn app:app)
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))
