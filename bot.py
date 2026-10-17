import asyncio
import os
import json
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject, ChatMemberUpdatedFilter, JOIN_TRANSITION
from aiogram.types import ChatPermissions, ChatMemberUpdated

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Путь к хранилищу Volume
DATA_DIR = "/app/data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "storage.json")

def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "filters": {int(cid): f for cid, f in data.get("filters", {}).items()},
                    "bot_admins": {int(cid): a for cid, a in data.get("bot_admins", {}).items()},
                    "welcomes": {int(cid): w for cid, w in data.get("welcomes", {}).items()},
                    "warns": {int(cid): {int(uid): cnt for uid, cnt in u_warns.items() if cnt > 0} for cid, u_warns in data.get("warns", {}).items()},
                    "bans": {int(cid): list(set(b)) for cid, b in data.get("bans", {}).items() if b}
                }
        except Exception as e:
            print(f"Ошибка при загрузке базы данных: {e}")
    return {"filters": {}, "bot_admins": {}, "welcomes": {}, "warns": {}, "bans": {}}

def save_data():
    try:
        clean_storage = {
            "filters": {cid: f for cid, f in STORAGE["filters"].items() if f},
            "bot_admins": {cid: a for cid, a in STORAGE["bot_admins"].items() if a},
            "welcomes": {cid: w for cid, w in STORAGE["welcomes"].items() if w},
            "warns": {cid: {uid: cnt for uid, cnt in u_warns.items() if cnt > 0} for cid, u_warns in STORAGE["warns"].items() if u_warns},
            "bans": {cid: list(set(b)) for cid, b in STORAGE["bans"].items() if b}
        }
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(clean_storage, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Ошибка при сохранении базы данных: {e}")

STORAGE = load_data()

FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_media_messages=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_send_polls=True,
    can_change_info=True,
    can_invite_users=True,
    can_pin_messages=True
)

async def is_bot_admin(message: types.Message) -> bool:
    if message.chat.type == "private":
        return True
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status == "creator":
            return True
    except Exception:
        pass

    allowed_admins = STORAGE["bot_admins"].get(chat_id, [])
    if user_id in allowed_admins:
        return True

    return False

def parse_time(time_str: str) -> timedelta | None:
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
    if message.reply_to_message:
        return message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name
    
    if command and command.args:
        args = command.args.split()
        target = args[0]
        if target.isdigit():
            return int(target), f"ID {target}"
    return None, None

# ----------------- 1. ВАЙТЛИСТ АДМИНОВ -----------------

@dp.message(Command("botadmin"))
async def add_bot_admin(message: types.Message, command: CommandObject):
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status != "creator" and message.chat.type != "private":
            await message.reply("❌ Только создатель (владелец) группы может выдавать доступ к администрированию бота!")
            return
    except Exception:
        if message.chat.type != "private":
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
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status != "creator" and message.chat.type != "private":
            await message.reply("❌ Только создатель группы может забирать доступ к боту!")
            return
    except Exception:
        if message.chat.type != "private":
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

async def send_welcome_msg(chat_id: int, user_name: str, target_message: types.Message = None):
    welcome_data = STORAGE["welcomes"].get(chat_id)
    if not welcome_data:
        return False

    content_type = welcome_data["type"]

    try:
        if content_type == "text":
            text = welcome_data["text"].format(name=user_name, first_name=user_name) if welcome_data.get("text") else f"Привет, {user_name}!"
            if target_message:
                await target_message.reply(text)
            else:
                await bot.send_message(chat_id, text)
        elif content_type == "animation":
            caption = welcome_data.get("caption", "").format(name=user_name, first_name=user_name) if welcome_data.get("caption") else None
            if target_message:
                await target_message.reply_animation(animation=welcome_data["file_id"], caption=caption)
            else:
                await bot.send_animation(chat_id, animation=welcome_data["file_id"], caption=caption)
        elif content_type == "photo":
            caption = welcome_data.get("caption", "").format(name=user_name, first_name=user_name) if welcome_data.get("caption") else None
            if target_message:
                await target_message.reply_photo(photo=welcome_data["file_id"], caption=caption)
            else:
                await bot.send_photo(chat_id, photo=welcome_data["file_id"], caption=caption)
        elif content_type == "sticker":
            if target_message:
                await target_message.reply_sticker(sticker=welcome_data["file_id"])
            else:
                await bot.send_sticker(chat_id, sticker=welcome_data["file_id"])
    except Exception as e:
        print(f"Ошибка при отправке приветствия: {e}")
    return True

@dp.message(Command("setwelcome"))
async def set_welcome(message: types.Message):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав для настройки приветствий!")
        return

    if not message.reply_to_message:
        await message.reply("⚠️ Ответьте этой командой на сообщение (текст/фото/гифка/стикер), которое будет приветствием!\n\n💡 *Совет:* Вы можете использовать `{name}` в тексте сообщения.", parse_mode="Markdown")
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

@dp.message(Command("welcome"))
async def show_welcome(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in STORAGE["welcomes"]:
        await message.reply("ℹ️ В этом чате еще не установлено приветствие.\nНастроить можно командой `/setwelcome` (в ответ на сообщение).", parse_mode="Markdown")
        return

    await message.reply("👋 **Текущее приветствие для этого чата:**", parse_mode="Markdown")
    await send_welcome_msg(chat_id, message.from_user.first_name, target_message=message)

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
async def greet_new_members_message(message: types.Message):
    chat_id = message.chat.id
    for member in message.new_chat_members:
        if member.is_bot:
            continue
        await send_welcome_msg(chat_id, member.first_name, target_message=message)

@dp.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def greet_new_members_event(event: ChatMemberUpdated):
    user = event.new_chat_member.user
    if user.is_bot:
        return
    await send_welcome_msg(event.chat.id, user.first_name)

# ----------------- 4. МОДЕРАЦИЯ (БАНЫ, КИКИ, МУТЫ, ВАРНЫ) -----------------

@dp.message(Command("ban"))
async def ban_user(message: types.Message, command: CommandObject):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав модератора!")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("⚠️ Ответьте на сообщение нарушителя или укажите его ID!\nПример: `/ban 123456789 Спам`", parse_mode="Markdown")
        return

    args_list = command.args.split() if command.args else []
    reason = " ".join(args_list[1:]) if len(args_list) > 1 and not message.reply_to_message else " ".join(args_list) if len(args_list) > 0 and message.reply_to_message else None

    try:
        await bot.ban_chat_member(message.chat.id, target_id)
        chat_id = message.chat.id
        if chat_id not in STORAGE["bans"]:
            STORAGE["bans"][chat_id] = []
        if target_id not in STORAGE["bans"][chat_id]:
            STORAGE["bans"][chat_id].append(target_id)
            save_data()

        msg_text = f"🚫 Пользователь **{target_name}** забанен!"
        if reason:
            msg_text += f"\n💬 Причина: {reason}"
        await message.reply(msg_text, parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"❌ Не удалось забанить пользователя: {e}")

@dp.message(Command("kick"))
async def kick_user(message: types.Message, command: CommandObject):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав модератора!")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("⚠️ Ответьте на сообщение нарушителя или укажите его ID!\nПример: `/kick 123456789 Оффтоп`", parse_mode="Markdown")
        return

    args_list = command.args.split() if command.args else []
    reason = " ".join(args_list[1:]) if len(args_list) > 1 and not message.reply_to_message else " ".join(args_list) if len(args_list) > 0 and message.reply_to_message else None

    try:
        await bot.ban_chat_member(message.chat.id, target_id)
        await bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)

        msg_text = f"👢 Пользователь **{target_name}** изгнан (кикнут) из чата!"
        if reason:
            msg_text += f"\n💬 Причина: {reason}"
        await message.reply(msg_text, parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"❌ Не удалось кикнуть пользователя: {e}")

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
            if not STORAGE["bans"][chat_id]:
                del STORAGE["bans"][chat_id]
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

    args_list = command.args.split() if command.args else []
    time_arg = "1h"
    reason = None

    if message.reply_to_message:
        if len(args_list) >= 1:
            parsed = parse_time(args_list[0])
            if parsed:
                time_arg = args_list[0]
                reason = " ".join(args_list[1:]) if len(args_list) > 1 else None
            else:
                reason = " ".join(args_list)
    else:
        if len(args_list) >= 2:
            parsed = parse_time(args_list[1])
            if parsed:
                time_arg = args_list[1]
                reason = " ".join(args_list[2:]) if len(args_list) > 2 else None
            else:
                reason = " ".join(args_list[1:])

    duration = parse_time(time_arg) or timedelta(hours=1)
    until_date = datetime.now() + duration

    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )

        msg_text = f"🔇 Пользователь **{target_name}** переведен в режим чтения на {time_arg}!"
        if reason:
            msg_text += f"\n💬 Причина: {reason}"
        await message.reply(msg_text, parse_mode="Markdown")
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
            permissions=FULL_PERMISSIONS
        )
        await message.reply(f"🔊 Пользователю **{target_name}** возвращен полный доступ к чату!", parse_mode="Markdown")
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

    args_list = command.args.split() if command.args else []
    reason = " ".join(args_list[1:]) if len(args_list) > 1 and not message.reply_to_message else " ".join(args_list) if len(args_list) > 0 and message.reply_to_message else None

    chat_id = message.chat.id
    if chat_id not in STORAGE["warns"]:
        STORAGE["warns"][chat_id] = {}

    current_warns = STORAGE["warns"][chat_id].get(target_id, 0) + 1
    STORAGE["warns"][chat_id][target_id] = current_warns
    save_data()

    if current_warns >= 3:
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
            msg_text = f"⚠️ Пользователь **{target_name}** получил 3/3 предупреждений и замучен на 24 часа!"
            if reason:
                msg_text += f"\n💬 Причина: {reason}"
            await message.reply(msg_text, parse_mode="Markdown")
        except Exception as e:
            await message.reply(f"⚠️ 3/3 варнов достигнуто, но не удалось замутить: {e}")
    else:
        msg_text = f"⚠️ Пользователю **{target_name}** выдан варн! ({current_warns}/3)"
        if reason:
            msg_text += f"\n💬 Причина: {reason}"
        await message.reply(msg_text, parse_mode="Markdown")

@dp.message(Command("unwarn"))
async def unwarn_user(message: types.Message, command: CommandObject):
    if not await is_bot_admin(message):
        await message.reply("❌ У вас нет прав!")
        return

    target_id, target_name = await extract_target_user(message, command)
    if not target_id:
        await message.reply("⚠️ Ответьте на сообщение пользователя или укажите его ID для снятия варна!", parse_mode="Markdown")
        return

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
        
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_id,
                permissions=FULL_PERMISSIONS
            )
        except Exception:
            pass

        await message.reply(f"✅ С пользователя **{target_name}** снято одно предупреждение! Текущий счет: **{new_warns}/3**.", parse_mode="Markdown")
    else:
        await message.reply(f"ℹ️ У пользователя **{target_name}** нет активных предупреждений.", parse_mode="Markdown")

@dp.message(Command("warns"))
async def check_warns(message: types.Message, command: CommandObject):
    chat_id = message.chat.id
    target_id, target_name = await extract_target_user(message, command)

    if target_id and target_id != message.from_user.id:
        if not await is_bot_admin(message):
            await message.reply("❌ Вы можете просматривать только свои варны!")
            return
    else:
        target_id = message.from_user.id
        target_name = message.from_user.first_name

    warns_count = STORAGE["warns"].get(chat_id, {}).get(target_id, 0)
    
    if target_id == message.from_user.id:
        await message.reply(f"📊 У вас **{warns_count}/3** предупреждений в этом чате.", parse_mode="Markdown")
    else:
        await message.reply(f"📊 У пользователя **{target_name}** количество предупреждений: **{warns_count}/3**.", parse_mode="Markdown")

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
        del STORAGE["warns"][chat_id][target_id]
        if not STORAGE["warns"][chat_id]:
            del STORAGE["warns"][chat_id]
        save_data()

    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            permissions=FULL_PERMISSIONS
        )
    except Exception:
        pass

    await message.reply(f"✅ Предупреждения пользователя **{target_name}** сброшены!", parse_mode="Markdown")

# ----------------- 5. ФИЛЬТРЫ ВХОДЯЩИХ СООБЩЕНИЙ -----------------

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
                await message.reply_voice(video=content["file_id"])
            break

async def main():
    print("Бот-модератор успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())