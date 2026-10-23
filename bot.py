import asyncio
import os
import json
import re
import time
import logging
from html import escape
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, ChatMemberUpdatedFilter, JOIN_TRANSITION
from aiogram.types import ChatPermissions, ChatMemberUpdated, Message
from aiogram.exceptions import TelegramAPIError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("Переменная окружения BOT_TOKEN или TELEGRAM_BOT_TOKEN не задана")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Универсальный путь для данных: если папки нет, сохраняем прямо в директории бота
DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "storage.json")

WARN_MUTE_AT = 3
WARN_BAN_AT = 5
WARN_TTL = timedelta(days=7)

def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "filters": {int(cid): f for cid, f in data.get("filters", {}).items()},
                    "admins": {int(cid): list(set(a)) for cid, a in data.get("admins", {}).items() if a},
                    "moderators": {int(cid): list(set(m)) for cid, m in data.get("moderators", {}).items() if m},
                    "welcomes": {int(cid): w for cid, w in data.get("welcomes", {}).items()},
                    "rules": {int(cid): r for cid, r in data.get("rules", {}).items() if r},
                    "antiflood": {int(cid): limit for cid, limit in data.get("antiflood", {}).items()},
                    "warns": {int(cid): {int(uid): cnt for uid, cnt in u_warns.items() if cnt > 0} for cid, u_warns in data.get("warns", {}).items()},
                    "bans": {int(cid): list(set(b)) for cid, b in data.get("bans", {}).items() if b},
                    "logs": {int(cid): int(log_id) for cid, log_id in data.get("logs", {}).items()}
                }
        except (json.JSONDecodeError, ValueError):
            corrupt_path = f"{DB_FILE}.corrupt-{int(time.time())}"
            os.replace(DB_FILE, corrupt_path)
            logging.exception("storage.json поврежден и сохранен как %s", corrupt_path)
    return {"filters": {}, "admins": {}, "moderators": {}, "welcomes": {}, "rules": {}, "antiflood": {}, "warns": {}, "bans": {}, "logs": {}}

def save_data():
    try:
        clean_storage = {
            "filters": {cid: f for cid, f in STORAGE["filters"].items() if f},
            "admins": {cid: list(set(a)) for cid, a in STORAGE["admins"].items() if a},
            "moderators": {cid: list(set(m)) for cid, m in STORAGE["moderators"].items() if m},
            "welcomes": {cid: w for cid, w in STORAGE["welcomes"].items() if w},
            "rules": {cid: r for cid, r in STORAGE["rules"].items() if r},
            "antiflood": {cid: limit for cid, limit in STORAGE["antiflood"].items() if limit},
            "warns": {cid: {uid: cnt for uid, cnt in u_warns.items() if cnt > 0} for cid, u_warns in STORAGE["warns"].items() if u_warns},
            "bans": {cid: list(set(b)) for cid, b in STORAGE["bans"].items() if b},
            "logs": {cid: log_id for cid, log_id in STORAGE["logs"].items() if log_id}
        }
        tmp_file = DB_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(clean_storage, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, DB_FILE)
    except Exception as e:
        logging.exception("Ошибка при сохранении базы данных: %s", e)

STORAGE = load_data()

MIN_T, MAX_T = timedelta(seconds=30), timedelta(days=366)
TIME_RE = re.compile(r"^(\d{1,6})([smhd])$", re.IGNORECASE)
UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}

def parse_time(time_str: str) -> timedelta:
    if not time_str:
        raise ValueError("Срок не указан")
    match = TIME_RE.fullmatch(time_str)
    if not match:
        raise ValueError("Формат срока: 30s, 15m, 2h, 7d")
    delta = timedelta(**{UNITS[match.group(2).lower()]: int(match.group(1))})
    if not MIN_T <= delta <= MAX_T:
        raise ValueError("Срок должен быть от 30 секунд до 366 дней")
    return delta

def format_time_rus(time_str: str) -> str:
    match = TIME_RE.fullmatch(time_str.strip())
    if not match:
        return time_str
    num = int(match.group(1))
    unit = match.group(2).lower()
    
    if unit == 's':
        if num % 10 == 1 and num % 100 != 11: form = "секунду"
        elif 2 <= num % 10 <= 4 and (num % 100 < 10 or num % 100 >= 20): form = "секунды"
        else: form = "секунд"
        return f"{num} {form}"
    elif unit == 'm':
        if num % 10 == 1 and num % 100 != 11: form = "минуту"
        elif 2 <= num % 10 <= 4 and (num % 100 < 10 or num % 100 >= 20): form = "минуты"
        else: form = "минут"
        return f"{num} {form}"
    elif unit == 'h':
        if num % 10 == 1 and num % 100 != 11: form = "час"
        elif 2 <= num % 10 <= 4 and (num % 100 < 10 or num % 100 >= 20): form = "часа"
        else: form = "часов"
        return f"{num} {form}"
    elif unit == 'd':
        if num % 10 == 1 and num % 100 != 11: form = "день"
        elif 2 <= num % 10 <= 4 and (num % 100 < 10 or num % 100 >= 20): form = "дня"
        else: form = "дней"
        return f"{num} {form}"
    return time_str

async def is_creator(message: types.Message) -> bool:
    if message.chat.type == "private":
        return True
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status == "creator":
            return True
    except Exception:
        pass
    return False

async def is_admin_or_creator(message: types.Message) -> bool:
    if await is_creator(message):
        return True
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in STORAGE["admins"].get(chat_id, []):
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ("creator", "administrator"):
            return True
    except Exception:
        pass
    return False

async def is_staff(message: types.Message) -> bool:
    if await is_creator(message):
        return True
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in STORAGE["admins"].get(chat_id, []) or user_id in STORAGE["moderators"].get(chat_id, []):
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ("creator", "administrator"):
            return True
    except Exception:
        pass
    return False

async def extract_target_user(message: types.Message, command: CommandObject):
    r = message.reply_to_message
    if r and r.from_user and not r.forum_topic_created:
        return r.from_user.id, r.from_user.full_name
    if command and command.args:
        args = command.args.split()
        target = args[0]
        if re.fullmatch(r"\d{1,15}", target, re.ASCII):
            return int(target), f"ID {target}"
    return None, None

def parse_time_and_reason(message: types.Message, command: CommandObject, default_time: str = None):
    args_list = command.args.split() if command and command.args else []
    time_arg = default_time
    reason = None

    if message.reply_to_message:
        if len(args_list) >= 1:
            try:
                parse_time(args_list[0])
                time_arg = args_list[0]
                reason = " ".join(args_list[1:]) if len(args_list) > 1 else None
            except ValueError:
                reason = " ".join(args_list)
    else:
        if len(args_list) >= 2:
            try:
                parse_time(args_list[1])
                time_arg = args_list[1]
                reason = " ".join(args_list[2:]) if len(args_list) > 2 else None
            except ValueError:
                reason = " ".join(args_list[1:])
        elif len(args_list) == 1:
            try:
                parse_time(args_list[0])
                reason = None
            except ValueError:
                reason = args_list[0]

    return time_arg, reason

def mention(uid: int, name: str) -> str:
    return f'<a href="tg://user?id={uid}">{escape(name)}</a>'

def get_admin_mention(user: types.User) -> str:
    admin_name = f"@{user.username}" if user.username else user.full_name
    return mention(user.id, admin_name)

async def send_log(chat_id: int, log_text: str):
    target_log_id = STORAGE["logs"].get(chat_id)
    if not target_log_id:
        return
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    full_log = f"<b>Лог модерации</b>\n<b>Время:</b> <code>{now_str}</code>\n\n{log_text}"
    try:
        await bot.send_message(target_log_id, full_log)
    except Exception as e:
        logging.exception("Ошибка при отправке лога в чат %s: %s", target_log_id, e)

# ----------------- ПРАВИЛА ЧАТА (/rules, /setrules) -----------------

@dp.message(Command("rules"))
async def show_rules(message: types.Message):
    chat_id = message.chat.id
    rules_text = STORAGE["rules"].get(chat_id)
    if not rules_text:
        await message.reply("В этом чате еще не установлены правила. Администратор может задать их командой /setrules.")
        return
    await message.answer(f"<b>Правила чата:</b>\n\n{rules_text}")

@dp.message(Command("setrules"))
async def set_rules(message: types.Message, command: CommandObject):
    if not await is_admin_or_creator(message):
        return
    if not message.reply_to_message and not (command and command.args):
        await message.reply("Ответьте на сообщение с текстом правил или укажите текст после команды.")
        return

    chat_id = message.chat.id
    if message.reply_to_message and message.reply_to_message.text:
        rules_text = message.reply_to_message.html_text
    else:
        rules_text = escape(command.args)

    STORAGE["rules"][chat_id] = rules_text
    save_data()
    await message.reply("Правила этого чата успешно обновлены.")

# ----------------- ЧАТ ЛОГОВ (/setlogs, /logs, /clearlogs) -----------------

@dp.message(Command("setlogs"))
async def set_logs(message: types.Message, command: CommandObject):
    if not await is_admin_or_creator(message):
        return

    chat_id = message.chat.id
    target_log_id = None

    if command and command.args:
        arg = command.args.split()[0]
        try:
            target_log_id = int(arg)
        except ValueError:
            await message.reply("Укажите числовой ID чата логов, например: <code>/setlogs -100123456789</code>")
            return
    else:
        target_log_id = chat_id

    STORAGE["logs"][chat_id] = target_log_id
    save_data()
    await message.reply(f"Чат для логов успешно установлен: <code>{target_log_id}</code>.")

@dp.message(Command("logs"))
async def show_logs(message: types.Message):
    if not await is_admin_or_creator(message):
        return
    log_id = STORAGE["logs"].get(message.chat.id)
    if log_id:
        await message.reply(f"Текущий чат логов: <code>{log_id}</code>")
    else:
        await message.reply("Чат логов не привязан. Установите его командой /setlogs.")

@dp.message(Command("clearlogs"))
async def clear_logs(message: types.Message):
    if not await is_admin_or_creator(message):
        return
    chat_id = message.chat.id
    if chat_id in STORAGE["logs"]:
        del STORAGE["logs"][chat_id]
        save_data()
        await message.reply("Логирование для этого чата отключено.")
    else:
        await message.reply("Чат логов не был установлен.")

# ----------------- УПРАВЛЕНИЕ СТАФФОМ (/staff, ролями) -----------------

@dp.message(Command("staff"))
async def list_staff(message: types.Message):
    chat_id = message.chat.id
    admins = STORAGE["admins"].get(chat_id, [])
    moderators = STORAGE["moderators"].get(chat_id, [])

    text = "<b>Состав стаффа чата:</b>\n\n"
    
    owner_str = "Создатель группы"
    try:
        members = await bot.get_chat_administrators(chat_id)
        for m in members:
            if m.status == "creator":
                owner_name = f"@{m.user.username}" if m.user.username else m.user.first_name
                owner_str = mention(m.user.id, owner_name)
                break
    except Exception:
        pass

    text += f"<b>Владелец:</b> {owner_str}\n"
    
    text += "\n<b>Администраторы:</b>\n"
    if admins:
        for uid in admins:
            try:
                member = await bot.get_chat_member(chat_id, uid)
                user = member.user
                name = f"@{user.username}" if user.username else user.first_name
                text += f"- {mention(uid, name)}\n"
            except Exception:
                text += f"- ID: <code>{uid}</code>\n"
    else:
        text += "- Отсутствуют\n"

    text += "\n<b>Модераторы:</b>\n"
    if moderators:
        for uid in moderators:
            try:
                member = await bot.get_chat_member(chat_id, uid)
                user = member.user
                name = f"@{user.username}" if user.username else user.first_name
                text += f"- {mention(uid, name)}\n"
            except Exception:
                text += f"- ID: <code>{uid}</code>\n"
    else:
        text += "- Отсутствуют"

    await message.answer(text)

@dp.message(Command("botadmin"))
async def add_bot_admin(message: types.Message, command: CommandObject):
    if not await is_creator(message):
        await message.reply("Только владелец группы может назначать администраторов.")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("Ответьте на сообщение пользователя или укажите его ID.")
        return

    chat_id = message.chat.id
    if chat_id not in STORAGE["admins"]:
        STORAGE["admins"][chat_id] = []

    if chat_id in STORAGE["moderators"] and target_id in STORAGE["moderators"][chat_id]:
        STORAGE["moderators"][chat_id].remove(target_id)

    if target_id in STORAGE["admins"][chat_id]:
        await message.reply(f"У пользователя {mention(target_id, target_name)} уже есть роль Администратора.")
        return

    STORAGE["admins"][chat_id].append(target_id)
    save_data()
    await message.reply(f"Пользователю {mention(target_id, target_name)} успешно присвоена роль <b>Администратора</b>.")

@dp.message(Command("unbotadmin"))
async def remove_bot_admin(message: types.Message, command: CommandObject):
    if not await is_creator(message):
        await message.reply("Только владелец группы может снимать администраторов.")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("Ответьте на сообщение пользователя или укажите его ID.")
        return

    chat_id = message.chat.id
    if chat_id in STORAGE["admins"] and target_id in STORAGE["admins"][chat_id]:
        STORAGE["admins"][chat_id].remove(target_id)
        save_data()
        await message.reply(f"Роль Администратора у {mention(target_id, target_name)} отозвана.")
    else:
        await message.reply(f"Пользователь {mention(target_id, target_name)} не найден в списке администраторов.")

@dp.message(Command("botmoderator"))
async def add_bot_moderator(message: types.Message, command: CommandObject):
    if not await is_admin_or_creator(message):
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("Ответьте на сообщение пользователя или укажите его ID.")
        return

    chat_id = message.chat.id
    if chat_id not in STORAGE["moderators"]:
        STORAGE["moderators"][chat_id] = []

    if target_id in STORAGE["moderators"][chat_id]:
        await message.reply(f"У пользователя {mention(target_id, target_name)} уже есть роль Модератора.")
        return

    STORAGE["moderators"][chat_id].append(target_id)
    save_data()
    await message.reply(f"Пользователю {mention(target_id, target_name)} успешно присвоена роль <b>Модератора</b>.")

@dp.message(Command("unbotmoderator"))
async def remove_bot_moderator(message: types.Message, command: CommandObject):
    if not await is_admin_or_creator(message):
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("Ответьте на сообщение пользователя или укажите его ID.")
        return

    chat_id = message.chat.id
    if chat_id in STORAGE["moderators"] and target_id in STORAGE["moderators"][chat_id]:
        STORAGE["moderators"][chat_id].remove(target_id)
        save_data()
        await message.reply(f"Роль Модератора у {mention(target_id, target_name)} отозвана.")
    else:
        await message.reply(f"Пользователь {mention(target_id, target_name)} не найден в списке модераторов.")

# ----------------- ФИЛЬТРЫ И АВТООТВЕТЫ -----------------

@dp.message(Command("filter"))
async def add_filter(message: types.Message, command: CommandObject):
    if not await is_admin_or_creator(message):
        return

    if not message.reply_to_message:
        await message.reply("Ответьте этой командой на сообщение, которое нужно привязать к фильтру.")
        return

    if not command.args:
        await message.reply("Укажите ключевое слово после команды.")
        return

    chat_id = message.chat.id
    trigger_word = command.args.strip().lower()
    reply = message.reply_to_message

    if chat_id not in STORAGE["filters"]:
        STORAGE["filters"][chat_id] = {}

    if reply.animation:
        STORAGE["filters"][chat_id][trigger_word] = {
            "type": "animation", 
            "file_id": reply.animation.file_id, 
            "caption": reply.caption or ""
        }
    elif reply.sticker:
        STORAGE["filters"][chat_id][trigger_word] = {"type": "sticker", "file_id": reply.sticker.file_id}
    elif reply.photo:
        STORAGE["filters"][chat_id][trigger_word] = {
            "type": "photo", 
            "file_id": reply.photo[-1].file_id, 
            "caption": reply.caption or ""
        }
    elif reply.video:
        STORAGE["filters"][chat_id][trigger_word] = {
            "type": "video", 
            "file_id": reply.video.file_id, 
            "caption": reply.caption or ""
        }
    elif reply.voice:
        STORAGE["filters"][chat_id][trigger_word] = {"type": "voice", "file_id": reply.voice.file_id}
    elif reply.text:
        STORAGE["filters"][chat_id][trigger_word] = {"type": "text", "text": reply.html_text}
    else:
        await message.reply("Этот тип сообщений не поддерживается.")
        return

    save_data()
    await message.reply(f"Сохранён фильтр на слово <b>'{escape(trigger_word)}'</b>.")

@dp.message(Command("stop"))
async def remove_filter(message: types.Message, command: CommandObject):
    if not await is_admin_or_creator(message):
        return

    if not command.args:
        await message.reply("Укажите ключевое слово, фильтр для которого нужно удалить.")
        return

    chat_id = message.chat.id
    trigger_word = command.args.strip().lower()

    if chat_id in STORAGE["filters"] and trigger_word in STORAGE["filters"][chat_id]:
        del STORAGE["filters"][chat_id][trigger_word]
        save_data()
        await message.reply(f"Фильтр <b>'{escape(trigger_word)}'</b> удалён.")
    else:
        await message.reply(f"Фильтр <b>'{escape(trigger_word)}'</b> не найден.")

@dp.message(Command("filters"))
async def list_filters(message: types.Message):
    chat_id = message.chat.id
    filters = STORAGE["filters"].get(chat_id, {})
    if not filters:
        await message.reply("В этом чате пока нет активных фильтров.")
        return

    sorted_words = sorted(filters.keys(), key=lambda w: (-len(w), w))
    lines = ["Список фильтров в чате:", *[f"- {escape(w)}" for w in sorted_words]]
    await message.reply("\n".join(lines))

# ----------------- ПРИВЕТСТВИЯ (WELCOME) -----------------

async def send_welcome_msg(chat_id: int, user_name: str):
    welcome_data = STORAGE["welcomes"].get(chat_id)
    if not welcome_data:
        return False

    content_type = welcome_data["type"]
    safe_name = escape(user_name)

    try:
        if content_type == "text":
            text = welcome_data["text"].replace("{name}", safe_name).replace("{first_name}", safe_name) if welcome_data.get("text") else f"Привет, {safe_name}!"
            await bot.send_message(chat_id, text)
        elif content_type == "animation":
            caption = welcome_data.get("caption", "").replace("{name}", safe_name).replace("{first_name}", safe_name) if welcome_data.get("caption") else None
            await bot.send_animation(chat_id, animation=welcome_data["file_id"], caption=caption)
        elif content_type == "photo":
            caption = welcome_data.get("caption", "").replace("{name}", safe_name).replace("{first_name}", safe_name) if welcome_data.get("caption") else None
            await bot.send_photo(chat_id, photo=welcome_data["file_id"], caption=caption)
        elif content_type == "sticker":
            await bot.send_sticker(chat_id, sticker=welcome_data["file_id"])
    except Exception as e:
        logging.exception("Ошибка при отправке приветствия: %s", e)
    return True

@dp.message(Command("setwelcome"))
async def set_welcome(message: types.Message):
    if not await is_admin_or_creator(message):
        return

    if not message.reply_to_message:
        await message.reply("Ответьте этой командой на сообщение, которое должно стать приветствием.")
        return

    chat_id = message.chat.id
    reply = message.reply_to_message

    if reply.animation:
        STORAGE["welcomes"][chat_id] = {"type": "animation", "file_id": reply.animation.file_id, "caption": reply.caption or ""}
    elif reply.sticker:
        STORAGE["welcomes"][chat_id] = {"type": "sticker", "file_id": reply.sticker.file_id}
    elif reply.photo:
        STORAGE["welcomes"][chat_id] = {"type": "photo", "file_id": reply.photo[-1].file_id, "caption": reply.caption or ""}
    elif reply.text:
        STORAGE["welcomes"][chat_id] = {"type": "text", "text": reply.html_text}
    else:
        await message.reply("Этот тип сообщений не поддерживается.")
        return

    save_data()
    await message.reply("Приветствие для новых участников успешно установлено.")

@dp.message(Command("welcome"))
async def show_welcome(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in STORAGE["welcomes"]:
        await message.reply("В этом чате ещё не установлено приветствие.")
        return

    await send_welcome_msg(chat_id, message.from_user.first_name)

@dp.message(Command("clearwelcome"))
async def clear_welcome(message: types.Message):
    if not await is_admin_or_creator(message):
        return

    chat_id = message.chat.id
    if chat_id in STORAGE["welcomes"]:
        del STORAGE["welcomes"][chat_id]
        save_data()
        await message.reply("Приветствие удалено.")
    else:
        await message.reply("В этом чате не было установлено приветствие.")

@dp.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def greet_new_members_event(event: ChatMemberUpdated):
    user = event.new_chat_member.user
    if user.is_bot:
        return
    await send_welcome_msg(event.chat.id, user.first_name)

# ----------------- АНТИФЛУД КОМАНДА -----------------

FLOOD_TRACKER = {}

@dp.message(Command("antiflood"))
async def set_antiflood(message: types.Message, command: CommandObject):
    if not await is_admin_or_creator(message):
        return
    if not command.args or not command.args.isdigit():
        current = STORAGE["antiflood"].get(message.chat.id, 5)
        await message.reply(f"Текущий лимит антифлуда: <b>{current} сообщений подряд</b> за короткое время.\nИзменить: <code>/antiflood [число]</code>")
        return

    limit = int(command.args)
    if limit < 2 or limit > 30:
        await message.reply("Лимит должен быть от 2 до 30 сообщений.")
        return

    STORAGE["antiflood"][message.chat.id] = limit
    save_data()
    await message.reply(f"Антифлуд успешно установлен на лимит: <b>{limit} сообщений подряд</b>.")

# ----------------- МОДЕРАЦИЯ И СИСТЕМА ВАРНОВ -----------------

@dp.message(Command("ban"))
async def ban_user(message: types.Message, command: CommandObject):
    if not await is_staff(message):
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("Ответьте на сообщение пользователя или укажите его ID.")
        return

    admin_mention = get_admin_mention(message.from_user)
    time_arg, reason = parse_time_and_reason(message, command)

    try:
        until_date = None
        time_text = "навсегда"
        if time_arg:
            duration = parse_time(time_arg)
            until_date = datetime.now(timezone.utc) + duration
            time_text = f"на <b>{format_time_rus(time_arg)}</b>"

        await bot.ban_chat_member(message.chat.id, target_id, until_date=until_date)
        chat_id = message.chat.id
        if chat_id not in STORAGE["bans"]:
            STORAGE["bans"][chat_id] = []
        if target_id not in STORAGE["bans"][chat_id]:
            STORAGE["bans"][chat_id].append(target_id)
            save_data()

        msg_text = (
            f"Пользователь {mention(target_id, target_name)} забанен {time_text}!\n"
            f"<b>Администратор:</b> {admin_mention}"
        )
        if reason:
            msg_text += f"\n<b>Причина:</b> {escape(reason)}"

        await message.answer(msg_text)
        await send_log(chat_id, msg_text)
    except ValueError as e:
        await message.reply(str(e))
    except TelegramAPIError as e:
        await message.answer(f"Не удалось забанить пользователя: {e}")

@dp.message(Command("kick"))
async def kick_user(message: types.Message, command: CommandObject):
    if not await is_staff(message):
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("Ответьте на сообщение пользователя или укажите его ID.")
        return

    admin_mention = get_admin_mention(message.from_user)
    _, reason = parse_time_and_reason(message, command)

    try:
        await bot.ban_chat_member(message.chat.id, target_id)
        try:
            await bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
        except TelegramAPIError:
            pass

        msg_text = (
            f"Пользователь {mention(target_id, target_name)} изгнан из чата!\n"
            f"<b>Администратор:</b> {admin_mention}"
        )
        if reason:
            msg_text += f"\n<b>Причина:</b> {escape(reason)}"

        await message.answer(msg_text)
        await send_log(message.chat.id, msg_text)
    except TelegramAPIError as e:
        await message.answer(f"Не удалось кикнуть пользователя: {e}")

@dp.message(Command("unban"))
async def unban_user(message: types.Message, command: CommandObject):
    if not await is_staff(message):
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("Ответьте на сообщение пользователя или укажите его ID.")
        return

    admin_mention = get_admin_mention(message.from_user)

    try:
        await bot.unban_chat_member(message.chat.id, target_id)
        chat_id = message.chat.id
        if chat_id in STORAGE["bans"] and target_id in STORAGE["bans"][chat_id]:
            STORAGE["bans"][chat_id].remove(target_id)
            save_data()

        msg_text = (
            f"Пользователь {mention(target_id, target_name)} разбанен!\n"
            f"<b>Администратор:</b> {admin_mention}"
        )
        await message.answer(msg_text)
        await send_log(chat_id, msg_text)
    except TelegramAPIError as e:
        await message.answer(f"Ошибка при разбане: {e}")

@dp.message(Command("mute"))
async def mute_user(message: types.Message, command: CommandObject):
    if not await is_staff(message):
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("Ответьте на сообщение пользователя или укажите его ID.")
        return

    admin_mention = get_admin_mention(message.from_user)
    time_arg, reason = parse_time_and_reason(message, command, default_time="1h")

    try:
        duration = parse_time(time_arg)
        until_date = datetime.now(timezone.utc) + duration

        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )

        msg_text = (
            f"Пользователь {mention(target_id, target_name)} замучен на <b>{format_time_rus(time_arg)}</b>!\n"
            f"<b>Администратор:</b> {admin_mention}"
        )
        if reason:
            msg_text += f"\n<b>Причина:</b> {escape(reason)}"

        await message.answer(msg_text)
        await send_log(message.chat.id, msg_text)
    except ValueError as e:
        await message.reply(str(e))
    except TelegramAPIError as e:
        await message.answer(f"Не удалось замутить пользователя: {e}")

@dp.message(Command("unmute"))
async def unmute_user(message: types.Message, command: CommandObject):
    if not await is_staff(message):
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("Ответьте на сообщение пользователя или укажите его ID.")
        return

    admin_mention = get_admin_mention(message.from_user)

    try:
        chat = await bot.get_chat(message.chat.id)
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=chat.permissions
        )
        msg_text = (
            f"С пользователя {mention(target_id, target_name)} сняты ограничения!\n"
            f"<b>Администратор:</b> {admin_mention}"
        )
        await message.answer(msg_text)
        await send_log(message.chat.id, msg_text)
    except TelegramAPIError as e:
        await message.answer(f"Ошибка при снятии мута: {e}")

@dp.message(Command("warn"))
async def warn_user(message: types.Message, command: CommandObject):
    if not await is_staff(message):
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("Ответьте на сообщение пользователя или укажите его ID.")
        return

    admin_mention = get_admin_mention(message.from_user)
    time_arg, reason = parse_time_and_reason(message, command, default_time="7d")
    
    try:
        parse_time(time_arg)
    except ValueError as e:
        await message.reply(str(e))
        return

    chat_id = message.chat.id
    if chat_id not in STORAGE["warns"]:
        STORAGE["warns"][chat_id] = {}

    current_warns = STORAGE["warns"][chat_id].get(target_id, 0) + 1
    progress_mute = min(current_warns, WARN_MUTE_AT)
    progress_ban = min(current_warns, WARN_BAN_AT)

    try:
        if current_warns >= WARN_BAN_AT:
            await bot.ban_chat_member(chat_id, target_id)
            STORAGE["warns"][chat_id][target_id] = 0
            if chat_id not in STORAGE["bans"]:
                STORAGE["bans"][chat_id] = []
            if target_id not in STORAGE["bans"][chat_id]:
                STORAGE["bans"][chat_id].append(target_id)
            save_data()

            msg_text = (
                f"Пользователь {mention(target_id, target_name)} получил <b>5/5</b> предупреждений и забанен навсегда!\n"
                f"<b>Администратор:</b> {admin_mention}\n"
                f"предупреждений до мута: 3/3\n"
                f"предупреждений до бана: 5/5"
            )
            if reason:
                msg_text += f"\n<b>Причина:</b> {escape(reason)}"
            await message.answer(msg_text)
            await send_log(chat_id, msg_text)
            return

        elif current_warns == WARN_MUTE_AT:
            until_date = datetime.now(timezone.utc) + timedelta(days=1)
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            STORAGE["warns"][chat_id][target_id] = current_warns
            save_data()

            msg_text = (
                f"Пользователь {mention(target_id, target_name)} получил <b>3/5</b> предупреждений и замучен на <b>1 день</b>!\n"
                f"<b>Администратор:</b> {admin_mention}\n"
                f"предупреждений до мута: 3/3\n"
                f"предупреждений до бана: 3/5"
            )
            if reason:
                msg_text += f"\n<b>Причина:</b> {escape(reason)}"
            await message.answer(msg_text)
            await send_log(chat_id, msg_text)
            return

        else:
            STORAGE["warns"][chat_id][target_id] = current_warns
            save_data()

            msg_text = (
                f"Пользователю {mention(target_id, target_name)} выдано предупреждение.\n"
                f"<b>Администратор:</b> {admin_mention}\n"
                f"предупреждений до мута: {progress_mute}/3\n"
                f"предупреждений до бана: {progress_ban}/5\n"
                f"Срок действия: {format_time_rus(time_arg)}"
            )
            if reason:
                msg_text += f"\n<b>Причина:</b> {escape(reason)}"
            await message.answer(msg_text)
            await send_log(chat_id, msg_text)

    except TelegramAPIError as e:
        await message.answer(f"Не удалось применить наказание: {e}")

@dp.message(Command("unwarn"))
async def unwarn_user(message: types.Message, command: CommandObject):
    if not await is_staff(message):
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("Ответьте на сообщение пользователя или укажите его ID.")
        return

    admin_mention = get_admin_mention(message.from_user)
    chat_id = message.chat.id
    current_warns = STORAGE["warns"].get(chat_id, {}).get(target_id, 0)

    if current_warns > 0:
        new_warns = current_warns - 1
        if new_warns == 0:
            del STORAGE["warns"][chat_id][target_id]
            if not STORAGE["warns"][chat_id]:
                del STORAGE["warns"][chat_id]
        else:
            STORAGE["warns"][chat_id][target_id] = new_warns
        save_data()

        progress_mute = min(new_warns, WARN_MUTE_AT)
        progress_ban = min(new_warns, WARN_BAN_AT)

        msg_text = (
            f"С пользователя {mention(target_id, target_name)} снято предупреждение.\n"
            f"<b>Администратор:</b> {admin_mention}\n"
            f"предупреждений до мута: {progress_mute}/3\n"
            f"предупреждений до бана: {progress_ban}/5"
        )
        await message.answer(msg_text)
        await send_log(chat_id, msg_text)
    else:
        await message.reply(f"У пользователя {mention(target_id, target_name)} нет активных предупреждений.")

@dp.message(Command("warns"))
async def check_warns(message: types.Message, command: CommandObject):
    chat_id = message.chat.id
    target_id, target_name = await extract_target_user(message, command)

    if target_id and target_id != message.from_user.id:
        if not await is_staff(message):
            return
    else:
        target_id = message.from_user.id
        target_name = message.from_user.first_name

    warns_count = STORAGE["warns"].get(chat_id, {}).get(target_id, 0)
    progress_mute = min(warns_count, WARN_MUTE_AT)
    progress_ban = min(warns_count, WARN_BAN_AT)

    msg_text = (
        f"Количество предупреждений у пользователя {mention(target_id, target_name)}:\n"
        f"предупреждений до мута: {progress_mute}/3\n"
        f"предупреждений до бана: {progress_ban}/5"
    )
    await message.answer(msg_text)

@dp.message(Command("resetwarns"))
async def reset_warns(message: types.Message, command: CommandObject):
    if not await is_staff(message):
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("Ответьте на сообщение пользователя или укажите его ID.")
        return

    admin_mention = get_admin_mention(message.from_user)
    chat_id = message.chat.id
    if chat_id in STORAGE["warns"] and target_id in STORAGE["warns"][chat_id]:
        del STORAGE["warns"][chat_id][target_id]
        if not STORAGE["warns"][chat_id]:
            del STORAGE["warns"][chat_id]
        save_data()

    msg_text = (
        f"Предупреждения пользователя {mention(target_id, target_name)} сброшены.\n"
        f"<b>Администратор:</b> {admin_mention}"
    )
    await message.answer(msg_text)
    await send_log(chat_id, msg_text)

# ----------------- ОБРАБОТЧИК СООБЩЕНИЙ (АНТИФЛУД И ФИЛЬТРЫ) -----------------

@dp.message(F.text)
async def check_messages_and_filters(message: types.Message):
    if not message.chat or message.chat.type == "private" or not message.from_user:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    msg_text_raw = message.text.strip()

    # Проверка антифлуда (мгновенная проверка одинаковых сообщений подряд)
    if not await is_staff(message):
        limit = STORAGE["antiflood"].get(chat_id, 5)
        now = time.time()
        
        if chat_id not in FLOOD_TRACKER:
            FLOOD_TRACKER[chat_id] = {}
        
        last_time, last_text, count = FLOOD_TRACKER[chat_id].get(user_id, (0, "", 0))
        
        if now - last_time > 5.0 or last_text != msg_text_raw.lower():
            count = 1
        else:
            count += 1
            
        FLOOD_TRACKER[chat_id][user_id] = (now, msg_text_raw.lower(), count)

        if count >= limit:
            FLOOD_TRACKER[chat_id][user_id] = (0, "", 0)
            
            if chat_id not in STORAGE["warns"]:
                STORAGE["warns"][chat_id] = {}
            current_warns = STORAGE["warns"][chat_id].get(user_id, 0) + 1
            STORAGE["warns"][chat_id][user_id] = current_warns
            save_data()

            try:
                if current_warns >= WARN_BAN_AT:
                    await bot.ban_chat_member(chat_id, user_id)
                    STORAGE["warns"][chat_id][user_id] = 0
                    save_data()
                    log_msg = f"Пользователь {mention(user_id, message.from_user.first_name)} забанен за флуд (достигнут лимит 5 варнов)."
                    await message.answer(log_msg)
                    await send_log(chat_id, log_msg)
                elif current_warns == WARN_MUTE_AT:
                    until_date = datetime.now(timezone.utc) + timedelta(days=1)
                    await bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False), until_date=until_date)
                    save_data()
                    log_msg = f"Пользователь {mention(user_id, message.from_user.first_name)} замучен на <b>1 день</b> за флуд (3 варна)."
                    await message.answer(log_msg)
                    await send_log(chat_id, log_msg)
                else:
                    log_msg = f"Пользователь {mention(user_id, message.from_user.first_name)} получает предупреждение за флуд ({current_warns}/5). Срок: 1 неделя."
                    await message.answer(log_msg)
                    await send_log(chat_id, log_msg)
            except TelegramAPIError:
                pass
            return

    # Проверка текстовых фильтров
    filters = STORAGE["filters"].get(chat_id)
    if not filters:
        return

    text_lower = msg_text_raw.lower()
    words_in_message = text_lower.split()

    for trigger_word, content in filters.items():
        if " " in trigger_word:
            match_found = trigger_word in text_lower
        else:
            match_found = trigger_word in words_in_message

        if match_found:
            content_type = content["type"]
            try:
                if content_type == "text":
                    await message.reply(content["text"])
                elif content_type == "animation":
                    await message.reply_animation(
                        animation=content["file_id"], 
                        caption=content.get("caption") if content.get("caption") else None
                    )
                elif content_type == "sticker":
                    await message.reply_sticker(sticker=content["file_id"])
                elif content_type == "photo":
                    await message.reply_photo(
                        photo=content["file_id"], 
                        caption=content.get("caption") if content.get("caption") else None
                    )
                elif content_type == "video":
                    await message.reply_video(
                        video=content["file_id"], 
                        caption=content.get("caption") if content.get("caption") else None
                    )
                elif content_type == "voice":
                    await message.reply_voice(voice=content["file_id"])
            except TelegramAPIError:
                logging.exception("filter send failed")
            break

async def main():
    logging.info("Бот-модератор успешно запущен!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
