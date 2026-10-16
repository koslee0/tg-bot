import asyncio
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Словарь для хранения фильтров
FILTERS = {}

# Функция для проверки, является ли пользователь администратором
async def is_admin(message: types.Message) -> bool:
    # В личных сообщениях проверка админства не требуется
    if message.chat.type == "private":
        return True
    
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in ["creator"]


# 1. Создание фильтра (ТОЛЬКО для админов)
@dp.message(Command("filter"))
async def add_filter(message: types.Message, command: CommandObject):
    if not await is_admin(message):
        await message.reply("❌ У вас нет прав администратора для создания фильтров!")
        return

    if not message.reply_to_message:
        await message.reply("⚠️ Ответьте этой командой на сообщение/гифку/стикер/картинку, которую хотите привязать!")
        return

    if not command.args:
        await message.reply("⚠️ Укажите ключевое слово после команды.\nПример: `/filter привет`", parse_mode="Markdown")
        return

    trigger_word = command.args.strip().lower()
    reply = message.reply_to_message

    # Сохраняем контент в словарь
    if reply.animation:
        FILTERS[trigger_word] = {"type": "animation", "file_id": reply.animation.file_id, "caption": reply.caption}
    elif reply.sticker:
        FILTERS[trigger_word] = {"type": "sticker", "file_id": reply.sticker.file_id}
    elif reply.photo:
        FILTERS[trigger_word] = {"type": "photo", "file_id": reply.photo[-1].file_id, "caption": reply.caption}
    elif reply.video:
        FILTERS[trigger_word] = {"type": "video", "file_id": reply.video.file_id, "caption": reply.caption}
    elif reply.voice:
        FILTERS[trigger_word] = {"type": "voice", "file_id": reply.voice.file_id}
    elif reply.text:
        FILTERS[trigger_word] = {"type": "text", "text": reply.text}
    else:
        await message.reply("❌ Этот тип сообщений пока не поддерживается.")
        return

    await message.reply(f"✅ Фильтр на слово **'{trigger_word}'** успешно сохранен!", parse_mode="Markdown")


# 2. Удаление фильтра (ТОЛЬКО для админов)
@dp.message(Command("stop"))
async def remove_filter(message: types.Message, command: CommandObject):
    if not await is_admin(message):
        await message.reply("❌ У вас нет прав администратора для удаления фильтров!")
        return

    if not command.args:
        await message.reply("⚠️ Укажите слово, фильтр для которого нужно удалить.\nПример: `/stop привет`", parse_mode="Markdown")
        return

    trigger_word = command.args.strip().lower()

    if trigger_word in FILTERS:
        del FILTERS[trigger_word]
        await message.reply(f"🗑️ Фильтр **'{trigger_word}'** удален!", parse_mode="Markdown")
    else:
        await message.reply(f"❓ Фильтр **'{trigger_word}'** не найден.")


# 3. Список всех фильтров (доступен всем участникам)
@dp.message(Command("filters"))
async def list_filters(message: types.Message):
    if not FILTERS:
        await message.reply("Список фильтров пуст.")
        return

    words = ", ".join([f"`{w}`" for w in FILTERS.keys()])
    await message.reply(f"📜 **Активные фильтры в чате:**\n{words}", parse_mode="Markdown")


# 4. Проверка входящих сообщений (точное совпадение по словам)
@dp.message(F.text)
async def check_filters(message: types.Message):
    text_lower = message.text.lower()
    
    # Разбиваем текст сообщения на отдельные слова по пробелам
    words_in_message = text_lower.split()

    for trigger_word, content in FILTERS.items():
        # Если триггер состоит из нескольких слов, ищем фразу целиком,
        # если из одного — проверяем точное совпадение со словом из сообщения
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
    print("Бот-модератор запущен и готов к работе...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
 