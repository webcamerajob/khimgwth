import os
import json
import asyncio
from datetime import datetime
from telegram import Bot
# Убедитесь, что здесь импортированы ВСЕ библиотеки, необходимые для вашего скрипта.
# Например:
# import requests
# from PIL import Image, ImageDraw, ImageFont

# --- Конфигурация ---
# Ваши токены и ID чата будут получены из переменных окружения GitHub Actions
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
ACCUWEATHER_API_KEY = os.getenv('ACCUWEATHER_API_KEY') # Если вы его используете

# Название файла для сохранения ID сообщений. Должно совпадать с настройками в YAML.
MESSAGES_TO_DELETE_FILE = 'messages_to_delete.json'

# --- ВАШ КОД: Логика получения данных о погоде ---
# Пример функции (замените своим реальным кодом):
async def get_weather_data(api_key: str, location: str) -> dict:
    print(f"Получение данных о погоде для {location}...")
    # Здесь должен быть ваш реальный код для запроса к AccuWeather API или другому источнику
    # Например, с использованием библиотеки 'requests'
    # response = requests.get(f"ВАШ_URL_API?apikey={api_key}&location={location}...")
    # data = response.json()
    # return data
    
    # ВОЗВРАЩАЙТЕ РЕАЛЬНЫЕ ДАННЫЕ О ПОГОДЕ ИЛИ None В СЛУЧАЕ ОШИБКИ
    # Для примера:
    return {"temperature": 25, "condition": "Sunny", "location": location}

# --- ВАШ КОД: Логика генерации изображения погоды ---
# Пример функции (замените своим реальным кодом):
async def generate_weather_image(weather_data: dict, output_path: str) -> str:
    print(f"Генерация изображения погоды в {output_path}...")
    # Здесь должен быть ваш реальный код для создания изображения
    # Например, с использованием библиотеки Pillow (PIL):
    # img = Image.new('RGB', (600, 400), color = (73, 109, 137))
    # d = ImageDraw.Draw(img)
    # font = ImageFont.truetype('path/to/your/font.ttf', 36) # Укажите путь к шрифту
    # d.text((10,10), f"Температура: {weather_data['temperature']}°C", fill=(255,255,0), font=font)
    # img.save(output_path)

    # Для успешного запуска в GitHub Actions, пока у вас нет реальной генерации,
    # убедитесь, что функция создает хоть какой-то файл.
    # Если вы не используете Pillow и просто хотите проверить workflow,
    # можно создать временный пустой файл как заглушку:
    try:
        with open(output_path, 'w') as f:
            f.write("This is a dummy image file. Replace with actual image generation.")
        print(f"Создан файл-заглушка: {output_path}")
    except Exception as e:
        print(f"Ошибка при создании файла-заглушки {output_path}: {e}")
        return None # Возвращаем None, если создание файла не удалось

    return output_path

# --- Функция отправки сообщений в Telegram и сохранения ID ---
async def send_weather_update(bot_instance: Bot, target_chat_id: str, photo_paths: list):
    """
    Отправляет фотографии погоды в указанный чат и сохраняет ID отправленных сообщений.
    """
    sent_message_ids = [] # Список для хранения ID сообщений, отправленных в рамках этого обновления

    # Отправка изображений
    for i, photo_path in enumerate(photo_paths):
        if not os.path.exists(photo_path):
            print(f"Ошибка: Файл изображения не найден для отправки: {photo_path}")
            continue # Пропускаем этот файл и переходим к следующему

        try:
            with open(photo_path, 'rb') as photo_file:
                # Здесь ваша логика для отправки фотографий с кнопками или без
                # message = await bot_instance.send_photo(chat_id=target_chat_id, photo=photo_file, reply_markup=keyboard_markup_if_any)
                message = await bot_instance.send_photo(chat_id=target_chat_id, photo=photo_file)
                
                sent_message_ids.append(message.message_id) # Сохраняем ID отправленного сообщения
                print(f"Отправлено фото {i+1} в чат {target_chat_id}, ID сообщения: {message.message_id}")
                await asyncio.sleep(0.5) # Небольшая задержка между отправками фото
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
        print("Ошибка: TELEGRAM_BOT_TOKEN не установлен. Проверьте секреты GitHub.")
        return
    if not TELEGRAM_CHAT_ID:
        print("Ошибка: TELEGRAM_CHAT_ID не установлен. Проверьте секреты GitHub.")
        return
    # Если используете ACCUWEATHER_API_KEY, раскомментируйте эту проверку:
    # if not ACCUWEATHER_API_KEY:
    #     print("Ошибка: ACCUWEATHER_API_KEY не установлен. Проверьте секреты GitHub.")
    #     return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # --- ВАШ КОД: Вызов функций получения данных и генерации изображений ---
    # Пример использования ваших функций:
    location_name = "Kharkiv" # Замените на реальное название города
    weather_data = await get_weather_data(ACCUWEATHER_API_KEY, location_name)
    
    if weather_data:
        output_image_path = "weather_report.png" # Убедитесь, что это имя файла, который вы генерируете
        generated_path = await generate_weather_image(weather_data, output_image_path)
        
        if generated_path and os.path.exists(generated_path):
            await send_weather_update(bot, TELEGRAM_CHAT_ID, [generated_path])
            os.remove(generated_path) # Удаляем временный файл после отправки
            print(f"Временный файл {generated_path} удален.")
        else:
            print(f"Не удалось сгенерировать или найти файл изображения для {location_name}.")
    else:
        print(f"Не удалось получить данные о погоде для {location_name}.")


if __name__ == '__main__':
    asyncio.run(main())
