# delete_messages.py
import os
import asyncio
import logging
import datetime
import yaml
from telegram import Bot
from telegram.error import TelegramError

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Настройки ---
MESSAGE_IDS_FILE = "message_ids.yml" # Файл для хранения ID сообщений
DELETE_AFTER_HOURS = 3              # Через сколько часов удалять сообщения

async def main():
    """
    Основная функция для удаления старых сообщений.
    """
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    target_chat_id = os.getenv("TARGET_CHAT_ID")

    if not telegram_bot_token or not target_chat_id:
        logger.error("ОШИБКА: Отсутствуют необходимые переменные окружения для удаления сообщений. "
                     "Убедитесь, что TELEGRAM_BOT_TOKEN и TARGET_CHAT_ID установлены.")
        return

    bot = Bot(token=telegram_bot_token)

    # Загружаем сохраненные ID сообщений
    messages_to_delete = []
    if os.path.exists(MESSAGE_IDS_FILE):
        with open(MESSAGE_IDS_FILE, 'r') as f:
            try:
                data = yaml.safe_load(f)
                if isinstance(data, list):
                    messages_to_delete = data
                else:
                    logger.warning(f"Файл {MESSAGE_IDS_FILE} содержит некорректный формат данных. Ожидался список.")
            except yaml.YAMLError as e:
                logger.error(f"Ошибка при парсинге YAML файла {MESSAGE_IDS_FILE}: {e}")
    else:
        logger.info(f"Файл {MESSAGE_IDS_FILE} не найден. Пока нет сообщений для удаления.")
        return # Если файла нет, значит, пока нечего удалять

    current_time = datetime.datetime.now(datetime.timezone.utc)
    updated_messages_list = []
    deleted_count = 0

    for msg_info in messages_to_delete:
        try:
            message_id = msg_info.get('message_id')
            sent_at_str = msg_info.get('sent_at')

            if not message_id or not sent_at_str:
                logger.warning(f"Пропущен некорректный элемент в файле: {msg_info}")
                continue

            sent_at = datetime.datetime.fromisoformat(sent_at_str).astimezone(datetime.timezone.utc)

            time_diff = current_time - sent_at
            if time_diff.total_seconds() > DELETE_AFTER_HOURS * 3600:
                try:
                    await bot.delete_message(chat_id=target_chat_id, message_id=message_id)
                    logger.info(f"Сообщение {message_id} успешно удалено (отправлено в {sent_at_str}).")
                    deleted_count += 1
                except TelegramError as e:
                    # Обработка случаев, когда сообщение уже удалено или не существует
                    if "message to delete not found" in str(e).lower() or "bad request: message can't be deleted" in str(e).lower():
                        logger.warning(f"Сообщение {message_id} не найдено или не может быть удалено (возможно, уже удалено).")
                    else:
                        logger.error(f"Ошибка при удалении сообщения {message_id}: {e}")
            else:
                updated_messages_list.append(msg_info) # Оставляем сообщение, если время удаления еще не пришло
        except Exception as e:
            logger.error(f"Неизвестная ошибка при обработке сообщения {msg_info}: {e}")

    # Сохраняем обновленный список ID сообщений
    if deleted_count > 0 or len(messages_to_delete) != len(updated_messages_list):
        try:
            with open(MESSAGE_IDS_FILE, 'w') as f:
                yaml.dump(updated_messages_list, f, default_flow_style=False)
            logger.info(f"Обновлен файл {MESSAGE_IDS_FILE}. Удалено сообщений: {deleted_count}. Осталось: {len(updated_messages_list)}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении файла {MESSAGE_IDS_FILE}: {e}")
    else:
        logger.info("Нет сообщений для удаления или обновления.")


if __name__ == "__main__":
    asyncio.run(main())
