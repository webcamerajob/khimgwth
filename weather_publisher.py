import os
import json
import asyncio
from datetime import datetime
from telegram import Bot
import requests # Для HTTP-запросов (если используете API погоды)
from PIL import Image, ImageDraw, ImageFont # Для генерации изображений

# --- Конфигурация ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
ACCUWEATHER_API_KEY = os.getenv('ACCUWEATHER_API_KEY') 

# Название файла для сохранения ID сообщений, должно совпадать с настройками в YAML
MESSAGES_TO_DELETE_FILE = 'messages_to_delete.json'

# --- Логика получения данных о погоде ---
async def get_weather_data(api_key: str, location: str) -> dict:
    print(f"Получение данных о погоде для {location}...")
    # Здесь должен быть ваш реальный код для запроса к AccuWeather API
    # Пример использования requests (убедитесь, что у вас есть API ключ и URL):
    # try:
    #     url = f"http://dataservice.accuweather.com/locations/v1/cities/search?apikey={api_key}&q={location}&language=ru"
    #     response = requests.get(url)
    #     response.raise_for_status() # Вызывает исключение для плохих статусов (4xx или 5xx)
    #     location_data = response.json()
    #     if not location_data:
    #         print(f"Не найдено данных для местоположения: {location}")
    #         return None
    #     location_key = location_data[0]['Key']

    #     current_conditions_url = f"http://dataservice.accuweather.com/currentconditions/v1/{location_key}?apikey={api_key}&language=ru"
    #     response = requests.get(current_conditions_url)
    #     response.raise_for_status()
    #     weather_data = response.json()

    #     if weather_data:
    #         temp_c = weather_data[0]['Temperature']['Metric']['Value']
    #         weather_text = weather_data[0]['WeatherText']
    #         return {"temperature": temp_c, "condition": weather_text, "location": location}
    #     else:
    #         print("Не получены текущие условия погоды.")
    #         return None
    # except requests.exceptions.RequestException as e:
    #     print(f"Ошибка HTTP-запроса к AccuWeather API: {e}")
    #     return None
    # except Exception as e:
    #     print(f"Общая ошибка при получении данных о погоде: {e}")
    #     return None
    
    # ВОЗВРАЩАЙТЕ ФИКТИВНЫЕ ДАННЫЕ ДЛЯ ТЕСТИРОВАНИЯ, ЕСЛИ РЕАЛЬНЫЙ API НЕ НАСТРОЕН:
    return {"temperature": 15, "condition": "Малооблачно", "location": location}

# --- Логика генерации изображения погоды ---
async def generate_weather_image(weather_data: dict, output_path: str) -> str:
    print(f"Генерация изображения погоды в {output_path}...")
    try:
        # Создаем новое изображение (800x600, белый фон)
        img = Image.new('RGB', (800, 600), color=(255, 255, 255))
        d = ImageDraw.Draw(img)

        # Попытка загрузки шрифта. В GitHub Actions (Ubuntu) часто доступны шрифты DejaVu.
        try:
            # Попробуем более универсальный путь к шрифту или fallback на стандартный
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(font_path): # Если стандартный DejaVu не найден, попробуем другой
                font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
                if not os.path.exists(font_path): # Если и он не найден, используем шрифт по умолчанию
                    font = ImageFont.load_default()
                    small_font = ImageFont.load_default()
                    print("Предупреждение: Пользовательский шрифт не найден, используется шрифт по умолчанию.")
                else:
                    font = ImageFont.truetype(font_path, size=40)
                    small_font = ImageFont.truetype(font_path, size=24)
            else:
                font = ImageFont.truetype(font_path, size=40)
                small_font = ImageFont.truetype(font_path, size=24)

        except Exception as font_e:
            print(f"Ошибка загрузки шрифта: {font_e}. Используется шрифт по умолчанию.")
            font = ImageFont.load_default()
            small_font = ImageFont.load_default()

        # Цвет текста (черный)
        text_color = (0, 0, 0) 
        
        # Данные для отображения на изображении
        location = weather_data.get('location', 'Неизвестно')
        temperature = weather_data.get('temperature', '?')
        condition = weather_data.get('condition', '?')

        d.text((50, 50), f"Погода в {location}:", fill=text_color, font=font)
        d.text((50, 150), f"Температура: {temperature}°C", fill=text_color, font=small_font)
        d.text((50, 200), f"Условия: {condition}", fill=text_color, font=small_font)
        
        # Сохраняем изображение как PNG-файл
        img.save(output_path, "PNG")
        print(f"Изображение погоды успешно сгенерировано: {output_path}")
        
        return output_path # Возвращаем путь к созданному файлу

    except Exception as e:
        print(f"Ошибка при генерации изображения: {e}")
        return None # Возвращаем None, если генерация не удалась

# --- Функция отправки сообщений в Telegram и сохранения ID ---
async def send_weather_update(bot_instance: Bot, target_chat_id: str, photo_paths: list):
    """
    Отправляет фотографии погоды в указанный чат и сохраняет ID отправленных сообщений.
    """
    sent_message_ids = [] # Список для хранения ID сообщений, отправленных в рамках этого обновления

    for i, photo_path in enumerate(photo_paths):
        if not os.path.exists(photo_path):
            print(f"Ошибка: Файл изображения не найден для отправки: {photo_path}")
            continue # Пропускаем этот файл и переходим к следующему

        try:
            with open(photo_path, 'rb') as photo_file:
                message = await bot_instance.send_photo(chat_id=target_chat_id, photo=photo_file)
                
                sent_message_ids.append(message.message_id) 
                print(f"Отправлено фото {i+1} в чат {target_chat_id}, ID сообщения: {message.message_id}")
                await asyncio.sleep(0.5) # Небольшая задержка между отправками фото
        except Exception as e:
            print(f"Ошибка при отправке фото {photo_path}: {e}")

    # Сохранение ID сообщений для последующего удаления
    if sent_message_ids:
        data_to_save = []
        if os.path.exists(MESSAGES_TO_DELETE_FILE):
            try:
                with open(MESSAGES_TO_DELETE_FILE, 'r', encoding='utf-8') as f:
                    data_to_save = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                print(f"Ошибка при чтении {MESSAGES_TO_DELETE_FILE}. Создаю новый файл.")
                data_to_save = []

        new_entry = {
            'timestamp': datetime.now().isoformat(),
            'chat_id': target_chat_id, 
            'message_ids': sent_message_ids
        }
        data_to_save.append(new_entry)

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
    # Если вы используете ACCUWEATHER_API_KEY, раскомментируйте эту проверку:
    # if not ACCUWEATHER_API_KEY:
    #     print("Ошибка: ACCUWEATHER_API_KEY не установлен. Проверьте секреты GitHub.")
    #     return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Вызов функций получения данных и генерации изображений
    location_name = "Kharkiv" # Замените на реальное название города
    weather_data = await get_weather_data(ACCUWEATHER_API_KEY, location_name)
    
    if weather_data:
        output_image_path = "weather_report.png" # Имя файла для сохранения изображения
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
