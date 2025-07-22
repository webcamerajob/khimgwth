import os
import json
import asyncio
from datetime import datetime
from telegram import Bot
# Убедитесь, что здесь импортированы все библиотеки, необходимые для вашего скрипта (например, requests, Pillow и т.д.)
# from PIL import Image, ImageDraw, ImageFont # Пример

# --- Конфигурация ---
# Ваши токены и ID чата, которые будут получены из переменных окружения GitHub Actions
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
ACCUWEATHER_API_KEY = os.getenv('ACCUWEATHER_API_KEY') # Если вы его используете

# Название файла для сохранения ID сообщений, должно совпадать с настройками в YAML
MESSAGES_TO_DELETE_FILE = 'messages_to_delete.json'

# --- Ваша логика получения погоды, генерации изображений и т.д. должна быть здесь ---
# Пример заглушек функций:
async def get_weather_data(api_key, location):
    print(f"Получение данных о погоде для {location}...")
    # Здесь ваш реальный код для получения данных (например, через requests)
    # Возвращает фиктивные данные для примера
    return {"temperature": 25, "condition": "Sunny"}

async def generate_weather_image(data, output_path):
    print(f"Генерация изображения погоды в {output_path}...")
    # Здесь ваш реальный код для генерации изображения (например, с помощью Pillow)
    # Создадим пустой файл-заглушку для примера
    with open(output_path, 'w') as f:
        f.write("dummy image content") # Это не реальное изображение, просто заглушка
    return output_path

# --- Функция отправки сообщений в Telegram и сохранения ID ---
async def send_weather_update(bot_instance: Bot, target_chat_id: str, photo_paths: list):
    """
    Отправляет фотографии погоды в указанный чат и сохраняет ID отправленных сообщений.
    """
    sent_message_ids = [] # Список для хранения ID сообщений, отправленных в рамках этого обновления

    # Отправка изображений
    for i, photo_path in enumerate(photo_paths):
        try:
            # В реальном проекте здесь будет `with open(photo_path, 'rb') as photo_file:`
            # Но для заглушки:
            if os.path.exists(photo_path): # Проверяем, что файл существует
                 with open(photo_path, 'rb') as photo_file:
                    # Здесь ваша логика для отправки фотографий с кнопками или без
                    # message = await bot_instance.send_photo(chat_id=target_chat_id, photo=photo_file, reply_markup=keyboard_markup_if_any)
                    message = await bot_instance.send_photo(chat_id=target_chat_id, photo=photo_file) # Пример без кнопок
                    
                    sent_message_ids.append(message.message_id) # Сохраняем ID отправленного сообщения
                    print(f"Отправлено фото {i+1} в чат {target_chat_id}, ID сообщения: {message.message_id}")
                    await asyncio.sleep(0.5) # Небольшая задержка между отправками фото
            else:
                print(f"Файл изображения не найден: {photo_path}")

        except Exception as e:
            print(f"Ошибка при отправке фото {photo_path}: {e}")

    # Сохранение ID сообщений для последующего удаления
    if sent_message_ids:
        # Загружаем существующие данные
        data_to_save = []
        if os.path.exists(MESSAGES_TO_DELETE_FILE):
            try:
                with open(MESSAGES_TO_DELETE_FILE, 'r', encoding='utf-8') as f:
                    data_to_save = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                print(f"Ошибка при чтении {MESSAGES_TO_DELETE_FILE}. Создаю новый файл.")
                data_to_save = []

        # Добавляем новую запись
        new_entry = {
            'timestamp': datetime.now().isoformat(),
            'chat_id': target_chat_id, # Используем тот же chat_id, куда отправляли сообщения
            'message_ids': sent_message_ids
        }
        data_to_save.append(new_entry)

        # Сохраняем обновленные данные обратно в файл
        try:
            with open(MESSAGES_TO_DELETE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            print(f"ID сообщений сохранены в {MESSAGES_TO_DELETE_FILE}.")
        except Exception as e:
            print(f"Ошибка при сохранении ID сообщений в {MESSAGES_TO_DELETE_FILE}: {e}")

# --- Главная функция для запуска в GitHub Actions ---
async def main():
    if not TELEGRAM_BOT_TOKEN:
        print("Ошибка: TELEGRAM_BOT_TOKEN не установлен.")
        return
    if not TELEGRAM_CHAT_ID:
        print("Ошибка: TELEGRAM_CHAT_ID не установлен.")
        return
    # if not ACCUWEATHER_API_KEY:
    #     print("Ошибка: ACCUWEATHER_API_KEY не установлен.")
    #     return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Пример использования ваших функций:
    # weather_data = await get_weather_data(ACCUWEATHER_API_KEY, "Kharkiv")
    # if weather_data:
    #     output_image_path = "weather_report.png"
    #     await generate_weather_image(weather_data, output_image_path)
    #     if os.path.exists(output_image_path):
    #         await send_weather_update(bot, TELEGRAM_CHAT_ID, [output_image_path])
    #         os.remove(output_image_path) # Удаляем временный файл
    # else:
    #     print("Не удалось получить данные о погоде.")

    # Для демонстрации работы JSON-файла, представим, что мы сгенерировали несколько путей к фото:
    dummy_photo_paths = ['temp_photo_1.txt', 'temp_photo_2.txt']
    for p in dummy_photo_paths:
        with open(p, 'w') as f: f.write("dummy") # Создаем пустые заглушки файлов
    
    await send_weather_update(bot, TELEGRAM_CHAT_ID, dummy_photo_paths)

    for p in dummy_photo_paths:
        if os.path.exists(p):
            os.remove(p) # Очистка заглушек


if __name__ == '__main__':
    asyncio.run(main())
