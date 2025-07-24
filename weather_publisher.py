import logging
import requests
import asyncio
import os
import datetime
from typing import Dict, Any, List, Optional
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError
from aiocircuitbreaker import circuit, CircuitBreaker
import yaml

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Константы ---
ACCUWEATHER_BASE_URL = "http://dataservice.accuweather.com/"
TEST_MODE = os.getenv("TEST_MODE", "False").lower() == "true"
WATERMARK_FILE = "watermark.png"
WATERMARK_SCALE_FACTOR = 0.25
AD_BUTTON_TEXT = "Новости"
AD_BUTTON_URL = "https://t.me/cambodiacriminal"
NEWS_BUTTON_TEXT = "Реклама"
NEWS_BUTTON_URL = "https://t.me/mister1dollar"
BACKGROUNDS_FOLDER = "backgrounds"
MESSAGE_IDS_FILE = "message_ids.yml"

# --- Настройки устойчивости ---
WEATHER_CB = CircuitBreaker(
    failure_threshold=3,  # 3 ошибки подряд
    recovery_timeout=60,  # 60 секунд блокировки
    name="AccuWeather API"
)
MAX_SEND_RETRIES = 3  # Максимальное количество попыток отправки
RETRY_DELAY = 2  # Задержка между попытками в секундах
TELEGRAM_TIMEOUT = 10  # Таймаут для запросов к Telegram API

# --- Оригинальные данные без изменений ---
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

WIND_DIRECTION_ABBR = {
    "Север": "С", "СВ": "СВ", "Восток": "В", "ЮВ": "ЮВ",
    "Юг": "Ю", "ЮЗ": "ЮЗ", "Запад": "З", "СЗ": "СЗ",
    "ССВ": "ССВ", "ВНВ": "ВНВ", "ВЮВ": "ВЮВ", "ЮЮВ": "ЮЮВ",
    "ЮЮЗ": "ЮЮЗ", "ЗЮЗ": "ЗЮЗ", "ЗСЗ": "ЗСЗ", "ССЗ": "ССЗ",
    "переменный": "переменный",
    "Юго-восток": "ЮВ",
    "Северо-запад": "СЗ",
    "Северо-восток": "СВ",
    "Юго-запад": "ЮЗ",
}

# --- Оригинальные функции без изменений ---
def get_wind_direction_abbr(direction_text: str) -> str:
    normalized_text = direction_text.strip()
    return WIND_DIRECTION_ABBR.get(normalized_text, direction_text)

async def get_location_key(city_name: str) -> str | None:
    if TEST_MODE:
        return "TEST_KEY"
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
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]["Key"]
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе Location Key для {city_name}: {e}")
        return None

# Глобальная переменная для временного хранения названия города
city_to_process = ""

@circuit(WEATHER_CB)
async def get_current_weather(location_key: str) -> Dict | None:
    if TEST_MODE:
        if city_to_process in PRESET_WEATHER_DATA:
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
        return data[0] if data else None
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе погоды: {e}")
        raise  # Для Circuit Breaker

def get_random_background_image(city_name: str) -> str | None:
    city_folder = os.path.join(BACKGROUNDS_FOLDER, city_name)
    if os.path.isdir(city_folder):
        import random
        image_files = [f for f in os.listdir(city_folder) 
                      if os.path.isfile(os.path.join(city_folder, f)) 
                      and f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
        return os.path.join(city_folder, random.choice(image_files)) if image_files else None
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
    try:
        font = ImageFont.truetype("arial.ttf", font_size, encoding="UTF-8")
        logger.info("Шрифт 'arial.ttf' успешно загружен.")
        return font
    except IOError:
        logger.warning("Шрифт 'arial.ttf' не найден. Попытка загрузить 'DejaVuSans.ttf'.")
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size, encoding="UTF-8")
            logger.info("Шрифт 'DejaVuSans.ttf' успешно загружен.")
            return font
        except IOError:
            logger.warning("Шрифт 'DejaVuSans.ttf' не найден. Используется стандартный шрифт Pillow.")
            font = ImageFont.load_default()
            logger.warning("Используется стандартный шрифт Pillow. Некоторые символы могут отображаться некорректно.")
            return font
    except Exception as e:
        logger.error(f"Неизвестная ошибка при загрузке шрифта: {e}. Используется стандартный шрифт Pillow.")
        font = ImageFont.load_default()
        logger.warning("Используется стандартный шрифт Pillow. Некоторые символы могут отображаться некорректно.")
        return font

def add_watermark(base_image_path: str) -> str | None:
    watermarked_image_path = base_image_path.replace(".png", "_watermarked.png")
    
    try:
        base_img = Image.open(base_image_path).convert("RGBA")
        base_width, base_height = base_img.size

        if not os.path.exists(WATERMARK_FILE):
            logger.warning(f"Файл вотермарки не найден: {WATERMARK_FILE}")
            return None

        watermark_img = Image.open(WATERMARK_FILE).convert("RGBA")

        # Масштабирование вотермарки
        target_watermark_width = int(base_width * WATERMARK_SCALE_FACTOR)
        watermark_height = int(watermark_img.height * (target_watermark_width / watermark_img.width))
        watermark_img = watermark_img.resize((target_watermark_width, watermark_height), Image.Resampling.LANCZOS)

        # Позиционирование
        padding = int(base_width * 0.02)
        position_x = base_width - watermark_img.width - padding
        position_y = padding

        # Создание прозрачного слоя
        transparent_layer = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        transparent_layer.paste(watermark_img, (position_x, position_y), watermark_img)

        # Композиция изображений
        final_img = Image.alpha_composite(base_img, transparent_layer)
        final_img.save(watermarked_image_path, "PNG")
        return watermarked_image_path

    except FileNotFoundError:
        logger.error(f"Файл не найден: {base_image_path} или {WATERMARK_FILE}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при добавлении вотермарки: {e}")
        return None

def create_weather_image(city_name: str, weather_data: Dict) -> str | None:
    background_path = get_random_background_image(city_name)
    if not background_path:
        return None

    try:
        img = Image.open(background_path).convert("RGB")
        width, height = img.size
        draw = ImageDraw.Draw(img) 

        # Формирование текста погоды
        wind_direction_text = weather_data['Wind']['Direction']['Localized']
        wind_direction_abbr = get_wind_direction_abbr(wind_direction_text)
        weather_text_lines = [
            f"Погода в городе {city_name}:",
            f"Температура: {weather_data['Temperature']['Metric']['Value']:.1f}°C",
            f"Ощущается как: {weather_data['RealFeelTemperature']['Metric']['Value']:.1f}°C",
            f"{weather_data['WeatherText']}",
            f"Влажность: {weather_data['RelativeHumidity']}%",
            f"Ветер: {wind_direction_abbr}, {weather_data['Wind']['Speed']['Metric']['Value']:.1f} км/ч",
        ]
        weather_text = "\n".join(weather_text_lines)

        # Рассчет размеров плашки
        plaque_width = int(width * 0.85)
        target_text_width_ratio = 0.75
        max_text_width_for_font_sizing = int(plaque_width * target_text_width_ratio)
        current_font_size = 15
        best_font = get_font(current_font_size)
        
        # Подбор размера шрифта
        while True:
            test_font = get_font(current_font_size + 1)
            if test_font is None:
                break
            max_line_width = 0
            for line in weather_text_lines:
                left, top, right, bottom = draw.textbbox((0,0), line, font=test_font)
                line_width = right - left
                max_line_width = max(max_line_width, line_width)
            if max_line_width <= max_text_width_for_font_sizing:
                best_font = test_font
                current_font_size += 1
            else:
                break

        font = best_font
        
        # Рассчет размеров текста
        left, top, right, bottom = draw.textbbox((0, 0), weather_text, font=font, spacing=10)
        text_width = right - left
        text_height = bottom - top

        # Параметры плашки
        padding = int(width * 0.03)
        border_radius = int(width * 0.02)
        plaque_height = text_height + 2 * padding
        plaque_x1 = (width - plaque_width) // 2
        plaque_y1 = (height - plaque_height) // 2
        plaque_x2 = plaque_x1 + plaque_width
        plaque_y2 = plaque_y1 + plaque_height

        # Создание плашки
        plaque_img = Image.new('RGBA', img.size, (0, 0, 0, 0))
        plaque_draw = ImageDraw.Draw(plaque_img)
        round_rectangle(plaque_draw, (plaque_x1, plaque_y1, plaque_x2, plaque_y2), border_radius, (0, 0, 0, 150))
        img.paste(plaque_img, (0, 0), plaque_img)

        # Отрисовка текста
        text_x = plaque_x1 + (plaque_width - text_width) // 2
        text_y = plaque_y1 + (plaque_height - text_height) // 2
        draw.multiline_text((text_x, text_y), weather_text, fill=(255, 255, 255), font=font, spacing=10, align="center")

        # Сохранение и добавление вотермарки
        original_output_path = f"weather_{city_name.lower().replace(' ', '_')}.png"
        img.save(original_output_path)
        watermarked_path = add_watermark(original_output_path)
        return watermarked_path if watermarked_path else original_output_path
    
    except Exception as e:
        logger.error(f"Ошибка при создании изображения для {city_name}: {e}")
        return None

def save_message_id(message_id: int):
    try:
        messages = []
        if os.path.exists(MESSAGE_IDS_FILE):
            with open(MESSAGE_IDS_FILE, 'r') as f:
                loaded_data = yaml.safe_load(f)
                if isinstance(loaded_data, list):
                    messages = loaded_data
        
        current_time_utc = datetime.datetime.now(datetime.timezone.utc)
        messages.append({
            'message_id': message_id,
            'sent_at': current_time_utc.isoformat()
        })

        with open(MESSAGE_IDS_FILE, 'w') as f:
            yaml.dump(messages, f, default_flow_style=False)
        logger.info(f"Сообщение ID {message_id} сохранено")
    except Exception as e:
        logger.error(f"Ошибка при сохранении ID сообщения: {e}")

# --- Новые функции для проверки отправки ---
async def verify_message_sent(bot: Bot, chat_id: str, message_id: int) -> bool:
    """Проверяет, было ли сообщение доставлено в чат"""
    try:
        # Попытка получить информацию о сообщении
        try:
            message = await bot.get_chat(chat_id=chat_id, message_id=message_id)
            return True
        except TelegramError:
            pass
        
        # Альтернативный метод: проверка последних сообщений
        updates = await bot.get_updates(limit=10, timeout=5)
        for update in updates:
            if update.message and update.message.message_id == message_id:
                return True
        
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки сообщения {message_id}: {e}")
        return False

async def send_photo_with_retry_and_verify(
    bot: Bot,
    chat_id: str,
    photo_path: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> Optional[int]:
    """Отправляет фото с повторными попытками и проверкой доставки"""
    for attempt in range(1, MAX_SEND_RETRIES + 1):
        try:
            with open(photo_path, 'rb') as photo_file:
                message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file,
                    reply_markup=reply_markup,
                    timeout=TELEGRAM_TIMEOUT
                )
                
                # Проверка доставки
                if await verify_message_sent(bot, chat_id, message.message_id):
                    return message.message_id
                else:
                    logger.warning(f"Не удалось подтвердить доставку сообщения {message.message_id}")
                    
        except TelegramError as e:
            logger.warning(f"Попытка {attempt}/{MAX_SEND_RETRIES} не удалась: {e}")
            if attempt < MAX_SEND_RETRIES:
                await asyncio.sleep(RETRY_DELAY * attempt)
        except Exception as e:
            logger.error(f"Критическая ошибка при отправке: {e}")
            break
    
    logger.error(f"Не удалось отправить фото после {MAX_SEND_RETRIES} попыток")
    return None

# --- Основная функция ---
async def main():
    global city_to_process
    print("DEBUG: --- Запуск функции main() ---")
    cities_to_publish = ["Пномпень", "Сиануквиль", "Сиемреап"]
    generated_image_paths = []

    # Проверка переменных окружения
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    accuweather_api_key = os.getenv("ACCUWEATHER_API_KEY")
    target_chat_id = os.getenv("TARGET_CHAT_ID")
    
    if not all([telegram_bot_token, target_chat_id]) or (not TEST_MODE and not accuweather_api_key):
        logger.error("ОШИБКА: Отсутствуют необходимые переменные окружения")
        return

    bot = Bot(token=telegram_bot_token)
    print("DEBUG: Бот Telegram инициализирован")

    # Создание папок для фонов
    if not os.path.exists(BACKGROUNDS_FOLDER):
        os.makedirs(BACKGROUNDS_FOLDER)
        logger.info(f"Создана папка для фонов: {BACKGROUNDS_FOLDER}")
    
    for city in cities_to_publish:
        city_folder = os.path.join(BACKGROUNDS_FOLDER, city)
        if not os.path.exists(city_folder):
            os.makedirs(city_folder)
            logger.info(f"Создана папка для фонов города: {city_folder}")

    # Получение данных и создание изображений
    for city in cities_to_publish:
        city_to_process = city
        logger.info(f"Обработка города: {city}")
        
        weather_data = None
        if TEST_MODE:
            weather_data = PRESET_WEATHER_DATA.get(city)
        else:
            location_key = await get_location_key(city)
            if location_key:
                weather_data = await get_current_weather(location_key)
        
        if weather_data:
            image_path = create_weather_image(city, weather_data)
            if image_path:
                generated_image_paths.append(image_path)
                print(f"DEBUG: Изображение создано: {image_path}")
        await asyncio.sleep(0.5)  # Задержка между городами

    # Отправка изображений с гарантией порядка
    if generated_image_paths:
        print("DEBUG: Начало отправки изображений")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(AD_BUTTON_TEXT, url=AD_BUTTON_URL),
             InlineKeyboardButton(NEWS_BUTTON_TEXT, url=NEWS_BUTTON_URL)]
        ])

        for i, path in enumerate(generated_image_paths):
            print(f"DEBUG: Отправка фото {i+1}/{len(generated_image_paths)}: {path}")
            message_id = await send_photo_with_retry_and_verify(
                bot=bot,
                chat_id=target_chat_id,
                photo_path=path,
                reply_markup=keyboard if i == len(generated_image_paths) - 1 else None
            )
            
            if message_id:
                save_message_id(message_id)
                print(f"DEBUG: Сообщение отправлено и проверено: {message_id}")
            else:
                logger.error(f"Не удалось отправить фото: {path}")
            
            # Небольшая задержка между сообщениями
            await asyncio.sleep(1)
    else:
        logger.error("Нет изображений для отправки")
        await bot.send_message(
            chat_id=target_chat_id,
            text="Не удалось сгенерировать изображения погоды",
            parse_mode='HTML'
        )

    # Очистка временных файлов
    print("DEBUG: Очистка временных файлов")
    for path in generated_image_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
            if path.endswith("_watermarked.png") and os.path.exists(path.replace("_watermarked.png", ".png")):
                os.remove(path.replace("_watermarked.png", ".png"))
        except Exception as e:
            logger.error(f"Ошибка при удалении файла {path}: {e}")
    
    print("DEBUG: --- Завершение функции main() ---")

if __name__ == "__main__":
    asyncio.run(main())
