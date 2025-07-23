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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Настройки ---
MESSAGE_IDS_FILE = "message_ids.yml"  # Файл для хранения ID сообщений
DELETE_AFTER_MINUTES = 1              # Через сколько минут удалять сообщения
MAX_HISTORY_LINES = 300               # Максимальное количество хранимых записей

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
        try:
            with open(MESSAGE_IDS_FILE, 'r') as f:
                data = yaml.safe_load(f)
                
                if isinstance(data, list):
                    messages_to_delete = data
                elif data is None:
                    logger.info(f"Файл {MESSAGE_IDS_FILE} пуст.")
                else:
                    logger.warning(f"Файл {MESSAGE_IDS_FILE} содержит некорректный формат данных. Ожидался список.")
        except yaml.YAMLError as e:
            logger.error(f"Ошибка при парсинге YAML файла {MESSAGE_IDS_FILE}: {e}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка при чтении файла {MESSAGE_IDS_FILE}: {e}")
    else:
        logger.info(f"Файл {MESSAGE_IDS_FILE} не найден. Пока нет сообщений для удаления.")
        return  # Если файла нет, значит, пока нечего удалять

    if not messages_to_delete:
        logger.info("Нет сообщений для удаления.")
        return

    current_time = datetime.datetime.now(datetime.timezone.utc)
    updated_messages_list = []
    deleted_count = 0
    error_count = 0

    # Очистка старых записей по достижению лимита (FIFO)
    if len(messages_to_delete) > MAX_HISTORY_LINES:
        # Удаляем самые старые записи (первые в списке)
        num_to_remove = len(messages_to_delete) - MAX_HISTORY_LINES
        removed_count = 0
        
        # Пытаемся удалить самые старые сообщения из Telegram
        for i in range(num_to_remove):
            msg_info = messages_to_delete[i]
            try:
                message_id = msg_info.get('message_id')
                if message_id:
                    try:
                        await bot.delete_message(chat_id=target_chat_id, message_id=message_id)
                        logger.info(f"Удалено старое сообщение {message_id} (очистка истории)")
                        removed_count += 1
                    except TelegramError as e:
                        # Если сообщение уже удалено или недоступно, просто пропускаем
                        if "message to delete not found" not in str(e).lower() and "message can't be deleted" not in str(e).lower():
                            logger.warning(f"Не удалось удалить старое сообщение {message_id}: {e}")
            except Exception as e:
                logger.error(f"Ошибка при удалении старого сообщения: {e}")
        
        # Оставляем только последние MAX_HISTORY_LINES записей
        messages_to_delete = messages_to_delete[num_to_remove:]
        logger.info(f"Очистка истории: удалено {removed_count} старых записей, осталось {len(messages_to_delete)}")

    # Обработка сообщений для удаления по времени
    for msg_info in messages_to_delete:
        try:
            message_id = msg_info.get('message_id')
            sent_at_str = msg_info.get('sent_at')

            if not message_id or not sent_at_str:
                logger.warning(f"Пропущен некорректный элемент в файле: {msg_info}")
                continue

            try:
                # Преобразуем строку в datetime объект
                sent_at = datetime.datetime.fromisoformat(sent_at_str)
                
                # Убедимся, что время в UTC
                if sent_at.tzinfo is None:
                    sent_at = sent_at.replace(tzinfo=datetime.timezone.utc)
                else:
                    sent_at = sent_at.astimezone(datetime.timezone.utc)
            except ValueError as e:
                logger.error(f"Некорректный формат времени в элементе {msg_info}: {e}")
                continue

            time_diff = current_time - sent_at
            minutes_diff = time_diff.total_seconds() / 60
            
            if minutes_diff > DELETE_AFTER_MINUTES:
                try:
                    await bot.delete_message(chat_id=target_chat_id, message_id=message_id)
                    logger.info(f"Сообщение {message_id} успешно удалено (отправлено в {sent_at_str}, прошло {minutes_diff:.1f} минут).")
                    deleted_count += 1
                except TelegramError as e:
                    error_count += 1
                    # Обработка случаев, когда сообщение уже удалено или не существует
                    if "message to delete not found" in str(e).lower() or "message can't be deleted" in str(e).lower():
                        logger.warning(f"Сообщение {message_id} не найдено или не может быть удалено: {e}")
                    else:
                        logger.error(f"Ошибка при удалении сообщения {message_id}: {e}")
                except Exception as e:
                    error_count += 1
                    logger.error(f"Неизвестная ошибка при удалении сообщения {message_id}: {e}")
            else:
                # Сохраняем сообщение для будущей проверки
                updated_messages_list.append(msg_info)
                logger.debug(f"Сообщение {message_id} еще не готово к удалению (прошло {minutes_diff:.1f}/{DELETE_AFTER_MINUTES} минут)")
        except Exception as e:
            error_count += 1
            logger.error(f"Неизвестная ошибка при обработке сообщения {msg_info}: {e}")

    # Сохраняем обновленный список ID сообщений
    try:
        with open(MESSAGE_IDS_FILE, 'w') as f:
            yaml.dump(updated_messages_list, f, default_flow_style=False)
        logger.info(f"Обновлен файл {MESSAGE_IDS_FILE}. Удалено: {deleted_count}, Ошибок: {error_count}, Осталось: {len(updated_messages_list)}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении файла {MESSAGE_IDS_FILE}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
