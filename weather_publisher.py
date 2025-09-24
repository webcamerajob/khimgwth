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
# ИЗМЕНЕНО: URL для One Call API 3.0
ONE_CALL_API_URL = "https://api.openweathermap.org/data/3.0/onecall"

# НОВОЕ: Координаты городов, так как Geocoding API недоступен
CITIES = {
    "Пномпень": {"lat": 11.5564, "lon": 104.9282},
    "Сиануквиль": {"lat": 10.6276, "lon": 103.5224},
    "Сиемреап": {"lat": 13.3639, "lon": 103.859}
}

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
        'current': {
            'temp': 32.5, 'feels_like': 38.0, 'humidity': 65,
            'weather': [{'description': 'ясно'}],
            'wind_speed': 4.22, 'wind_deg': 135
        }
    },
    # ... (остальные города для теста можно добавить по аналогии)
}

# --- Функции ---

def get_wind_direction_abbr(deg: int) -> str:
    """Преобразует градусы в аббревиатуру направления ветра."""
    directions = ["С", "ССВ", "СВ", "ВСВ", "В", "ВЮВ", "ЮВ", "ЮЮВ", "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ", "З", "ЗСЗ", "СЗ", "ССЗ"]
    index = round(deg / 22.5) % 16
    return directions[index]

# ИЗМЕНЕНО: Функция теперь использует One Call API
async def get_current_weather(coords: Dict[str, float], api_key: str, city_name_for_test: str) -> Dict | None:
    """Получает текущие погодные условия по координатам через One Call API."""
    if TEST_MODE:
        logger.info(f"Используются предустановленные данные для: {city_name_for_test}")
        return PRESET_WEATHER_DATA.get(city_name_for_test)

    params = {
        "lat": coords["lat"],
        "lon": coords["lon"],
        "appid": api_key,
        "units": "metric",
        "lang": "ru",
        "exclude": "minutely,hourly,daily,alerts" # Запрашиваем только текущую погоду
    }
    try:
        response = requests.get(ONE_CALL_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Получены данные о погоде для координат: {coords['lat']}, {coords['lon']}")
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе погоды через One Call API: {e}")
        return None

# ИЗМЕНЕНО: Парсинг данных адаптирован под ответ от One Call API
# ИЗМЕНЕНО: Функция теперь принимает и отображает исторические данные
def create_weather_frame(city_name: str, weather_data: Dict, historical_data: Optional[Dict[str, float]]) -> Optional[Image.Image]:
    background_path = get_random_background_image(city_name)
    if not background_path:
        return None

    try:
        img = Image.open(background_path).convert("RGB")

        # --- ИЗМЕНЕНИЕ РАЗРЕШЕНИЯ ---
        target_width = 600  # <-- Изменено на 600px ✅
        w_percent = (target_width / float(img.size[0]))
        h_size = int((float(img.size[1]) * float(w_percent)))
        img = img.resize((target_width, h_size), Image.Resampling.LANCZOS)
        # --- КОНЕЦ БЛОКА ---

        current_weather = weather_data['current']
        width, height = img.size # Обновляем размеры после resize
        draw = ImageDraw.Draw(img)

        temp = current_weather['temp']
        feels_like = current_weather['feels_like']
        weather_description = current_weather['weather'][0]['description'].capitalize()
        humidity = current_weather['humidity']
        wind_speed_ms = current_weather['wind_speed']
        wind_speed_kmh = wind_speed_ms * 3.6
        wind_deg = current_weather['wind_deg']
        wind_direction_abbr = get_wind_direction_abbr(wind_deg)

        weather_text_lines = [
            f"Погода в г. {city_name}\n",
            f"Температура: {temp:.1f}°C (ощущ. {feels_like:.1f}°C)",
            f"{weather_description}",
            f"Влажность: {humidity}%",
            f"Ветер: {wind_direction_abbr}, {wind_speed_kmh:.1f} км/ч\n",
        ]
        
        if historical_data:
            hist_min = historical_data.get('min')
            hist_max = historical_data.get('max')
            if hist_min is not None and hist_max is not None:
                 weather_text_lines.append(f"Исторический мин.: {hist_min:.1f}°C")
                 weather_text_lines.append(f"Исторический макс.: {hist_max:.1f}°C")

        weather_text = "\n".join(weather_text_lines)
        
        plaque_width = int(width * 0.9)
        padding = int(width * 0.04)
        border_radius = int(width * 0.03)
        font_size = int(width / 22)
        font = get_font(font_size)
        text_bbox = draw.textbbox((0, 0), weather_text, font=font, spacing=10)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        plaque_height = text_height + 2 * padding
        plaque_x1 = (width - plaque_width) // 2
        plaque_y1 = (height - plaque_height) // 2
        plaque_x2 = plaque_x1 + plaque_width
        plaque_y2 = plaque_y1 + plaque_height
        plaque_img = Image.new('RGBA', img.size, (0,0,0,0))
        plaque_draw = ImageDraw.Draw(plaque_img)
        round_rectangle(plaque_draw, (plaque_x1, plaque_y1, plaque_x2, plaque_y2), border_radius, (0, 0, 0, 160))
        img.paste(plaque_img, (0,0), plaque_img)
        draw = ImageDraw.Draw(img)
        text_x = plaque_x1 + (plaque_width - text_width) // 2
        text_y = plaque_y1 + (plaque_height - text_height) // 2
        draw.multiline_text((text_x, text_y), weather_text, fill=(255, 255, 255), font=font, spacing=10, align="center")

        return img

    except Exception as e:
        logger.error(f"Ошибка при создании кадра для {city_name}: {e}")
        return None

# --- Основной блок и вспомогательные функции (без изменений) ---

def get_random_background_image(city_name: str) -> str | None:
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
    if font_size in font_cache:
        return font_cache[font_size]
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
    font_cache[font_size] = font
    return font

def add_watermark(base_img: Image.Image) -> Image.Image:
    try:
        base_img = base_img.convert("RGBA")
        if not os.path.exists(WATERMARK_FILE):
            return base_img.convert("RGB")
        watermark_img = Image.open(WATERMARK_FILE).convert("RGBA")
        base_width, base_height = base_img.size
        target_width = int(base_width * WATERMARK_SCALE_FACTOR)
        w_percent = (target_width / float(watermark_img.size[0]))
        h_size = int((float(watermark_img.size[1]) * float(w_percent)))
        watermark_img = watermark_img.resize((target_width, h_size), Image.Resampling.LANCZOS)
        padding = int(base_width * 0.02)
        position = (base_width - watermark_img.width - padding, padding)
        transparent = Image.new('RGBA', base_img.size, (0,0,0,0))
        transparent.paste(base_img, (0,0))
        transparent.paste(watermark_img, position, mask=watermark_img)
        return transparent.convert("RGB")
    except Exception as e:
        logger.error(f"Ошибка при добавлении вотермарки: {e}")
        return base_img.convert("RGB")

def create_weather_gif(frames: List[Image.Image], output_path: str = "output/weather.gif") -> str:
    if not frames:
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
        final_frames.append(add_watermark(current_frame.copy()))
        durations.append(hold_duration)
        for step in range(1, transition_steps + 1):
            alpha = step / transition_steps
            blended = Image.blend(current_frame, next_frame, alpha)
            final_frames.append(add_watermark(blended))
            durations.append(blend_duration)
    final_frames[0].save(output_path, save_all=True, append_images=final_frames[1:], duration=durations, loop=0, optimize=True, disposal=2)
    logger.info(f"GIF-анимация успешно создана: {output_path}")
    return output_path

def save_message_id(message_id: int):
    messages = []
    if os.path.exists(MESSAGE_IDS_FILE):
        with open(MESSAGE_IDS_FILE, 'r') as f:
            try:
                loaded_data = yaml.safe_load(f)
                if isinstance(loaded_data, list):
                    messages = loaded_data
            except yaml.YAMLError:
                pass
    messages.append({'message_id': message_id, 'sent_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    with open(MESSAGE_IDS_FILE, 'w') as f:
        yaml.dump(messages, f)

# ИЗМЕНЕНО: Основной цикл теперь работает с новым словарём CITIES
async def main():
    logger.info("--- Запуск основного процесса ---")
    openweather_api_key = os.getenv("OPENWEATHER_API_KEY")
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    target_chat_id = os.getenv("TARGET_CHAT_ID")

    if not all([telegram_bot_token, target_chat_id, openweather_api_key]):
        logger.error("ОШИБКА: Отсутствуют необходимые переменные окружения.")
        return

    bot = Bot(token=telegram_bot_token)
    frames = []

    for city_name, coords in CITIES.items():
        logger.info(f"Обработка города: {city_name}...")
        weather_data = await get_current_weather(coords, openweather_api_key, city_name)

        if weather_data:
            frame = create_weather_frame(city_name, weather_data)
            if frame:
                frames.append(frame)
        else:
            logger.warning(f"Нет погодных данных для {city_name}. Пропускаю.")
        await asyncio.sleep(1)

    if not frames:
        logger.error("Не удалось создать ни одного кадра. Отправка отменена.")
        return

    gif_path = "weather_report.gif"
    create_weather_gif(frames, gif_path)

    if os.path.exists(gif_path):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(AD_BUTTON_TEXT, url=AD_BUTTON_URL), InlineKeyboardButton(NEWS_BUTTON_TEXT, url=NEWS_BUTTON_URL)]])
        try:
            with open(gif_path, 'rb') as animation_file:
                message = await bot.send_animation(chat_id=target_chat_id, animation=animation_file, reply_markup=keyboard, disable_notification=True)
            save_message_id(message.message_id)
            logger.info(f"GIF успешно отправлен в чат {target_chat_id}.")
        except Exception as e:
            logger.error(f"Ошибка при отправке GIF: {e}")
        finally:
            if os.path.exists(gif_path):
                os.remove(gif_path)
    else:
        logger.error("Файл GIF не был создан.")

    logger.info("--- Завершение работы ---")

if __name__ == "__main__":
    asyncio.run(main())
