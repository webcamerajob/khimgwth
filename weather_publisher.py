import logging
import requests
import asyncio
from telegram import Bot
import os
from typing import Dict, Any, List
from PIL import Image, ImageDraw, ImageFont
import random

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# URL для AccuWeather API
ACCUWEATHER_BASE_URL = "http://dataservice.accuweather.com/"

# --- Переключатель тестового режима ---
TEST_MODE = True  # Установите True для использования предустановленных данных, False для использования реального API

# --- Предустановленные данные о погоде ---
PRESET_WEATHER_DATA = {
    "Пномпень": {
        "Temperature": {"Metric": {"Value": 32.5}},
        "RealFeelTemperature": {"Metric": {"Value": 38.0}},
        "WeatherText": "Солнечно",
        "RelativeHumidity": 65,
        "Wind": {"Speed": {"Metric": {"Value": 15.2}}, "Direction": {"Localized": "Юго-восток"}},
        "Pressure": {"Metric": {"Value": 1009.5}},
    },
    "Сиануквиль": {
        "Temperature": {"Metric": {"Value": 28.1}},
        "RealFeelTemperature": {"Metric": {"Value": 31.5}},
        "WeatherText": "Переменная облачность",
        "RelativeHumidity": 80,
        "Wind": {"Speed": {"Metric": {"Value": 10.8}}, "Direction": {"Localized": "Запад"}},
        "Pressure": {"Metric": {"Value": 1010.1}},
    },
    "Сиемреап": {
        "Temperature": {"Metric": {"Value": 30.0}},
        "RealFeelTemperature": {"Metric": {"Value": 35.5}},
        "WeatherText": "Небольшой дождь",
        "RelativeHumidity": 75,
        "Wind": {"Speed": {"Metric": {"Value": 7.5}}, "Direction": {"Localized": "Север"}},
        "Pressure": {"Metric": {"Value": 1008.9}},
    },
}

# --- Путь к папке с фонами ---
BACKGROUNDS_FOLDER = "backgrounds"

# --- Словарь для сокращений направления ветра ---
WIND_DIRECTION_ABBR = {
    "Север": "С", "СВ": "СВ", "Восток": "В", "ЮВ": "ЮВ",
    "Юг": "Ю", "ЮЗ": "ЮЗ", "Запад": "З", "СЗ": "СЗ",
    "ССВ": "ССВ", "ВНВ": "ВНВ", "ВЮВ": "ВЮВ", "ЮЮВ": "ЮЮВ",
    "ЮЮЗ": "ЮЮЗ", "ЗЮЗ": "ЗЮЗ", "ЗСЗ": "ЗСЗ", "ССЗ": "ССЗ",
    "переменный": "переменный",
}

def get_wind_direction_abbr(direction_text: str) -> str:
    """
    Возвращает аббревиатуру для направления ветра.
    """
    normalized_text = direction_text.strip()
    return WIND_DIRECTION_ABBR.get(normalized_text, direction_text)

async def get_location_key(city_name: str) -> str | None:
    """
    Получает Location Key AccuWeather для заданного города.
    """
    if TEST_MODE:
        return "TEST_KEY" # Заглушка для тестового режима
    url = f"{ACCUWEATHER_BASE_URL}locations/v1/cities/search"
    params = {
        "apikey": os.getenv("ACCUWEATHER_API_KEY"),
        "q": city_name,
        "language": "ru-ru"
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data:
            logger.info(f"Найден Location Key для {city_name}: {data[0]['Key']} (TEST_MODE OFF)")
            return data[0]["Key"] # Возвращаем только ключ
        else:
            logger.warning(f"Не удалось найти Location Key для города: {city_name} (TEST_MODE OFF)")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе Location Key для {city_name} к AccuWeather API: {e} (TEST_MODE OFF)")
        return None

# Глобальная переменная для временного хранения названия города в тестовом режиме,
# чтобы get_current_weather мог найти нужные предустановленные данные.
city_to_process = ""

async def get_current_weather(location_key: str) -> Dict | None:
    """
    Получает текущие погодные условия для заданного Location Key.
    """
    if TEST_MODE:
        if city_to_process in PRESET_WEATHER_DATA:
            logger.info(f"Используются предустановленные данные для: {city_to_process}")
            return PRESET_WEATHER_DATA.get(city_to_process)
        return None

    url = f"{ACCUWEATHER_BASE_URL}currentconditions/v1/{location_key}"
    params = {
        "apikey": os.getenv("ACCUWEATHER_API_KEY"),
        "language": "ru-ru",
        "details": "true"
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data:
            logger.info(f"Получены данные о погоде для Location Key: {location_key} (TEST_MODE OFF)")
            return data[0] # Возвращаем первый элемент списка
        else:
            logger.warning(f"Не удалось получить данные о погоде для Location Key: {location_key} (TEST_MODE OFF)")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе погоды для Location Key {location_key} к AccuWeather API: {e} (TEST_MODE OFF)")
        return None

def get_random_background_image(city_name: str) -> str | None:
    """
    Возвращает случайный путь к файлу изображения фона для заданного города.
    """
    city_folder = os.path.join(BACKGROUNDS_FOLDER, city_name)
    if os.path.isdir(city_folder):
        image_files = [f for f in os.listdir(city_folder) if os.path.isfile(os.path.join(city_folder, f)) and f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
        if image_files:
            return os.path.join(city_folder, random.choice(image_files))
    logger.warning(f"Папка с фонами не найдена или пуста для города: {city_name} ({city_folder})")
    return None

def round_rectangle(draw, xy, radius, fill):
    x1, y1, x2, y2 = xy
    draw.rectangle((x1 + radius, y1, x2 - radius, y2), fill=fill)
    draw.rectangle((x1, y1 + radius, x2, y2 - radius), fill=fill)
    draw.ellipse((x1, y1, x1 + radius * 2, y1 + radius * 2), fill=fill)
    draw.ellipse((x2 - radius * 2, y1, x2, y1 + radius * 2), fill=fill)
    draw.ellipse((x1, y2 - radius * 2, x1 + radius * 2, y2), fill=fill)
    draw.ellipse((x2 - radius * 2, y2 - radius * 2, x2, y2), fill=fill)

def get_font(font_size: int):
    """
    Пытается загрузить шрифт, подходящий для кириллицы.
    Возвращает объект шрифта или None, если ни один шрифт не загружен.
    """
    # 1. Попробуйте загрузить Arial.ttf (предполагая, что он находится рядом со скриптом)
    try:
        font = ImageFont.truetype("arial.ttf", font_size, encoding="UTF-8")
        logger.info("Шрифт 'arial.ttf' успешно загружен.")
        return font
    except IOError:
        logger.warning("Шрифт 'arial.ttf' не найден. Попытка загрузить 'DejaVuSans.ttf'.")
        # 2. Попробуйте DejaVuSans.ttf (часто предустановлен в Linux)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size, encoding="UTF-8")
            logger.info("Шрифт 'DejaVuSans.ttf' успешно загружен.")
            return font
        except IOError:
            logger.warning("Шрифт 'DejaVuSans.ttf' не найден. Используется стандартный шрифт Pillow.")
            # 3. В крайнем случае используйте стандартный шрифт Pillow
            font = ImageFont.load_default()
            logger.warning("Используется стандартный шрифт Pillow. Некоторые символы могут отображаться некорректно.")
            return font
    except Exception as e:
        logger.error(f"Неизвестная ошибка при загрузке шрифта: {e}. Используется стандартный шрифт Pillow.")
        font = ImageFont.load_default()
        logger.warning("Используется стандартный шрифт Pillow. Некоторые символы могут отображаться некорректно.")
        return font


def create_weather_image(city_name: str, weather_data: Dict) -> str | None:
    """
    Создает изображение с информацией о погоде на фоне с полупрозрачной плашкой.
    """
    background_path = get_random_background_image(city_name)
    if not background_path:
        return None

    try:
        img = Image.open(background_path).convert("RGB")
        width, height = img.size
        
        draw = ImageDraw.Draw(img) 

        # Параметры текста
        weather_text_lines = [
            f"Погода в {city_name.capitalize()}:",
            f"Температура: {weather_data['Temperature']['Metric']['Value']:.1f}°C",
            f"Ощущается как: {weather_data['RealFeelTemperature']['Metric']['Value']:.1f}°C",
            f"{weather_data['WeatherText']}", # Состояние без эмодзи
            f"Влажность: {weather_data['RelativeHumidity']}%",
            f"Ветер: {get_wind_direction_abbr(weather_data['Wind']['Direction']['Localized'])}, {weather_data['Wind']['Speed']['Metric']['Value']:.1f} км/ч",
            f"Давление: {weather_data['Pressure']['Metric']['Value'] * 0.1:.1f} кПа",
        ]
        weather_text = "\n".join(weather_text_lines)

        # Рассчитываем размер плашки (85% ширины от полного кадра)
        plaque_width = int(width * 0.85)
        
        # Определяем размер шрифта на основе 75% от ширины плашки
        # Это потребует итеративного подбора или более сложного расчета
        # Для простоты, сначала установим базовый font_size
        font_size_base = int(height * 0.04)
        font = get_font(font_size_base)

        # Теперь определим реальный font_size так, чтобы текст занимал 75% ширины плашки
        # Это итеративный процесс: увеличиваем размер шрифта, пока текст не достигнет 75% ширины плашки
        # или пока не превысит ее. Начинаем с меньшего размера и увеличиваем.
        target_text_width_ratio = 0.75
        max_text_width = int(plaque_width * target_text_width_ratio)
        
        current_font_size = int(height * 0.02) # Начинаем с меньшего размера
        best_font = font # Сохраняем лучший найденный шрифт
        
        # Итеративно увеличиваем размер шрифта
        while True:
            test_font = get_font(current_font_size)
            if test_font is None: # Если шрифт не загрузился
                logger.warning("Не удалось загрузить шрифт для итеративного подбора размера.")
                break

            # Используем getbbox для более точного измерения размера текста
            # draw.textbbox((0,0), text, font=font) возвращает (left, top, right, bottom)
            # Ширина текста = right - left
            bbox = draw.textbbox((0, 0), weather_text, font=test_font, spacing=10)
            text_width_current = bbox[2] - bbox[0]

            if text_width_current <= max_text_width:
                best_font = test_font
                current_font_size += 1
            else:
                break # Текст стал слишком большим, используем предыдущий размер

        font = best_font # Используем найденный оптимальный шрифт
        
        # Пересчитываем размер текста с финальным шрифтом
        bbox = draw.textbbox((0, 0), weather_text, font=font, spacing=10)
        text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]

        # Высота плашки подстраивается под текст с отступами
        padding = int(width * 0.02) # Отступы от текста до краев плашки
        border_radius = int(width * 0.02) # Радиус скругления углов
        
        plaque_height = text_height + 2 * padding

        # Позиционирование плашки (по центру по горизонтали, небольшой отступ сверху)
        plaque_x1 = (width - plaque_width) // 2
        plaque_y1 = int(height * 0.05) # Небольшой отступ сверху
        plaque_x2 = plaque_x1 + plaque_width
        plaque_y2 = plaque_y1 + plaque_height

        # Создаем изображение для плашки с прозрачностью
        plaque_img = Image.new('RGBA', img.size, (0, 0, 0, 0)) # Полностью прозрачная основа
        plaque_draw = ImageDraw.Draw(plaque_img)

        # Рисуем скругленный прямоугольник на плашке
        round_rectangle(plaque_draw, (plaque_x1, plaque_y1, plaque_x2, plaque_y2), border_radius, (0, 0, 0, 150)) # Черный, полупрозрачный

        # Накладываем плашку на основное изображение
        img.paste(plaque_img, (0, 0), plaque_img)

        # Выравнивание текста по центру плашки
        text_x = plaque_x1 + (plaque_width - text_width) // 2
        text_y = plaque_y1 + padding
        
        draw.multiline_text((text_x, text_y), weather_text, fill=(255, 255, 255), font=font, spacing=10, align="center")

        output_path = f"weather_{city_name.lower().replace(' ', '_')}.png"
        img.save(output_path)
        return output_path

    except Exception as e:
        logger.error(f"Ошибка при создании изображения для {city_name}: {e}")
        return None

async def format_and_send_weather(bot: Bot, city_name: str, weather_data: Dict, target_chat_id: str):
    """
    Форматирует данные о погоде и отправляет изображение в Telegram.
    """
    image_path = create_weather_image(city_name, weather_data)
    if image_path:
        try:
            with open(image_path, 'rb') as photo:
                await bot.send_photo(chat_id=target_chat_id, photo=photo)
            os.remove(image_path) # Удаляем файл изображения после отправки
            logger.info(f"Изображение погоды для {city_name} успешно отправлено.")
        except Exception as e:
            logger.error(f"Ошибка при отправке изображения для {city_name}: {e}")
            await bot.send_message(chat_id=target_chat_id, text=f"Ошибка при отправке изображения погоды для {city_name}.", parse_mode='HTML')
    else:
        await bot.send_message(chat_id=target_chat_id, text=f"Не удалось создать изображение погоды для {city_name}.", parse_mode='HTML')

async def main():
    """
    Главная функция, которая запускается при выполнении скрипта.
    Собирает данные для каждого города и отправляет отдельное сообщение (теперь изображение).
    """
    global city_to_process # Объявляем глобальной для доступа в get_current_weather (тестовый режим)
    cities_to_publish = ["Пномпень", "Сиануквиль", "Сиемреап"]

    # Проверка наличия всех необходимых переменных окружения
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    accuweather_api_key = os.getenv("ACCUWEATHER_API_KEY")
    target_chat_id = os.getenv("TARGET_CHAT_ID")

    # Проверка конфигурации (API-ключ нужен только если TEST_MODE=False)
    if not all([telegram_bot_token, target_chat_id]) or (not TEST_MODE and not accuweather_api_key):
        logger.error("ОШИБКА: Отсутствуют необходимые переменные окружения. "
                     "Убедитесь, что TELEGRAM_BOT_TOKEN и TARGET_CHAT_ID установлены.")
        if not TEST_MODE and not accuweather_api_key:
            logger.error("ACCUWEATHER_API_KEY также необходим, когда TEST_MODE=False.")
        
        # Пытаемся отправить сообщение об ошибке, если хотя бы токен и chat_id доступны
        if telegram_bot_token and target_chat_id:
            bot = Bot(token=telegram_bot_token)
            await bot.send_message(chat_id=target_chat_id,
                                   text="❌ <b>Ошибка конфигурации бота!</b> Отсутствуют API-ключи или ID чата.",
                                   parse_mode='HTML')
        return

    bot = Bot(token=telegram_bot_token)

    # Создаем папку backgrounds и подпапки для городов, если их нет
    if not os.path.exists(BACKGROUNDS_FOLDER):
        os.makedirs(BACKGROUNDS_FOLDER)
        logger.info(f"Создана папка для фонов: {BACKGROUNDS_FOLDER}")
    for city in cities_to_publish:
        city_folder = os.path.join(BACKGROUNDS_FOLDER, city)
        if not os.path.exists(city_folder):
            os.makedirs(city_folder)
            logger.info(f"Создана папка для фонов города: {city_folder}")
    
    logger.warning(f"Убедитесь, что в папках '{BACKGROUNDS_FOLDER}/<НазваниеГорода>' есть изображения для использования в качестве фонов.")


    # Собираем и отправляем данные для каждого города отдельно
    for city in cities_to_publish:
        city_to_process = city # Устанавливаем глобальную переменную для тестового режима
        logger.info(f"Получаю данные для {city}...")
        
        weather_data = None
        if TEST_MODE:
            # В тестовом режиме напрямую берем из PRESET_WEATHER_DATA
            weather_data = PRESET_WEATHER_DATA.get(city)
            if not weather_data:
                logger.error(f"Предустановленные данные для города {city} не найдены.")
        else:
            # В реальном режиме сначала получаем Location Key, затем данные о погоде
            location_key = await get_location_key(city)
            if location_key:
                weather_data = await get_current_weather(location_key)
            else:
                await bot.send_message(chat_id=target_chat_id,
                                       text=f"⚠️ Не удалось получить Location Key для города <b>{city}</b>.",
                                       parse_mode='HTML')
                continue # Переходим к следующему городу, если ключ не получен

        if weather_data:
            await format_and_send_weather(bot, city, weather_data, target_chat_id)
        else:
            await bot.send_message(chat_id=target_chat_id,
                                   text=f"❌ Не удалось получить данные о погоде для <b>{city}</b>.",
                                   parse_mode='HTML')

        await asyncio.sleep(1) # Небольшая задержка между сообщениями

if __name__ == "__main__":
    asyncio.run(main())
