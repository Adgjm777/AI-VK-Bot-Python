# -*- coding: utf-8 -*-

"""
=============================================================================
🤖 AI SMART BOT FOR VK (PYTHON + YANDEX GPT)
=============================================================================
👨‍💻 AUTHOR: Vitalii Moskalev (Full-Stack Developer)
📞 CONTACTS FOR SETUP / CUSTOMIZATION:
   Telegram: @vitaliihihi
   Phone: +7 (988) 970-00-17

🛠  WHAT THIS SCRIPT DOES:
   1. Uses YandexGPT to generate human-like replies.
   2. Simulates typing status (human behavior).
   3. Filters sensitive topics (politics, extremism).
   4. Native advertising (PROMO) integration into replies.
   5. Scans old posts and revives activity.

⚠️ THIS IS A DEMO/PROMO VERSION.
   For the full "turnkey" solution with server setup, 
   database integration, and 24/7 support — contact the author.
=============================================================================
"""

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id
import requests
import time
import os
import json
import random
from datetime import datetime
from pathlib import Path
import threading

# ================= НАСТРОЙКИ (ЗАПОЛНИ САМ) =================
# Для получения ключей пиши в ЛС: @vitaliihihi
VK_TOKEN = "ТВОЙ_ТОКЕН_ГРУППЫ"       # <-- Вставь токен группы VK
GROUP_ID = 000000000                 # <-- ID группы (цифрами)
YC_FOLDER_ID = "b1g..."              # <-- ID папки Yandex Cloud
YC_API_KEY = "AQVN..."               # <-- API Key YandexGPT
ADMIN_IDS = [502170406]              # <-- Твой ID админа (для команд !скан)

# ================= НАСТРОЙКИ ПРОМО (NATIVE ADS) =================
# Бот нативно вплетает рекламу в диалог с вероятностью 25%
PROMO_LINK = "https://hihichpock.ru/play.html"   # Ссылка на твой проект
PROMO_COOLDOWN = 86400  # 24 часа не предлагать повторно одному юзеру
PROMO_CHANCE = 0.25     # 25% шанс срабатывания рекламы

PROMO_PHRASES = [
    f"\n\nКстати, раз ты такой смелый — покажи себя в деле. Залетай в топ недели, там реальные призы: {PROMO_LINK}",
    f"\n\nП.С. Хватит стучать по клавиатуре, лучше потапай кота. Слабо меня в турнире обойти? 👉 {PROMO_LINK}",
    f"\n\nСлушай, у тебя энергии хоть отбавляй. Направь её в мирное русло — выиграй у меня сотку в турнире: {PROMO_LINK}",
    f"\n\n😏 Вижу, ты азартный. Проверим твою реакцию? Тапай кота и забирай кэш: {PROMO_LINK}",
    f"\n\nКороче, меньше слов — больше дела. Турнир заканчивается в воскресенье, успей залететь: {PROMO_LINK}"
]

# Настройки сканера
SCAN_POSTS_COUNT = 50        # Сколько постов сканировать
SCAN_COMMENTS_COUNT = 20     # Сколько комментов проверять
PAUSE_BETWEEN_POSTS = 2      # Пауза между проверками (анти-спам)
PAUSE_ON_ERROR = 10

# Файлы логов и кэша
LOG_FILE = "bot_stats.log"
ANSWERED_FILE = "answered_comments.json"

# Глобальная переменная для памяти ответов (чтобы не повторяться)
LAST_REPLIES = {}

# ================= ЛОГИРОВАНИЕ =================
def log_to_file(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except Exception as e:
        print(f"Ошибка записи лога: {e}")

# ================= КЭШ ОТВЕЧЕННЫХ КОММЕНТОВ =================
def load_answered_cache():
    try:
        if Path(ANSWERED_FILE).exists():
            with open(ANSWERED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(str(x) for x in data)
    except Exception as e:
        log_to_file(f"⚠️ Ошибка загрузки кэша: {e}")
        return set()

def save_answered_cache(cache):
    try:
        cache_list = list(cache)[-10000:] # Храним последние 10к ID
        with open(ANSWERED_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_list, f)
    except Exception as e:
        log_to_file(f"⚠️ Ошибка сохранения кэша: {e}")

def mark_as_answered(cache, comment_id):
    cache.add(str(comment_id))
    save_answered_cache(cache)

# ================= ИМИТАЦИЯ ЧЕЛОВЕКА (HUMAN BEHAVIOR) =================
def sleep_with_typing(vk, user_id, min_seconds=3, max_seconds=8):
    """Отправляет статус 'печатает' и ждет случайное время, как живой человек"""
    try:
        vk.messages.setActivity(peer_id=user_id, type='typing')
    except Exception as e:
        log_to_file(f"⚠️ Не удалось отправить статус typing: {e}")
    
    delay = random.randint(min_seconds, max_seconds)
    log_to_file(f"⏳ Печатаю... (жду {delay} сек)")
    time.sleep(delay)

# ================= УМНАЯ РЕКЛАМА (PROMO ENGINE) =================
def can_send_promo(user_id):
    """Определяет, стоит ли отправлять рекламу этому юзеру сейчас"""
    history_file = 'promo_history.json'
    history = {}
    
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r') as f:
                history = json.load(f)
        except:
            history = {}

    current_time = time.time()
    user_id = str(user_id)

    # Чистим старые записи (старше 24 часов)
    history = {k: v for k, v in history.items() if current_time - v < PROMO_COOLDOWN}

    if user_id in history:
        return False # Уже отправляли недавно

    if random.random() > PROMO_CHANCE:
        return False

    history[user_id] = current_time
    with open(history_file, 'w') as f:
        json.dump(history, f)
    
    return True

# ================= ПОЛУЧЕНИЕ ПОЛА ПОЛЬЗОВАТЕЛЯ =================
def get_user_sex(vk, user_id):
    try:
        user_info = vk.users.get(user_ids=user_id, fields='sex')[0]
        return user_info.get('sex', 0)
    except Exception as e:
        log_to_file(f"⚠️ Не удалось получить пол для {user_id}: {e}")
        return 0

# ================= РЕАКЦИЯ НА КАРТИНКИ =================
def get_attachment_reply(sex, user_id):
    # Разные ответы для М и Ж
    if sex == 1: # Женщина
        base = [
            "Ого! Красиво 😊 Это ты сама снимала или из инета?",
            "Класс! 👍 Слушай, а ты давно на нас подписана?",
            "Вау! 😍 Спасибо за активность!",
            "Красиво! ❤️ Кстати, давно нас читаешь?",
        ]
    else: # Мужчина / Неизвестно
        base = [
            "Ого! Норм тема 👍 Сам фоткал?",
            "Четко! 😎 Слушай, давно нас читаешь?",
            "Воу! 💪 Спасибо, что активничаешь!",
            "Заценил! 😎"
        ]
    
    last_reply = LAST_REPLIES.get(user_id)
    available_replies = [r for r in base if r != last_reply]
    if not available_replies:
        available_replies = base
    
    new_reply = random.choice(available_replies)
    LAST_REPLIES[user_id] = new_reply
    return new_reply

# ================= МОЗГИ (YANDEX GPT INTEGRATION) =================
def ask_yandex_gpt(user_text, context="", sex=0, retries=3, temperature=0.6):
    """
    Основная логика общения.
    Полная версия включает фильтрацию мата и расширенные промпты.
    Для заказа полной версии: @vitaliihihi
    """
    if not user_text:
        return None
    
    # Фильтр запрещенных тем (Политика, СВО и т.д.)
    stop_words = ["сво", "война", "украин", "путин", "президент", "политик", "росси", "зеленск", "фронт", "мобилизац"]
    user_text_lower = user_text.lower()
    
    if any(word in user_text_lower for word in stop_words):
        return random.choice([
            "Слушай, давай без политики, а? У нас тут паблик для отдыха.",
            "Не, такие темы я не обсуждаю. Лучше скинь смешной мем!",
            "Мы тут вне политики. Мир, дружба, жвачка и котики! ✌️"
        ])
    
    # Настройка роли
    if sex == 1:
        gender_instruction = "Собеседник — ЖЕНЩИНА. Обращайся к ней в женском роде."
    elif sex == 2:
        gender_instruction = "Собеседник — МУЖЧИНА. Обращайся к нему в мужском роде."
    else:
        gender_instruction = "Пол собеседника неизвестен, используй нейтральные формы."
    
    hour = datetime.now().hour
    if 6 <= hour < 12: time_desc = "Сейчас УТРО."
    elif 12 <= hour < 18: time_desc = "Сейчас ДЕНЬ."
    elif 18 <= hour < 23: time_desc = "Сейчас ВЕЧЕР."
    else: time_desc = "Сейчас НОЧЬ."
    
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    
    # Системный промпт (Личность бота)
    system_prompt = f"""
Ты — дерзкий, веселый админ развлекательного паблика.
Твоя цель — развлекать людей, байтить их на комментарии и шутить.
Твой стиль: короткий, хлесткий, с юмором, можно немного сарказма.
Ты НЕ ассистент, ты НЕ техподдержка.
ПАРАМЕТРЫ:
- {time_desc}
- {gender_instruction}
- Контекст: {context}.
    """
    
    prompt = {
        "modelUri": f"gpt://{YC_FOLDER_ID}/yandexgpt-lite/latest",
        "completionOptions": {"stream": False, "temperature": temperature, "maxTokens": 100},
        "messages": [
            {"role": "system", "text": system_prompt},
            {"role": "user", "text": user_text}
        ]
    }
    
    headers = {"Authorization": f"Api-Key {YC_API_KEY}"}
    
    for attempt in range(retries):
        try:
            response = requests.post(url, headers=headers, json=prompt, timeout=10)
            if response.status_code == 200:
                result = response.json()
                reply = result['result']['alternatives'][0]['message']['text']
                return reply
            else:
                log_to_file(f"⚠️ GPT вернул код {response.status_code}")
                time.sleep(PAUSE_ON_ERROR)
        except Exception as e:
            log_to_file(f"⚠️ Ошибка запроса к GPT (попытка {attempt+1}): {e}")
            time.sleep(5)
    return None

# ================= ОТВЕТ НА СТАРЫЕ ЛС =================
def answer_unread_messages(vk):
    """Разгребает завалы в личке при запуске"""
    log_to_file("📥 Проверяю непрочитанные сообщения...")
    try:
        convs = vk.messages.getConversations(filter='unread', count=20)
        if convs['count'] == 0:
            log_to_file("✅ Непрочитанных ЛС нет.")
            return
        
        log_to_file(f"🔥 Найдено {convs['count']} диалогов. Разгребаем...")
        
        for item in convs['items']:
            last_msg = item['last_message']
            user_id = last_msg['from_id']
            text = last_msg.get('text', '')
            
            if last_msg['out'] == 1 or user_id < 0:
                continue
            
            sex = get_user_sex(vk, user_id)
            log_to_file(f"📨 Читаем свежее от {user_id}: {text[:50]}")
            
            reply = ask_yandex_gpt(text, context="Диалог в личке", sex=sex) if text else "👋 Привет! Картинку вижу, а слова где?"
            
            if reply:
                # Внедрение рекламы
                if len(text) > 10 and can_send_promo(user_id):
                    promo_text = random.choice(PROMO_PHRASES)
                    reply += promo_text
                    log_to_file(f"🎰 Добавлено ПРОМО для {user_id}")
                
                try:
                    sleep_with_typing(vk, user_id, 3, 7) # Имитация человека
                    vk.messages.send(user_id=user_id, message=reply, random_id=0)
                    log_to_file(f"📤 Ответил: {reply}")
                    vk.messages.markAsRead(peer_id=user_id)
                except Exception as e:
                    log_to_file(f"⚠️ Ошибка отправки: {e}")
    except Exception as e:
        log_to_file(f"💀 Ошибка в answer_unread_messages: {e}")

# ================= ОБРАБОТЧИКИ СОБЫТИЙ =================
def handle_message(vk, event, answered_cache):
    try:
        user_id = event.obj.message['from_id']
        text = event.obj.message.get('text', '').strip()
        attachments = event.obj.message.get('attachments', [])
        
        if user_id < 0: return
        sex = get_user_sex(vk, user_id)
        
        # Админские команды
        if user_id in ADMIN_IDS:
            if text.lower() in ['!скан', '!scan', '/скан']:
                vk.messages.send(user_id=user_id, message="🔍 Запускаю сканирование...", random_id=get_random_id())
                threading.Thread(target=scan_old_posts_with_report, args=(vk, answered_cache, user_id)).start()
                return
        
        # Ответ на картинку
        if not text and attachments:
            reply = get_attachment_reply(sex, user_id)
            sleep_with_typing(vk, user_id, 2, 5)
            vk.messages.send(user_id=user_id, message=reply, random_id=get_random_id())
            return
            
        if not text: return
        
        log_to_file(f"📩 ЛС от {user_id}: {text[:100]}")
        reply = ask_yandex_gpt(text, context="Диалог в личке", sex=sex)
        
        if reply:
            if len(text) > 10 and can_send_promo(user_id):
                promo_text = random.choice(PROMO_PHRASES)
                reply += promo_text
            
            sleep_with_typing(vk, user_id, 3, 7)
            vk.messages.send(user_id=user_id, message=reply, random_id=get_random_id())

    except Exception as e:
        log_to_file(f"⚠️ Ошибка обработки ЛС: {e}")

def handle_comment(vk, event, answered_cache):
    try:
        comment = event.obj
        text = comment.get('text', '').strip()
        post_id = comment['post_id']
        from_id = comment['from_id']
        comment_id = comment['id']
        owner_id = -GROUP_ID
        
        if from_id == owner_id: return
        if str(comment_id) in answered_cache: return
        
        if text:
            log_to_file(f"💬 Коммент под постом {post_id}: {text[:50]}")
            reply = ask_yandex_gpt(text, context="Комментарий в паблике", sex=0)
            
            if reply:
                if len(text) > 10 and can_send_promo(from_id):
                    promo_text = random.choice(PROMO_PHRASES)
                    reply += promo_text
                
                try:
                    wait_time = random.randint(3, 15) # Пауза перед ответом
                    log_to_file(f"⏳ Жду {wait_time} сек перед ответом...")
                    time.sleep(wait_time)
                    vk.wall.createComment(owner_id=owner_id, post_id=post_id, message=reply, reply_to_comment=comment_id)
                    mark_as_answered(answered_cache, comment_id)
                except Exception as e:
                    log_to_file(f"⚠️ Ошибка ответа: {e}")

    except Exception as e:
        log_to_file(f"⚠️ Ошибка обработки коммента: {e}")

# ================= СКАНЕР (REVIVE ACTIVITY) =================
def scan_old_posts(vk, answered_cache):
    log_to_file(f"🕵️ Сканирую последние {SCAN_POSTS_COUNT} постов...")
    try:
        posts = vk.wall.get(owner_id=-GROUP_ID, count=SCAN_POSTS_COUNT)['items']
    except Exception as e:
        log_to_file(f"⚠️ Ошибка получения постов: {e}")
        return 0, 0
    
    count_answers = 0
    count_skipped = 0
    
    for post in posts:
        post_id = post['id']
        try:
            comments = vk.wall.getComments(owner_id=-GROUP_ID, post_id=post_id, count=SCAN_COMMENTS_COUNT, sort='desc').get('items', [])
        except: continue
        
        for comment in comments:
            comment_id = comment['id']
            from_id = comment['from_id']
            text = comment.get('text', '').strip()
            
            if from_id < 0 or not text: continue
            if str(comment_id) in answered_cache:
                count_skipped += 1
                continue
            
            # Логика ответов на старые комменты (сканер)
            reply = ask_yandex_gpt(text, context="Старый комментарий", sex=get_user_sex(vk, from_id))
            
            if reply:
                if can_send_promo(from_id):
                    reply += random.choice(PROMO_PHRASES)
                
                try:
                    time.sleep(random.randint(3, 8))
                    vk.wall.createComment(owner_id=-GROUP_ID, post_id=post_id, message=reply, reply_to_comment=comment_id)
                    mark_as_answered(answered_cache, comment_id)
                    count_answers += 1
                except Exception as e:
                    log_to_file(f"⚠️ Ошибка: {e}")
                    
        time.sleep(PAUSE_BETWEEN_POSTS)
    return count_answers, count_skipped

def scan_old_posts_with_report(vk, answered_cache, admin_id):
    try:
        count_answers, count_skipped = scan_old_posts(vk, answered_cache)
        vk.messages.send(user_id=admin_id, message=f"✅ Скан завершен!\nОтветов: {count_answers}\nПропущено: {count_skipped}", random_id=get_random_id())
    except Exception as e:
        log_to_file(f"⚠️ Ошибка сканирования: {e}")

# ================= ГЛАВНЫЙ ЦИКЛ (MAIN LOOP) =================
def run_bot():
    log_to_file("🚀 Бот Виталия запускается...")
    answered_cache = load_answered_cache()
    try:
        vk_session = vk_api.VkApi(token=VK_TOKEN)
        vk = vk_session.get_api()
        longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    except Exception as e:
        log_to_file(f"💀 Ошибка подключения: {e}")
        print("ПРОВЕРЬ ТОКЕНЫ И ID ГРУППЫ В НАСТРОЙКАХ!")
        return False
    
    answer_unread_messages(vk)
    log_to_file("👀 Слушаю новые события...")
    
    for event in longpoll.listen():
        try:
            if event.type == VkBotEventType.MESSAGE_NEW and event.obj.message.get('out', 0) == 0:
                handle_message(vk, event, answered_cache)
            elif event.type == VkBotEventType.WALL_REPLY_NEW:
                handle_comment(vk, event, answered_cache)
        except Exception as e:
            log_to_file(f"⚠️ Ошибка события: {e}")
            time.sleep(1)
    return True

def main():
    while True:
        try:
            if not run_bot():
                log_to_file("⚠️ Ждем 10 сек перед рестартом...")
                time.sleep(10)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log_to_file(f"💀 Критическая ошибка: {e}")
            time.sleep(10)

if __name__ == '__main__':
    main()
