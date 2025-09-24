import logging
import requests
import asyncio
import os
import datetime
from typing import Dict, Any, List, Optional
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
import yaml
# НОВЫЕ ИМПОРТЫ для создания видео
import imageio
import numpy as np

# --- Базовые настройки ---
font_cache: Dict[int, ImageFont.FreeTypeFont] = {}
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Константы и конфигурация ---
OPENWEATHER_API_URL = "https://api.openweathermap.org/data/3.0/onecall"
VISUALCROSSING_API_URL = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
CITIES = {
    "Пномпень": {"lat": 11.5564, "lon": 104.9282},
    "Сиануквиль": {"lat": 10.6276, "lon": 103.5224},
    "Сиемреап": {"lat": 13.3639, "lon": 103.859}
}
WATERMARK_FILE = "watermark.png"
WATERMARK_SCALE_FACTOR = 0.5
AD_BUTTON_TEXT = "Новости 🇰🇭"
AD_BUTTON_URL = "https://t.me/cambodiacriminal"
NEWS_BUTTON_TEXT = "Попробуй! 🆕"
NEWS_BUTTON_URL = "https://bot.cambodiabank.ru"
BACKGROUNDS_FOLDER = "backgrounds2"
MESSAGE_IDS_FILE = "message_ids.yml"

# --- Функции получения данных (без изменений) ---
async def get_historical_records(lat: float, lon: float, api_key: str) -> Optional[Dict[str, float]]:
    url = f"{VISUALCROSSING_API_URL}{lat},{lon}/today"
    params = {'unitGroup': 'metric', 'key': api_key, 'include': 'normal,days', 'elements': 'tempmin,tempmax'}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if 'days' in data and data['days'] and 'normal' in data['days'][0]:
            normals = data['days'][0]['normal']
            if 'tempmin' in normals and len(normals['tempmin']) == 3 and 'tempmax' in normals and len(normals['tempmax']) == 3:
                return {"record_min": normals['tempmin'][0], "record_max": normals['tempmax'][2]}
        logger.warning(f"Не найдены исторические данные в ответе от Visual Crossing для {lat},{lon}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе исторических данных от Visual Crossing: {e}")
        return None

async def get_current_weather(coords: Dict[str, float], api_key: str) -> Optional[Dict]:
    params = {"lat": coords["lat"], "lon": coords["lon"], "appid": api_key, "units": "metric", "lang": "ru", "exclude": "minutely,hourly,daily,alerts"}
    try:
        response = requests.get(OPENWEATHER_API_URL, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе погоды через One Call API: {e}")
        return None

# --- Функции обработки изображений (без изменений) ---
def create_weather_frame(city_name: str, weather_data: Dict, historical_data: Optional[Dict[str, float]]) -> Optional[Image.Image]:
    background_path = get_random_background_image(city_name)
    if not background_path: return None
    try:
        img = Image.open(background_path).convert("RGB")
        target_width = 800
        w_percent = (target_width / float(img.size[0]))
        h_size = int((float(img.size[1]) * float(w_percent)))
        img = img.resize((target_width, h_size), Image.Resampling.LANCZOS)
        
        current_weather = weather_data['current']
        width, height = img.size
        draw = ImageDraw.Draw(img)

        temp = current_weather['temp']
        feels_like = current_weather['feels_like']
        weather_description = current_weather['weather'][0]['description'].capitalize()
        humidity = current_weather['humidity']
        wind_speed_ms = current_weather['wind_speed']
        wind_deg = current_weather['wind_deg']
        wind_direction_abbr = get_wind_direction_abbr(wind_deg)

        weather_text_lines = [
            f"Погода в г. {city_name}\n",
            f"Температура: {temp:.1f}°C (ощущ. {feels_like:.1f}°C)",
            f"{weather_description}", f"Влажность: {humidity}%",
            f"Ветер: {wind_direction_abbr}, {wind_speed_ms:.1f} м/с\n",
        ]
        if historical_data:
            record_min = historical_data.get('record_min')
            record_max = historical_data.get('record_max')
            if record_min is not None and record_max is not None:
                 weather_text_lines.append(f"Рекордный мин.: {record_min:.1f}°C")
                 weather_text_lines.append(f"Рекордный макс.: {record_max:.1f}°C")

        weather_text = "\n".join(weather_text_lines)
        plaque_width, padding, border_radius = int(width * 0.9), int(width * 0.04), int(width * 0.03)
        font_size = int(width / 22)
        font = get_font(font_size)
        text_bbox = draw.textbbox((0, 0), weather_text, font=font, spacing=10)
        text_width, text_height = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
        plaque_height = text_height + 2 * padding
        plaque_x1, plaque_y1 = (width - plaque_width) // 2, (height - plaque_height) // 2
        
        plaque_img = Image.new('RGBA', img.size, (0,0,0,0))
        plaque_draw = ImageDraw.Draw(plaque_img)
        round_rectangle(plaque_draw, (plaque_x1, plaque_y1, plaque_x1 + plaque_width, plaque_y1 + plaque_height), border_radius, (0, 0, 0, 160))
        img.paste(plaque_img, (0,0), plaque_img)
        
        draw = ImageDraw.Draw(img)
        text_x, text_y = plaque_x1 + (plaque_width - text_width) // 2, plaque_y1 + (plaque_height - text_height) // 2
        draw.multiline_text((text_x, text_y), weather_text, fill=(255, 255, 255), font=font, spacing=10, align="center")
        return img
    except Exception as e:
        logger.error(f"Ошибка при создании кадра для {city_name}: {e}")
        return None

# --- ИЗМЕНЕНО: Функция create_weather_gif заменена на create_weather_video ---
def create_weather_video(frames: List[Image.Image], output_path: str = "weather_report.mp4") -> str:
    if not frames:
        logger.error("Нет кадров для создания видео.")
        return ""

    # Настройки видео
    fps = 20  # Кадров в секунду. 20-25 дает плавную картинку
    hold_duration_sec = 3  # Сколько секунд показывать каждый слайд
    transition_steps = 15  # Количество кадров для перехода

    # Рассчитываем, сколько раз нужно продублировать кадр для удержания
    hold_frames_count = fps * hold_duration_sec

    try:
        with imageio.get_writer(output_path, fps=fps, codec='libx264', quality=8, pixelformat='yuv420p') as writer:
            num_cities = len(frames)
            for i in range(num_cities):
                current_pil_frame = frames[i]
                next_pil_frame = frames[(i + 1) % num_cities]

                # Добавляем основной кадр с вотермаркой (удерживаем на экране)
                main_frame_with_watermark = add_watermark(current_pil_frame.copy())
                np_main_frame = np.array(main_frame_with_watermark)
                for _ in range(hold_frames_count):
                    writer.append_data(np_main_frame)

                # Добавляем кадры перехода
                for step in range(1, transition_steps + 1):
                    alpha = step / transition_steps
                    blended_frame = Image.blend(current_pil_frame, next_pil_frame, alpha)
                    blended_with_watermark = add_watermark(blended_frame)
                    np_blended_frame = np.array(blended_with_watermark)
                    writer.append_data(np_blended_frame)
        
        logger.info(f"Видеофайл MP4 успешно создан: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Ошибка при создании MP4 файла: {e}")
        return ""

# --- Вспомогательные функции (без изменений) ---
def get_wind_direction_abbr(deg: int) -> str:
    directions = ["С", "ССВ", "СВ", "ВСВ", "В", "ВЮВ", "ЮВ", "ЮЮВ", "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ", "З", "ЗСЗ", "СЗ", "ССЗ"]
    return directions[round(deg / 22.5) % 16]
def get_random_background_image(city_name: str) -> str | None:
    city_folder = os.path.join(BACKGROUNDS_FOLDER, city_name)
    if os.path.isdir(city_folder):
        import random
        image_files = [f for f in os.listdir(city_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if image_files: return os.path.join(city_folder, random.choice(image_files))
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
    if font_size in font_cache: return font_cache[font_size]
    try: font = ImageFont.truetype("arial.ttf", font_size)
    except IOError: font = ImageFont.load_default()
    font_cache[font_size] = font
    return font
def add_watermark(base_img: Image.Image) -> Image.Image:
    try:
        base_img = base_img.convert("RGBA")
        if not os.path.exists(WATERMARK_FILE): return base_img.convert("RGB")
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
def save_message_id(message_id: int):
    messages = []
    if os.path.exists(MESSAGE_IDS_FILE):
        with open(MESSAGE_IDS_FILE, 'r') as f:
            try:
                loaded_data = yaml.safe_load(f)
                if isinstance(loaded_data, list): messages = loaded_data
            except yaml.YAMLError: pass
    messages.append({'message_id': message_id, 'sent_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    with open(MESSAGE_IDS_FILE, 'w') as f: yaml.dump(messages, f)

# --- Основной исполняемый блок ---
async def main():
    logger.info("--- Запуск основного процесса ---")
    openweather_api_key = os.getenv("OPENWEATHER_API_KEY")
    visualcrossing_api_key = os.getenv("VISUALCROSSING_API_KEY")
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    target_chat_id = os.getenv("TARGET_CHAT_ID")

    if not all([telegram_bot_token, target_chat_id, openweather_api_key, visualcrossing_api_key]):
        logger.error("ОШИБКА: Отсутствуют необходимые переменные окружения.")
        return

    bot = Bot(token=telegram_bot_token)
    frames = []
    for city_name, coords in CITIES.items():
        logger.info(f"Обработка города: {city_name}...")
        weather_data, historical_data = await asyncio.gather(
            get_current_weather(coords, openweather_api_key),
            get_historical_records(coords['lat'], coords['lon'], visualcrossing_api_key)
        )
        if weather_data:
            frame = create_weather_frame(city_name, weather_data, historical_data)
            if frame: frames.append(frame)
        else:
            logger.warning(f"Нет погодных данных для {city_name}. Пропускаю.")
        await asyncio.sleep(0.5)

    if not frames:
        logger.error("Не удалось создать ни одного кадра. Отправка отменена.")
        return
    
    # ИЗМЕНЕНО: Создаем и отправляем видео вместо GIF
    video_path = "weather_report.mp4"
    create_weather_video(frames, video_path)
    
    if os.path.exists(video_path):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(AD_BUTTON_TEXT, url=AD_BUTTON_URL), InlineKeyboardButton(NEWS_BUTTON_TEXT, url=NEWS_BUTTON_URL)]])
        try:
            with open(video_path, 'rb') as video_file:
                # ИСПОЛЬЗУЕМ bot.send_video
                message = await bot.send_video(
                    chat_id=target_chat_id,
                    video=video_file,
                    supports_streaming=True, # Полезный параметр для видео
                    disable_notification=True
                )
            save_message_id(message.message_id)
            logger.info(f"Видео MP4 успешно отправлено в чат {target_chat_id}.")
        except Exception as e:
            logger.error(f"Ошибка при отправке MP4: {e}")
        finally:
            if os.path.exists(video_path): os.remove(video_path)
    else:
        logger.error("Файл MP4 не был создан.")
        
    logger.info("--- Завершение работы ---")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
