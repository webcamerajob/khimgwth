import logging
import requests
import asyncio
import os
import datetime
from typing import Dict, Any, List
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
import yaml

font_cache: Dict[int, ImageFont.FreeTypeFont] = {}

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Настройки и Константы ---
OPENWEATHER_BASE_URL = "http://api.openweathermap.org/"

# Переключатель тестового режима
TEST_MODE = os.getenv("TEST_MODE", "False").lower() == "true"

# Настройки вотермарки
WATERMARK_FILE = "watermark.png"
WATERMARK_SCALE_FACTOR = 0.5

# Настройки кнопок
AD_BUTTON_TEXT = "Новости 🇰🇭"
AD_BUTTON_URL = "https://t.me/cambodiacriminal"
NEWS_BUTTON_TEXT = "Попробуй! 🆕"
NEWS_BUTTON_URL = "https://bot.cambodiabank.ru"

# Путь к папке с фонами
BACKGROUNDS_FOLDER = "backgrounds2"

# Файл для сохранения ID сообщений
MESSAGE_IDS_FILE = "message_ids.yml"

# --- Предустановленные данные о погоде (для TEST_MODE) ---
PRESET_WEATHER_DATA = {
    "Пномпень": {
        'main': {'temp': 32.5, 'feels_like': 38.0, 'humidity': 65, 'pressure': 1009.5},
        'weather': [{'description': 'ясно'}],
        'wind': {'speed': 4.22, 'deg': 135} # Speed in m/s, deg for direction
    },
    "Сиануквиль": {
        'main': {'temp': 28.1, 'feels_like': 31.5, 'humidity': 80, 'pressure': 1010.1},
        'weather': [{'description': 'переменная облачность'}],
        'wind': {'speed': 3.0, 'deg': 270}
    },
    "Сиемреап": {
        'main': {'temp': 30.0, 'feels_like': 35.5, 'humidity': 75, 'pressure': 1008.9},
        'weather': [{'description': 'небольшой дождь'}],
        'wind': {'speed': 2.08, 'deg': 0}
    },
}

# --- Функция для получения аббревиатуры направления ветра ---
def get_wind_direction_abbr(deg: int) -> str:
    """Преобразует градусы в аббревиатуру направления ветра."""
    directions = ["С", "ССВ", "СВ", "ВСВ", "В", "ВЮВ", "ЮВ", "ЮЮВ", "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ", "З", "ЗСЗ", "СЗ", "ССЗ"]
    index = round(deg / 22.5) % 16
    return directions[index]

async def get_coordinates(city_name: str, api_key: str) -> Dict[str, float] | None:
    """Получает координаты (широту и долготу) для города."""
    if TEST_MODE:
        return {"lat": 0, "lon": 0} # Заглушка для теста

    url = f"{OPENWEATHER_BASE_URL}geo/1.0/direct"
    params = {
        "q": city_name,
        "limit": 1,
        "appid": api_key
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data:
            logger.info(f"Координаты для {city_name}: {data[0]['lat']}, {data[0]['lon']}")
            return {"lat": data[0]["lat"], "lon": data[0]["lon"]}
        else:
            logger.warning(f"Не удалось найти координаты для: {city_name}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе координат для {city_name}: {e}")
        return None

async def get_current_weather(coords: Dict[str, float], api_key: str, city_name_for_test: str) -> Dict | None:
    """Получает текущие погодные условия по координатам."""
    if TEST_MODE:
        logger.info(f"Используются предустановленные данные для: {city_name_for_test}")
        return PRESET_WEATHER_DATA.get(city_name_for_test)

    if not coords:
        return None

    url = f"{OPENWEATHER_BASE_URL}data/2.5/weather"
    params = {
        "lat": coords["lat"],
        "lon": coords["lon"],
        "appid": api_key,
        "units": "metric",
        "lang": "ru"
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Получены данные о погоде для координат: {coords['lat']}, {coords['lon']}")
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе погоды: {e}")
        return None

def get_random_background_image(city_name: str) -> str | None:
    """Возвращает случайный путь к файлу изображения фона для заданного города."""
    city_folder = os.path.join(BACKGROUNDS_FOLDER, city_name)
    if os.path.isdir(city_folder):
        import random
        image_files = [f for f in os.listdir(city_folder) if os.path.isfile(os.path.join(city_folder, f)) and f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if image_files:
            return os.path.join(city_folder, random.choice(image_files))
    logger.warning(f"Папка с фонами не найдена или пуста для города: {city_name}")
    return None

def round_rectangle(draw, xy, radius, fill):
    x1, y1, x2, y2 = xy
    draw.rectangle((x1 + radius, y1, x2 - radius, y2), fill=fill)
    draw.rectangle((x1, y1 + radius, x2, y2 - radius), fill=fill)
    draw.pieslice((x1, y1, x1 + 2 * radius, y1 + 2 * radius), 180, 270, fill=fill)
    draw.pieslice((x2 - 2 * radius, y1, x2, y1 + 2 * radius), 270, 360, fill=fill)
    draw.pieslice((x1, y2 - 2 * radius, x1 + 2 * radius, y2), 90, 180, fill=fill)
    draw.pieslice((x2 - 2 * radius, y2 - 2 * radius, x2, y2), 0, 90, fill=fill)


def get_font(font_size: int) -> ImageFont.FreeTypeFont:
    """Возвращает шрифт нужного размера из кэша или загружает его."""
    if font_size in font_cache:
        return font_cache[font_size]
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
        logger.info(f"Шрифт 'arial.ttf' загружен (размер {font_size}).")
    except IOError:
        logger.warning("Шрифт 'arial.ttf' не найден. Используется стандартный шрифт.")
        font = ImageFont.load_default()
    font_cache[font_size] = font
    return font

def add_watermark(base_img: Image.Image) -> Image.Image:
    """Накладывает вотермарку на изображение."""
    try:
        base_img = base_img.convert("RGBA")
        if not os.path.exists(WATERMARK_FILE):
            logger.warning(f"Файл вотермарки не найден: {WATERMARK_FILE}. Пропускаю.")
            return base_img.convert("RGB")

        watermark_img = Image.open(WATERMARK_FILE).convert("RGBA")
        base_width, base_height = base_img.size

        # Масштабирование
        target_width = int(base_width * WATERMARK_SCALE_FACTOR)
        w_percent = (target_width / float(watermark_img.size[0]))
        h_size = int((float(watermark_img.size[1]) * float(w_percent)))
        watermark_img = watermark_img.resize((target_width, h_size), Image.Resampling.LANCZOS)

        # Позиционирование
        padding = int(base_width * 0.02)
        position = (base_width - watermark_img.width - padding, padding)

        # Наложение
        transparent = Image.new('RGBA', base_img.size, (0,0,0,0))
        transparent.paste(base_img, (0,0))
        transparent.paste(watermark_img, position, mask=watermark_img)
        return transparent.convert("RGB")
    except Exception as e:
        logger.error(f"Ошибка при добавлении вотермарки: {e}")
        return base_img.convert("RGB")


def create_weather_frame(city_name: str, weather_data: Dict) -> Image.Image | None:
    """Создает кадр изображения с текстом погоды."""
    background_path = get_random_background_image(city_name)
    if not background_path:
        return None

    try:
        img = Image.open(background_path).convert("RGB")
        width, height = img.size
        draw = ImageDraw.Draw(img)

        # Адаптация под структуру OpenWeatherMap
        temp = weather_data['main']['temp']
        feels_like = weather_data['main']['feels_like']
        weather_description = weather_data['weather'][0]['description'].capitalize()
        humidity = weather_data['main']['humidity']
        wind_speed_ms = weather_data['wind']['speed']
        wind_speed_kmh = wind_speed_ms * 3.6 # Конвертация м/с в км/ч
        wind_deg = weather_data['wind']['deg']
        wind_direction_abbr = get_wind_direction_abbr(wind_deg)

        weather_text_lines = [
            f"Погода в г. {city_name}\n",
            f"Температура: {temp:.1f}°C",
            f"Ощущается как: {feels_like:.1f}°C",
            f"{weather_description}",
            f"Влажность: {humidity}%",
            f"Ветер: {wind_direction_abbr}, {wind_speed_kmh:.1f} км/ч",
        ]
        weather_text = "\n".join(weather_text_lines)

        plaque_width = int(width * 0.9)
        padding = int(width * 0.04)
        border_radius = int(width * 0.03)
        font_size = int(width / 20) # Адаптивный размер шрифта
        font = get_font(font_size)

        # Вычисляем размеры текстового блока
        text_bbox = draw.textbbox((0, 0), weather_text, font=font, spacing=10)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        plaque_height = text_height + 2 * padding

        # Координаты плашки
        plaque_x1 = (width - plaque_width) // 2
        plaque_y1 = (height - plaque_height) // 2
        plaque_x2 = plaque_x1 + plaque_width
        plaque_y2 = plaque_y1 + plaque_height

        # Создаем полупрозрачную плашку
        plaque_img = Image.new('RGBA', img.size, (0,0,0,0))
        plaque_draw = ImageDraw.Draw(plaque_img)
        round_rectangle(plaque_draw, (plaque_x1, plaque_y1, plaque_x2, plaque_y2), border_radius, (0, 0, 0, 160))

        # Наложение плашки на фон
        img.paste(plaque_img, (0,0), plaque_img)
        draw = ImageDraw.Draw(img) # Пересоздаем draw для основного изображения

        # Координаты текста
        text_x = plaque_x1 + (plaque_width - text_width) // 2
        text_y = plaque_y1 + (plaque_height - text_height) // 2
        draw.multiline_text((text_x, text_y), weather_text, fill=(255, 255, 255), font=font, spacing=10, align="center")

        return img

    except Exception as e:
        logger.error(f"Ошибка при создании кадра для {city_name}: {e}")
        return None

def create_weather_gif(frames: List[Image.Image], output_path: str = "output/weather.gif") -> str:
    """Создает GIF-анимацию из кадров."""
    if not frames:
        logger.error("Нет кадров для создания GIF.")
        return ""

    final_frames = []
    durations = []
    transition_steps = 15
    hold_duration = 3000
    blend_duration = 80
    num_frames = len(frames)

    for i in range(num_frames):
        current_frame = frames[i]
        next_frame = frames[(i + 1) % num_frames]

        # Добавляем основной кадр с вотермаркой
        final_frames.append(add_watermark(current_frame.copy()))
        durations.append(hold_duration)

        # Создаем кадры перехода
        for step in range(1, transition_steps + 1):
            alpha = step / transition_steps
            blended = Image.blend(current_frame, next_frame, alpha)
            final_frames.append(add_watermark(blended))
            durations.append(blend_duration)

    # Сохраняем GIF
    final_frames[0].save(
        output_path,
        save_all=True,
        append_images=final_frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2
    )
    logger.info(f"GIF-анимация успешно создана: {output_path}")
    return output_path

def save_message_id(message_id: int):
    """Сохраняет ID отправленного сообщения в YAML файл."""
    messages = []
    if os.path.exists(MESSAGE_IDS_FILE):
        with open(MESSAGE_IDS_FILE, 'r') as f:
            try:
                loaded_data = yaml.safe_load(f)
                if isinstance(loaded_data, list):
                    messages = loaded_data
            except yaml.YAMLError as e:
                logger.error(f"Ошибка парсинга {MESSAGE_IDS_FILE}: {e}")

    messages.append({
        'message_id': message_id,
        'sent_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
    })

    try:
        with open(MESSAGE_IDS_FILE, 'w') as f:
            yaml.dump(messages, f)
        logger.info(f"ID сообщения {message_id} сохранено в {MESSAGE_IDS_FILE}.")
    except Exception as e:
        logger.error(f"Ошибка сохранения ID сообщения: {e}")

async def main():
    logger.info("--- Запуск основного процесса ---")
    cities_to_publish = ["Пномпень", "Сиануквиль", "Сиемреап"]

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    openweather_api_key = os.getenv("OPENWEATHER_API_KEY") # <-- Новая переменная
    target_chat_id = os.getenv("TARGET_CHAT_ID")

    if not all([telegram_bot_token, target_chat_id]) or (not TEST_MODE and not openweather_api_key):
        logger.error("ОШИБКА: Отсутствуют необходимые переменные окружения (TELEGRAM_BOT_TOKEN, TARGET_CHAT_ID, OPENWEATHER_API_KEY).")
        return

    bot = Bot(token=telegram_bot_token)
    if not os.path.exists(BACKGROUNDS_FOLDER):
        os.makedirs(BACKGROUNDS_FOLDER)

    frames = []
    for city in cities_to_publish:
        logger.info(f"Обработка города: {city}...")
        coords = await get_coordinates(city, openweather_api_key)
        weather_data = await get_current_weather(coords, openweather_api_key, city)

        if weather_data:
            frame = create_weather_frame(city, weather_data)
            if frame:
                frames.append(frame)
        else:
            logger.warning(f"Нет погодных данных для {city}. Пропускаю.")
        await asyncio.sleep(1) # Задержка между запросами к API

    if not frames:
        logger.error("Не удалось создать ни одного кадра. Отправка отменена.")
        return

    gif_path = "weather_report.gif"
    create_weather_gif(frames, gif_path)

    if os.path.exists(gif_path):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(AD_BUTTON_TEXT, url=AD_BUTTON_URL),
             InlineKeyboardButton(NEWS_BUTTON_TEXT, url=NEWS_BUTTON_URL)]
        ])
        try:
            with open(gif_path, 'rb') as animation_file:
                message = await bot.send_animation(
                    chat_id=target_chat_id,
                    animation=animation_file,
                    reply_markup=keyboard,
                    disable_notification=True
                )
            save_message_id(message.message_id)
            logger.info(f"GIF успешно отправлен в чат {target_chat_id}.")
        except Exception as e:
            logger.error(f"Ошибка при отправке GIF: {e}")
        finally:
            os.remove(gif_path) # Удаляем файл после отправки
    else:
        logger.error("Файл GIF не был создан.")

    logger.info("--- Завершение работы ---")

if __name__ == "__main__":
    asyncio.run(main())
