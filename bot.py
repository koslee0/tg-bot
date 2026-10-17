import asyncio
import os
import json
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatPermissions

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Путь к хранилищу Volume
DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "storage.json")

# Структура данных по умолчанию:
# {
#   "filters": { chat_id: { "word": content } },
#   "bot_admins": { chat_id: [ user_id1, user_id2 ] },
#   "welcomes": { chat_id: content },
#   "warns": { chat_id: { user_id: count } },
#   "bans": { chat_id: [ user_id1, user_id2 ] }
# }

def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "filters": {int(cid): f for cid, f in data.get("filters", {}).items()},
                    "bot_admins": {int(cid): a for cid, a in data.get("bot_admins", {}).items()},
                    "welcomes": {int(cid): w for cid, w in data.get("welcomes", {}).items()},
                    "warns": {int(cid): {int(uid): cnt for uid, cnt in u_warns.items()} for cid, u_warns in data.get("warns", {}).items()},
                    "bans": {int(cid): b for cid, b in data.get("bans", {}).items()}
                }
        except Exception as e:
            print(f"Ошибка при загрузке базы данных: {e}")
    return {"filters": {}, "bot_admins": {}, "welcomes": {}, "warns": {}, "bans": {}}

def save_data():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(STORAGE, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Ошибка при сохранении базы данных: {e}")

STORAGE = load_data()

# ----------------- ПРОВЕРКА ПРАВ (Итог: Создатель или Админ из Вайтлиста) -----------------
async def is_bot_admin(message: types.Message) -> bool:
    if message.chat.type == "private":
        return True
    
    chat_id = message.chat.id
    user_id = message.from_user.id

    member = await bot.get_chat_member(chat_id, user_id)
    
    # Владелец группы всегда имеет доступ
    if member.status == "creator":
        return True

    # Проверка вайтлиста админов бота для этого чата
    allowed_admins = STORAGE["bot_admins"].get(chat_id, [])
    if user_id in allowed_admins:
        return True

    return False

def parse_time(time_str: str) -> timedelta | None:
    """Парсит строки типа 10m, 2h, 1d в timedelta"""
    if not time_str:
        return None
    match = re.match(r"^(\d+)([smhd])$", time_str.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == "s": return timedelta(seconds=value)
    if unit == "m": return timedelta(minutes=value)
    if unit == "h": return timedelta(hours=value)
    if unit == "d": return timedelta(days=value)
    return None

async def extract_target_user(message: types.Message, command: CommandObject):
    """Вспомогательная функция для получения user_id из ответа на сообщение или аргументов"""
    if message.reply_to_message:
        return message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name
    
    if command.args:
        args = command.args.split()
        target = args[0]
        if target.isdigit():
            return int(target), f"ID {target}"
        elif target.startswith("@"):
            # Для получения ID по юзернейму нужен поиск в чате или передача объектом
            await message.reply("⚠️ Если пользователю не отвечают на сообщение, укажите его цифровой Telegram ID!")
            return None, None
    return None, None

# ----------------- 1. УПРАВЛЕНИЕ ВАЙТЛИСТОМ АДМИНОВ -----------------

@dp.message(Command("botadmin"))
async def add_bot_admin(message: types.Message, command: CommandObject):
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status != "creator" and message.chat.type != "private":
        await message.reply("❌ Только создатель (владелец) группы может выдавать доступ к администрированию бота!")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("⚠️ Ответьте на сообщение администратора или укажите его ID после команды!\nПример: `/botadmin 123456789`", parse_mode="Markdown")
        return

    chat_id = message.chat.id
    if chat_id not in STORAGE["bot_admins"]:
        STORAGE["bot_admins"][chat_id] = []

    if target_id in STORAGE["bot_admins"][chat_id]:
        await message.reply(f"ℹ️ У пользователя **{target_name}** уже есть доступ к боту.", parse_mode="Markdown")
        return

    STORAGE["bot_admins"][chat_id].append(target_id)
    save_data()
    await message.reply(f"✅ Пользователю **{target_name}** успешно выдан доступ к командам бота!", parse_mode="Markdown")

@dp.message(Command("unbotadmin"))
async def remove_bot_admin(message: types.Message, command: CommandObject):
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status != "creator" and message.chat.type != "private":
        await message.reply("❌ Только создатель группы может забирать доступ к боту!")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("⚠️ Ответьте на сообщение администратора или укажите его ID!", parse_mode="Markdown")
        return

    chat_id = message.chat.id
    if chat_id in STORAGE["bot_admins"] and target_id in STORAGE["bot_admins"][chat_id]:
        STORAGE["bot_admins"][chat_id].remove(target_id)
        save_data()
        await message.reply(f"🗑️ Доступ к командам бота у **{target_name}** отозван!", parse_mode="Markdown")
    else:
        await message.reply(f"❓ Пользователь **{target_name}** не был в вайтлисте бота.")

@dp.message(Command("botadmins"))
async def list_bot_admins(message: types.Message):
    chat_id = message.chat.id
    admins = STORAGE["bot_admins"].get(chat_id, [])
    if not admins:
        await message.reply("📜 Управлять ботом в этом чате сейчас может только создатель группы.")
        return
    
    text = "📜 **Вайтлист администраторов бота:**\n" + "\n".join([f"• ID: `{uid}`" for uid in admins])
    await message.reply(text, parse_mode="Markdown")

# ----------------- 2. ФИЛЬТРЫ -----------------

@dp.message(Command("filter"))
async def add_filter(message: types.Message, command: CommandObject):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав для управления фильтрами бота!")
        return

    if not message.reply_to_message:
        await message.reply("⚠️ Ответьте этой командой на сообщение которое хотите привязать!")
        return

    if not command.args:
        await message.reply("⚠️ Укажите ключевое слово после команды.\nПример: `/filter привет`", parse_mode="Markdown")
        return

    chat_id = message.chat.id
    trigger_word = command.args.strip().lower()
    reply = message.reply_to_message

    if chat_id not in STORAGE["filters"]:
        STORAGE["filters"][chat_id] = {}

    if reply.animation:
        STORAGE["filters"][chat_id][trigger_word] = {"type": "animation", "file_id": reply.animation.file_id, "caption": reply.caption}
    elif reply.sticker:
        STORAGE["filters"][chat_id][trigger_word] = {"type": "sticker", "file_id": reply.sticker.file_id}
    elif reply.photo:
        STORAGE["filters"][chat_id][trigger_word] = {"type": "photo", "file_id": reply.photo[-1].file_id, "caption": reply.caption}
    elif reply.video:
        STORAGE["filters"][chat_id][trigger_word] = {"type": "video", "file_id": reply.video.file_id, "caption": reply.caption}
    elif reply.voice:
        STORAGE["filters"][chat_id][trigger_word] = {"type": "voice", "file_id": reply.voice.file_id}
    elif reply.text:
        STORAGE["filters"][chat_id][trigger_word] = {"type": "text", "text": reply.text}
    else:
        await message.reply("❌ Этот тип сообщений пока не поддерживается.")
        return

    save_data()
    await message.reply(f"✅ Фильтр на слово **'{trigger_word}'** успешно сохранен!", parse_mode="Markdown")

@dp.message(Command("stop"))
async def remove_filter(message: types.Message, command: CommandObject):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав для удаления фильтров!")
        return

    if not command.args:
        await message.reply("⚠️ Укажите слово, фильтр для которого нужно удалить.\nПример: `/stop привет`", parse_mode="Markdown")
        return

    chat_id = message.chat.id
    trigger_word = command.args.strip().lower()

    if chat_id in STORAGE["filters"] and trigger_word in STORAGE["filters"][chat_id]:
        del STORAGE["filters"][chat_id][trigger_word]
        save_data()
        await message.reply(f"🗑️ Фильтр **'{trigger_word}'** удален!", parse_mode="Markdown")
    else:
        await message.reply(f"❓ Фильтр **'{trigger_word}'** не найден.")

@dp.message(Command("filters"))
async def list_filters(message: types.Message):
    chat_id = message.chat.id
    filters = STORAGE["filters"].get(chat_id, {})
    if not filters:
        await message.reply("В этом чате пока нет активных фильтров.")
        return

    words = ", ".join([f"`{w}`" for w in filters.keys()])
    await message.reply(f"📜 **Активные фильтры этого чата:**\n{words}", parse_mode="Markdown")

# ----------------- 3. ПРИВЕТСТВИЯ (WELCOME) -----------------

@dp.message(Command("setwelcome"))
async def set_welcome(message: types.Message):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав для настройки приветствий!")
        return

    if not message.reply_to_message:
        await message.reply("⚠️ Ответьте этой командой на сообщение (текст/фото/гифка/стикер), которое будет приветствием!\n\n💡 *Совет:* Вы можете использовать `{name}` в тексте сообщения, чтобы бот обращался к пользователю по имени.", parse_mode="Markdown")
        return

    chat_id = message.chat.id
    reply = message.reply_to_message

    if reply.animation:
        STORAGE["welcomes"][chat_id] = {"type": "animation", "file_id": reply.animation.file_id, "caption": reply.caption}
    elif reply.sticker:
        STORAGE["welcomes"][chat_id] = {"type": "sticker", "file_id": reply.sticker.file_id}
    elif reply.photo:
        STORAGE["welcomes"][chat_id] = {"type": "photo", "file_id": reply.photo[-1].file_id, "caption": reply.caption}
    elif reply.text:
        STORAGE["welcomes"][chat_id] = {"type": "text", "text": reply.text}
    else:
        await message.reply("❌ Этот тип сообщений не поддерживается для приветствия.")
        return

    save_data()
    await message.reply("✅ Приветствие для новых участников успешно установлено!", parse_mode="Markdown")

@dp.message(Command("clearwelcome"))
async def clear_welcome(message: types.Message):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав администратора!")
        return

    chat_id = message.chat.id
    if chat_id in STORAGE["welcomes"]:
        del STORAGE["welcomes"][chat_id]
        save_data()
        await message.reply("🗑️ Приветствие удалено.")
    else:
        await message.reply("❓ В этом чате не было установлено приветствие.")

@dp.message(F.new_chat_members)
async def greet_new_members(message: types.Message):
    chat_id = message.chat.id
    welcome_data = STORAGE["welcomes"].get(chat_id)
    if not welcome_data:
        return

    for member in message.new_chat_members:
        name = member.first_name
        content_type = welcome_data["type"]

        if content_type == "text":
            text = welcome_data["text"].format(name=name, first_name=name) if welcome_data.get("text") else f"Привет, {name}!"
            await message.reply(text)
        elif content_type == "animation":
            caption = welcome_data.get("caption", "").format(name=name, first_name=name) if welcome_data.get("caption") else None
            await message.reply_animation(animation=welcome_data["file_id"], caption=caption)
        elif content_type == "photo":
            caption = welcome_data.get("caption", "").format(name=name, first_name=name) if welcome_data.get("caption") else None
            await message.reply_photo(photo=welcome_data["file_id"], caption=caption)
        elif content_type == "sticker":
            await message.reply_sticker(sticker=welcome_data["file_id"])

# ----------------- 4. МОДЕРАЦИЯ (БАНЫ, МУТЫ, ВАРНЫ) -----------------

@dp.message(Command("ban"))
async def ban_user(message: types.Message, command: CommandObject):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав модератора!")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("⚠️ Ответьте на сообщение нарушителя или укажите его ID!\nПример: `/ban 123456789 Спам`", parse_mode="Markdown")
        return

    reason = " ".join(command.args.split()[1:]) if command.args and len(command.args.split()) > 1 else "Причина не указана"

    try:
        await bot.ban_chat_member(message.chat.id, target_id)
        chat_id = message.chat.id
        if chat_id not in STORAGE["bans"]:
            STORAGE["bans"][chat_id] = []
        if target_id not in STORAGE["bans"][chat_id]:
            STORAGE["bans"][chat_id].append(target_id)
            save_data()

        await message.reply(f"🚫 Пользователь **{target_name}** забанен!\n💬 Причина: {reason}", parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"❌ Не удалось забанить пользователя: {e}")

@dp.message(Command("unban"))
async def unban_user(message: types.Message, command: CommandObject):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав!")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("⚠️ Ответьте на сообщение или укажите ID забаненного пользователя!", parse_mode="Markdown")
        return

    try:
        await bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
        chat_id = message.chat.id
        if chat_id in STORAGE["bans"] and target_id in STORAGE["bans"][chat_id]:
            STORAGE["bans"][chat_id].remove(target_id)
            save_data()

        await message.reply(f"✅ Пользователь **{target_name}** разбанен!", parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"❌ Ошибка при разбане: {e}")

@dp.message(Command("mute"))
async def mute_user(message: types.Message, command: CommandObject):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав модератора!")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("⚠️ Ответьте на сообщение пользователя или укажите его ID!\nПримеры: `/mute 10m`, `/mute 2h`, `/mute 1d`", parse_mode="Markdown")
        return

    time_arg = command.args.split()[1] if command.args and len(command.args.split()) > 1 else "1h"
    duration = parse_time(time_arg) or timedelta(hours=1)
    until_date = datetime.now() + duration

    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        await message.reply(f"🔇 Пользователь **{target_name}** переведен в режим чтения на {time_arg}!", parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"❌ Не удалось замутить пользователя: {e}")

@dp.message(Command("unmute"))
async def unmute_user(message: types.Message, command: CommandObject):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав!")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("⚠️ Ответьте на сообщение замученного пользователя!", parse_mode="Markdown")
        return

    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await message.reply(f"🔊 Пользователю **{target_name}** возвращен доступ к чату!", parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"❌ Ошибка при снятии мута: {e}")

@dp.message(Command("warn"))
async def warn_user(message: types.Message, command: CommandObject):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав!")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("⚠️ Ответьте на сообщение нарушителя для выдачи варна!", parse_mode="Markdown")
        return

    chat_id = message.chat.id
    if chat_id not in STORAGE["warns"]:
        STORAGE["warns"][chat_id] = {}

    current_warns = STORAGE["warns"][chat_id].get(target_id, 0) + 1
    STORAGE["warns"][chat_id][target_id] = current_warns
    save_data()

    if current_warns >= 3:
        # Автоматический мут при достижении 3 варнов
        STORAGE["warns"][chat_id][target_id] = 0
        save_data()
        try:
            until_date = datetime.now() + timedelta(days=1)
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            await message.reply(f"⚠️ Пользователь **{target_name}** получил 3/3 предупреждений и замучен на 24 часа!", parse_mode="Markdown")
        except Exception as e:
            await message.reply(f"⚠️ 3/3 варнов достигнуто, но не удалось замутить: {e}")
    else:
        await message.reply(f"⚠️ Пользователю **{target_name}** выдан варн! ({current_warns}/3)", parse_mode="Markdown")

@dp.message(Command("resetwarns"))
async def reset_warns(message: types.Message, command: CommandObject):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав!")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("⚠️ Ответьте на сообщение пользователя!", parse_mode="Markdown")
        return

    chat_id = message.chat.id
    if chat_id in STORAGE["warns"] and target_id in STORAGE["warns"][chat_id]:
        STORAGE["warns"][chat_id][target_id] = 0
        save_data()

    await message.reply(f"✅ Предупреждения пользователя **{target_name}** сброшены!", parse_mode="Markdown")

# ----------------- 5. ПРОВЕРКА ВХОДЯЩИХ СООБЩЕНИЙ (ФИЛЬТРЫ) -----------------

@dp.message(F.text)
async def check_filters(message: types.Message):
    chat_id = message.chat.id
    filters = STORAGE["filters"].get(chat_id)
    if not filters:
        return

    text_lower = message.text.lower()
    words_in_message = text_lower.split()

    for trigger_word, content in filters.items():
        if " " in trigger_word:
            match_found = trigger_word in text_lower
        else:
            match_found = trigger_word in words_in_message

        if match_found:
            content_type = content["type"]

            if content_type == "text":
                await message.reply(content["text"])
            elif content_type == "animation":
                await message.reply_animation(animation=content["file_id"], caption=content.get("caption"))
            elif content_type == "sticker":
                await message.reply_sticker(sticker=content["file_id"])
            elif content_type == "photo":
                await message.reply_photo(photo=content["file_id"], caption=content.get("caption"))
            elif content_type == "video":
                await message.reply_video(video=content["file_id"], caption=content.get("caption"))
            elif content_type == "voice":
                await message.reply_voice(voice=content["file_id"])
            break

async def main():
    print("Бот-модератор запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())