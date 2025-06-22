import os
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import openai
import asyncio

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

# Конфигурация
CONFIG = {
    "TELEGRAM_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
    "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY"),
    "OPENROUTER_API_BASE": "https://openrouter.ai/api/v1",
    "REQUEST_TIMEOUT": 30,  # Таймаут запроса в секундах
    "RATE_LIMIT": 3,  # Максимум запросов в минуту
}

# Настраиваем OpenAI для работы с OpenRouter
openai.api_key = CONFIG["OPENROUTER_API_KEY"]
openai.api_base = CONFIG["OPENROUTER_API_BASE"]

# Для ограничения частоты запросов
user_requests = defaultdict(list)

def is_rate_limited(user_id: int) -> bool:
    """Проверяем, не превысил ли пользователь лимит запросов"""
    now = datetime.now()
    user_requests[user_id] = [
        req for req in user_requests[user_id]
        if req > now - timedelta(minutes=1)
    ]
    if len(user_requests[user_id]) >= CONFIG["RATE_LIMIT"]:
        return True
    user_requests[user_id].append(now)
    return False

async def get_llm_response(user_id: int, message_text: str) -> str:
    """Получаем ответ от языковой модели с обработкой ошибок"""
    try:
        if is_rate_limited(user_id):
            return "⚠️ Слишком много запросов. Пожалуйста, подождите минуту."
            
        response = await asyncio.wait_for(
            openai.ChatCompletion.acreate(
                model="mistralai/mistral-small-3.2-24b-instruct:free",
                messages=[{"role": "user", "content": message_text}],
                timeout=CONFIG["REQUEST_TIMEOUT"]
            ),
            timeout=CONFIG["REQUEST_TIMEOUT"]
        )
        return response.choices[0].message['content']
    except asyncio.TimeoutError:
        logger.warning(f"Timeout for user {user_id}")
        return "⌛ Время ожидания ответа истекло. Попробуйте позже."
    except Exception as e:
        logger.error(f"Error for user {user_id}: {str(e)}")
        return "⚠️ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."

# Инициализируем бота и диспетчер
bot = Bot(token=CONFIG["TELEGRAM_TOKEN"])
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

@dp.message(Command("start", "reset"))
async def handle_start_reset(message: types.Message) -> None:
    """Обработка команд /start и /reset"""
    welcome_text = (
        "Привет! Я ваш бот. "
        "История диалога была сброшена. "
        "Как я могу помочь вам сегодня?"
    )
    await message.reply(welcome_text)

@dp.message(Command("help"))
async def handle_help(message: types.Message) -> None:
    """Обработка команды /help"""
    help_text = (
        "Справка:\n"
        "• Просто отправьте мне сообщение, и я постараюсь ответить!\n"
        "• Если я не отвечаю, возможно, сервер перегружен - попробуйте позже.\n"
        "• Ограничение: не более 3 запросов в минуту."
    )
    await message.reply(help_text)

@dp.message()
async def process_message(message: types.Message) -> None:
    """Обработка всех входящих сообщений"""
    try:
        # Отправляем уведомление о начале обработки
        processing_msg = await message.reply("🔄 Обрабатываю запрос...")
        
        response = await get_llm_response(message.from_user.id, message.text)
        
        # Удаляем сообщение о обработке
        await bot.delete_message(
            chat_id=processing_msg.chat.id,
            message_id=processing_msg.message_id
        )
        
        await message.answer(response)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        await message.answer("⚠️ Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже.")

if __name__ == "__main__":
    logger.info("Starting bot...")
    try:
        dp.run_polling(bot)
    except Exception as e:
        logger.critical(f"Bot crashed: {str(e)}")

