import asyncio
import os
import json
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Имя файла для сохранения фильтров
DB_FILE = "filters.json"

# Загрузка фильтров из файла при запуске бота
def load_filters():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # JSON сохраняет ключи словарей как строки, приводим chat_id обратно к int
                return {int(chat_id): filters for chat_id, filters in data.items()}
        except Exception as e:
            print(f"Ошибка при загрузке фильтров: {e}")
    return {}

# Сохранение фильтров в файл
def save_filters():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(CHAT_FILTERS, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Ошибка при сохранении фильтров: {e}")

# Словарь фильтров по чатам (загружается из файла при старте)
CHAT_FILTERS = load_filters()

# Функция для проверки прав администратора
async def is_admin(message: types.Message) -> bool:
    if message.chat.type == "private":
        return True
    
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in ["creator"]


# 1. Создание фильтра (только для админов)
@dp.message(Command("filter"))
async def add_filter(message: types.Message, command: CommandObject):
    if not await is_admin(message):
        await message.reply("❌ У вас нет прав администратора для создания фильтров!")
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

    if chat_id not in CHAT_FILTERS:
        CHAT_FILTERS[chat_id] = {}

    # Сохраняем контент в словарь конкретного чата
    if reply.animation:
        CHAT_FILTERS[chat_id][trigger_word] = {"type": "animation", "file_id": reply.animation.file_id, "caption": reply.caption}
    elif reply.sticker:
        CHAT_FILTERS[chat_id][trigger_word] = {"type": "sticker", "file_id": reply.sticker.file_id}
    elif reply.photo:
        CHAT_FILTERS[chat_id][trigger_word] = {"type": "photo", "file_id": reply.photo[-1].file_id, "caption": reply.caption}
    elif reply.video:
        CHAT_FILTERS[chat_id][trigger_word] = {"type": "video", "file_id": reply.video.file_id, "caption": reply.caption}
    elif reply.voice:
        CHAT_FILTERS[chat_id][trigger_word] = {"type": "voice", "file_id": reply.voice.file_id}
    elif reply.text:
        CHAT_FILTERS[chat_id][trigger_word] = {"type": "text", "text": reply.text}
    else:
        await message.reply("❌ Этот тип сообщений пока не поддерживается.")
        return

    # Сохраняем в файл на диске
    save_filters()

    await message.reply(f"✅ Фильтр на слово **'{trigger_word}'** успешно сохранен!", parse_mode="Markdown")


# 2. Удаление фильтра (только для админов)
@dp.message(Command("stop"))
async def remove_filter(message: types.Message, command: CommandObject):
    if not await is_admin(message):
        await message.reply("❌ У вас нет прав администратора для удаления фильтров!")
        return

    if not command.args:
        await message.reply("⚠️ Укажите слово, фильтр для которого нужно удалить.\nПример: `/stop привет`", parse_mode="Markdown")
        return

    chat_id = message.chat.id
    trigger_word = command.args.strip().lower()

    if chat_id in CHAT_FILTERS and trigger_word in CHAT_FILTERS[chat_id]:
        del CHAT_FILTERS[chat_id][trigger_word]
        
        if not CHAT_FILTERS[chat_id]:
            del CHAT_FILTERS[chat_id]

        # Обновляем файл на диске
        save_filters()

        await message.reply(f"🗑️ Фильтр **'{trigger_word}'** удален!", parse_mode="Markdown")
    else:
        await message.reply(f"❓ Фильтр **'{trigger_word}'** не найден в этом чате.")


# 3. Список всех фильтров текущего чата (доступен всем)
@dp.message(Command("filters"))
async def list_filters(message: types.Message):
    chat_id = message.chat.id
    
    if chat_id not in CHAT_FILTERS or not CHAT_FILTERS[chat_id]:
        await message.reply("В этом чате пока нет активных фильтров.")
        return

    words = ", ".join([f"`{w}`" for w in CHAT_FILTERS[chat_id].keys()])
    await message.reply(f"📜 **Активные фильтры этого чата:**\n{words}", parse_mode="Markdown")


# 4. Проверка входящих сообщений (точное совпадение по словам)
@dp.message(F.text)
async def check_filters(message: types.Message):
    chat_id = message.chat.id
    
    if chat_id not in CHAT_FILTERS or not CHAT_FILTERS[chat_id]:
        return

    text_lower = message.text.lower()
    words_in_message = text_lower.split()

    for trigger_word, content in CHAT_FILTERS[chat_id].items():
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
    print("Бот-модератор запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```[cite: 1]