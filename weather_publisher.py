import logging
import requests
import asyncio
import os
import datetime
from typing import Dict, Any, List
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
import yaml  # Импортируем PyYAML

font_cache: Dict[int, ImageFont.FreeTypeFont] = {}

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Настройки и Константы ---
ACCUWEATHER_BASE_URL = "http://dataservice.accuweather.com/"

# Переключатель тестового режима (можно управлять из YML через env var TEST_MODE)
TEST_MODE = os.getenv("TEST_MODE", "False").lower() == "true"  # Читаем из переменной окружения, по умолчанию False

# Настройки вотермарки
WATERMARK_FILE = "watermark.png"  # Имя файла вашей вотермарки, расположенного в корневой папке
WATERMARK_SCALE_FACTOR = 0.35  # Масштаб вотермарки (например, 0.25 означает 25% от ширины основного изображения)

# Настройки кнопок
AD_BUTTON_TEXT = "Новости"
AD_BUTTON_URL = "https://t.me/cambodiacriminal"
NEWS_BUTTON_TEXT = "Реклама"
NEWS_BUTTON_URL = "https://t.me/mister1dollar"

# Путь к папке с фонами
BACKGROUNDS_FOLDER = "backgroung2"

# Файл для сохранения ID сообщений
MESSAGE_IDS_FILE = "message_ids.yml"

# --- Предустановленные данные о погоде (для TEST_MODE) ---
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

# --- Словарь для сокращений направления ветра ---
WIND_DIRECTION_ABBR = {
    "Север": "С", "СВ": "СВ", "Восток": "В", "ЮВ": "ЮВ",
    "Юг": "Ю", "ЮЗ": "ЮЗ", "Запад": "З", "СЗ": "СЗ",
    "ССВ": "ССВ", "ВНВ": "ВНВ", "ВЮВ": "ВЮВ", "ЮЮВ": "ЮЮВ",
    "ЮЮЗ": "ЮЮЗ", "ЗЮЗ": "ЗЮЗ", "ЗСЗ": "ЗСЗ", "ССЗ": "ССЗ",
    "переменный": "переменный",
    "Юго-восток": "ЮВ",  # Добавлено
    "Северо-запад": "СЗ",  # Добавлено
    "Северо-восток": "СВ",  # Добавлено
    "Юго-запад": "ЮЗ",  # Добавлено
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
        return "TEST_KEY"  # Заглушка для тестового режима
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
        if data and isinstance(data, list) and len(data) > 0:  # Убеждаемся, что это список и не пустой
            # Исправлено: AccuWeather API для поиска городов возвращает список,
            # и ключ находится в первом элементе списка.
            logger.info(f"Найден Location Key для {city_name}: {data[0]['Key']} (TEST_MODE OFF)")
            return data[0]["Key"]  # Доступ к первому элементу списка
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
        if data and isinstance(data, list) and len(data) > 0:  # Убеждаемся, что это список и не пустой
            # Исправлено: AccuWeather API для текущих условий возвращает список,
            # и данные находятся в первом элементе списка.
            logger.info(f"Получены данные о погоде для Location Key: {location_key} (TEST_MODE OFF)")
            return data[0]  # Доступ к первому элементу списка
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
        import random  # Импортируем random локально для этой функции, если не импортирован в начале
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

def get_font(font_size: int) -> ImageFont.FreeTypeFont:
    """
    Возвращает шрифт нужного размера из кэша или загружает его с диска.
    """
    if font_size in font_cache:
        return font_cache[font_size]

    try:
        font = ImageFont.truetype("arial.ttf", font_size, encoding="UTF-8")
        logger.info(f"Шрифт 'arial.ttf' загружен и закеширован (размер {font_size}).")
    except IOError:
        logger.warning("Шрифт 'arial.ttf' не найден. Попытка загрузить 'DejaVuSans.ttf'.")
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", font_size, encoding="UTF-8")
            logger.info(f"Шрифт 'DejaVuSans.ttf' загружен и закеширован (размер {font_size}).")
        except IOError:
            logger.warning("Оба шрифта не найдены. Используется стандартный шрифт Pillow.")
            font = ImageFont.load_default()
        except Exception as e:
            logger.error(f"Неизвестная ошибка при загрузке 'DejaVuSans.ttf': {e}")
            font = ImageFont.load_default()
    except Exception as e:
        logger.error(f"Неизвестная ошибка при загрузке 'arial.ttf': {e}")
        font = ImageFont.load_default()

    font_cache[font_size] = font
    return font

def add_watermark(base_image_path: str) -> str | None:
    """
    Накладывает вотермарку из 'watermark.png' на изображение по заданному пути.
    Вотермарка масштабируется и размещается в правом верхнем углу.
    Возвращает путь к изображению с вотермаркой или None в случае ошибки.
    """
    watermarked_image_path = base_image_path.replace(".png", "_watermarked.png")
    
    try:
        base_img = Image.open(base_image_path).convert("RGBA")  # Открываем как RGBA для прозрачности
        base_width, base_height = base_img.size

        watermark_path = WATERMARK_FILE
        if not os.path.exists(watermark_path):
            logger.warning(f"Файл вотермарки не найден по пути: {watermark_path}. Наложение вотермарки пропущено.")
            return None

        watermark_img = Image.open(watermark_path).convert("RGBA")

        # Масштабируем вотермарку на основе ширины основного изображения
        target_watermark_width = int(base_width * WATERMARK_SCALE_FACTOR)
        watermark_height = int(watermark_img.height * (target_watermark_width / watermark_img.width))
        watermark_img = watermark_img.resize((target_watermark_width, watermark_height), Image.Resampling.LANCZOS)

        # Позиционируем вотермарку в правом верхнем углу с отступами
        padding = int(base_width * 0.02)  # Отступ 2% от края
        position_x = base_width - watermark_img.width - padding
        position_y = padding

        # Создаем пустой прозрачный слой для вставки вотермарки
        transparent_layer = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        transparent_layer.paste(watermark_img, (position_x, position_y), watermark_img)

        # Компонуем вотермарку с основным изображением
        final_img = Image.alpha_composite(base_img, transparent_layer)
        
        final_img.save(watermarked_image_path, "PNG")
        logger.info(f"Вотермарка добавлена к {base_image_path}. Сохранено как {watermarked_image_path}")
        return watermarked_image_path

    except FileNotFoundError:
        logger.error(f"Файл вотермарки '{WATERMARK_FILE}' не найден. Убедитесь, что он находится в корневой директории скрипта.")
        return None
    except Exception as e:
        logger.error(f"Ошибка при добавлении вотермарки к {base_image_path}: {e}")
        return None

def create_weather_frame(city_name: str, weather_data: Dict) -> Image.Image | None:
    """
    Создает отдельный кадр изображения с текстом погоды для использования в GIF-анимации.
    Возвращает объект Image.
    """
    background_path = get_random_background_image(city_name)
    if not background_path:
        return None

    try:
        img = Image.open(background_path).convert("RGB")
        width, height = img.size
        draw = ImageDraw.Draw(img)

        wind_direction_text = weather_data['Wind']['Direction']['Localized']
        wind_direction_abbr = get_wind_direction_abbr(wind_direction_text)

        weather_text_lines = [
            f"Погода в городе {city_name}:\n",
            f"Температура: {weather_data['Temperature']['Metric']['Value']:.1f}°C",
            f"Ощущается как: {weather_data['RealFeelTemperature']['Metric']['Value']:.1f}°C",
            f"{weather_data['WeatherText']}",
            f"Влажность: {weather_data['RelativeHumidity']}%",
            f"Ветер: {wind_direction_abbr}, {weather_data['Wind']['Speed']['Metric']['Value']:.1f} км/ч",
        ]
        weather_text = "\n".join(weather_text_lines)

        plaque_width = int(width * 0.85)
        padding = int(width * 0.03)
        border_radius = int(width * 0.02)

        font = get_font(24)

        left, top, right, bottom = draw.textbbox((0, 0), weather_text, font=font, spacing=10)
        text_width = right - left
        text_height = bottom - top
        plaque_height = text_height + 2 * padding

        plaque_x1 = (width - plaque_width) // 2
        plaque_y1 = (height - plaque_height) // 2
        plaque_x2 = plaque_x1 + plaque_width
        plaque_y2 = plaque_y1 + plaque_height

        # Создаем полупрозрачный слой
        plaque_img = Image.new('RGBA', img.size, (0, 0, 0, 0))
        plaque_draw = ImageDraw.Draw(plaque_img)
        round_rectangle(plaque_draw, (plaque_x1, plaque_y1, plaque_x2, plaque_y2), border_radius, (0, 0, 0, 150))

        # Объединяем с основным изображением
        img = img.convert("RGBA")  # временно переведем в RGBA
        img = Image.alpha_composite(img, plaque_img).convert("RGB")  # снова в RGB
        draw = ImageDraw.Draw(img)  # пересоздаем объект draw после преобразования

        text_x = plaque_x1 + (plaque_width - text_width) // 2
        text_y = plaque_y1 + (plaque_height - text_height) // 2
        draw.multiline_text((text_x, text_y), weather_text, fill=(255, 255, 255), font=font, spacing=10, align="center")

        return img

    except Exception as e:
        logger.error(f"Ошибка при создании кадра для {city_name}: {e}")
        return None

def create_weather_gif(frames: List[Image.Image], output_path: str = "output/weather.gif") -> str:
    if not frames:
        logger.error("Нет кадров для создания GIF.")
        return ""

    final_frames = []
    durations = []

    transition_steps = 8       # Количество промежуточных кадров для плавности
    hold_duration = 800        # Сколько держать каждый основной кадр (мс)
    blend_duration = 100       # Длительность каждого blended-кадра (мс)

    num_frames = len(frames)

    for i in range(num_frames):
        current = frames[i]
        next_frame = frames[(i + 1) % num_frames]  # Переход от последнего к первому

        # Основной кадр с текстом
        final_frames.append(current.copy())
        durations.append(hold_duration)

        # Переход между current и next_frame
        for step in range(1, transition_steps):
            alpha = step / transition_steps
            blended = Image.blend(current, next_frame, alpha)
            final_frames.append(blended)
            durations.append(blend_duration)

    # Сохраняем как анимированный GIF
    final_frames[0].save(
        output_path,
        save_all=True,
        append_images=final_frames[1:],
        duration=durations,
        loop=0,
        optimize=False
    )

    logger.info(f"GIF-анимация успешно создана: {output_path}")
    return output_path

# --- Модифицированная часть main ---
async def main():
    print("DEBUG: --- Запуск функции main() ---")
    global city_to_process
    cities_to_publish = ["Пномпень", "Сиануквиль", "Сиемреап"]

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    accuweather_api_key = os.getenv("ACCUWEATHER_API_KEY")
    target_chat_id = os.getenv("TARGET_CHAT_ID")

    if not all([telegram_bot_token, target_chat_id]) or (not TEST_MODE and not accuweather_api_key):
        logger.error("ОШИБКА: Отсутствуют необходимые переменные окружения.")
        return

    bot = Bot(token=telegram_bot_token)
    if not os.path.exists(BACKGROUNDS_FOLDER):
        os.makedirs(BACKGROUNDS_FOLDER)

    frames = []

    for city in cities_to_publish:
        city_to_process = city
        logger.info(f"Получаю данные для {city}...")

        weather_data = PRESET_WEATHER_DATA.get(city) if TEST_MODE else None
        if not TEST_MODE:
            location_key = await get_location_key(city)
            weather_data = await get_current_weather(location_key) if location_key else None

        if weather_data:
            frame = create_weather_frame(city, weather_data)
            if frame:
                frames.append(frame)
        else:
            logger.warning(f"Нет погодных данных для {city}. Пропускаю.")

        await asyncio.sleep(0.5)

    gif_path = "weather_report.gif"
    gif_result = create_weather_gif(frames, gif_path)

    if gif_result and os.path.exists(gif_path):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(AD_BUTTON_TEXT, url=AD_BUTTON_URL),
             InlineKeyboardButton(NEWS_BUTTON_TEXT, url=NEWS_BUTTON_URL)]
        ])

        try:
            with open(gif_path, 'rb') as f:
                message = await bot.send_animation(
                    chat_id=target_chat_id,
                    animation=f,
                    caption=None,
                    reply_markup=keyboard
                )
                save_message_id(message.message_id)
                logger.info(f"GIF отправлен: {gif_path}")
        except Exception as e:
            logger.error(f"Ошибка при отправке GIF: {e}")
    else:
        await bot.send_message(chat_id=target_chat_id,
                               text="Не удалось создать анимацию погоды.",
                               parse_mode='HTML')

    # Очистка
    try:
        if os.path.exists(gif_path):
            os.remove(gif_path)
    except Exception as e:
        logger.error(f"Ошибка при удалении файла GIF: {e}")

    print("DEBUG: --- Завершение функции main() ---")

if __name__ == "__main__":
    asyncio.run(main())
