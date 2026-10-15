import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

# =========================================================
# 📝 БЕЛЫЙ СПИСОК (Вайт-лист модераторов)
# Замени цифры ниже на свой ID и ID твоих модераторов через запятую.
# =========================================================
WHITELIST = [123456789, 987654321] 


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот для мута и размута с вайт-листом. 🛡️\nИспользовать команды могут только люди из белого списка.")

# 1. КОМАНДА ДЛЯ МУТА (/mute)
@dp.message(Command("mute"))
async def cmd_mute(message: types.Message):
    # Проверяем, есть ли пользователь в вайт-листе
    if message.from_user.id not in WHITELIST:
        await message.reply("У тебя нет прав модератора для использования этой команды! 🛑")
        return

    # Проверяем, ответил ли модератор на сообщение
    if not message.reply_to_message:
        await message.reply("Эту команду нужно писать в ответе (Reply) на сообщение нарушителя!")
        return

    user_id = message.reply_to_message.from_user.id
    
    # Запрещаем отправку сообщений
    permissions = types.ChatPermissions(can_send_messages=False)
    
    try:
        await bot.restrict_chat_member(chat_id=message.chat.id, user_id=user_id, permissions=permissions)
        await message.answer(f"Модератор выдал мут пользователю @{message.reply_to_message.from_user.username} 🤐")
    except Exception as e:
        await message.reply("Не удалось выдать мут. Убедись, что я добавлен в админы группы с правом блокировки!")

# 2. КОМАНДА ДЛЯ РАЗМУТА (/unmute)
@dp.message(Command("unmute"))
async def cmd_unmute(message: types.Message):
    # Проверяем вайт-лист
    if message.from_user.id not in WHITELIST:
        await message.reply("У тебя нет прав модератора для использования этой команды! 🛑")
        return

    if not message.reply_to_message:
        await message.reply("Эту команду нужно писать в ответе (Reply) на сообщение пользователя!")
        return

    user_id = message.reply_to_message.from_user.id
    
    # Возвращаем все права общения
    permissions = types.ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True
    )
    
    try:
        await bot.restrict_chat_member(chat_id=message.chat.id, user_id=user_id, permissions=permissions)
        await message.answer(f"Модератор размутил пользователя @{message.reply_to_message.from_user.username} 🎉")
    except Exception as e:
        await message.reply("Не удалось размутить. Проверь мои права администратора!")

async def main():
    print("Бот для мута/размута с вайт-листом успешно запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
