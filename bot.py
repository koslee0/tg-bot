import asyncio
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Словарь для хранения фильтров: { "слово": {"type": "gif", "file_id": "...", "text": "..."} }
FILTERS = {}


# 1. Создание фильтра по команде /filter <слово>
@dp.message(Command("filter"))
async def add_filter(message: types.Message, command: CommandObject):
    # Проверка: команда должна быть отправлена в ответ на сообщение
    if not message.reply_to_message:
        await message.reply("Ответьте этой командой на сообщение, которое хотите привязать")
        return

    # Проверка: передал ли пользователь ключевое слово
    if not command.args:
        await message.reply("Укажите ключевое слово после команды", parse_mode="Markdown")
        return

    trigger_word = command.args.strip().lower()
    reply = message.reply_to_message

    # Определяем тип содержимого и сохраняем его
    if reply.animation:  # GIF
        FILTERS[trigger_word] = {"type": "animation", "file_id": reply.animation.file_id, "caption": reply.caption}
    elif reply.sticker:  # Стикер
        FILTERS[trigger_word] = {"type": "sticker", "file_id": reply.sticker.file_id}
    elif reply.photo:    # Картинка
        FILTERS[trigger_word] = {"type": "photo", "file_id": reply.photo[-1].file_id, "caption": reply.caption}
    elif reply.video:    # Видео
        FILTERS[trigger_word] = {"type": "video", "file_id": reply.video.file_id, "caption": reply.caption}
    elif reply.voice:    # Голосовое сообщение
        FILTERS[trigger_word] = {"type": "voice", "file_id": reply.voice.file_id}
    elif reply.text:     # Обычный текст
        FILTERS[trigger_word] = {"type": "text", "text": reply.text}
    else:
        await message.reply("❌ Этот тип сообщений пока не поддерживается.")
        return

    await message.reply(f"Фильтр на слово **'{trigger_word}'** успешно сохранен", parse_mode="Markdown")


# 2. Удаление фильтра по команде /stop <слово>
@dp.message(Command("stop"))
async def remove_filter(message: types.Message, command: CommandObject):
    if not command.args:
        await message.reply("Укажите слово, фильтр для которого нужно удалить", parse_mode="Markdown")
        return

    trigger_word = command.args.strip().lower()

    if trigger_word in FILTERS:
        del FILTERS[trigger_word]
        await message.reply(f"🗑Фильтр **'{trigger_word}'** удален", parse_mode="Markdown")
    else:
        await message.reply(f"Фильтр **'{trigger_word}'** не найден")


# 3. Список всех фильтров в чате
@dp.message(Command("filters"))
async def list_filters(message: types.Message):
    if not FILTERS:
        await message.reply("Список фильтров пуст.")
        return

    words = ", ".join([f"`{w}`" for w in FILTERS.keys()])
    await message.reply(f"📜 **Активные фильтры:**\n{words}", parse_mode="Markdown")


# 4. Проверка входящих сообщений на совпадение с фильтрами
@dp.message(F.text)
async def check_filters(message: types.Message):
    text = message.text.lower()

    # Ищем, есть ли ключевое слово в тексте сообщения
    for trigger_word, content in FILTERS.items():
        if trigger_word in text:
            content_type = content["type"]

            # Отправляем нужный тип контента
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
            
            # Прерываем цикл, чтобы не срабатывало сразу несколько фильтров
            break


async def main():
    print("Бот запущен с поддержкой фильтров!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())