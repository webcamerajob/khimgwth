import logging
import requests
import asyncio
import os
import datetime
from typing import Dict, Any, List, Optional
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest
import yaml
import imageio
import numpy as np

# --- Базовые настройки ---
font_cache: Dict[int, ImageFont.FreeTypeFont] = {}
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Константы и конфигурация ---
OPENWEATHER_API_URL = "https://api.openweathermap.org/data/3.0/onecall"
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
DAY_ABBREVIATIONS = {0: 'пн', 1: 'вт', 2: 'ср', 3: 'чт', 4: 'пт', 5: 'сб', 6: 'вс'}

# --- Функции ---

async def delete_old_messages(bot: Bot, chat_id: str):
    if not os.path.exists(MESSAGE_IDS_FILE): return
    try:
        with open(MESSAGE_IDS_FILE, 'r') as f:
            messages_to_delete = yaml.safe_load(f)
        if not messages_to_delete or not isinstance(messages_to_delete, list): return
        for msg_info in messages_to_delete:
            if message_id := msg_info.get('message_id'):
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=message_id)
                    logger.info(f"Сообщение {message_id} удалено.")
                except BadRequest as e:
                    if "message to delete not found" in str(e).lower() or "message can't be deleted" in str(e).lower():
                        logger.warning(f"Не удалось удалить {message_id} (уже удалено).")
                    else: raise e
                await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"Ошибка при удалении: {e}")

async def get_current_weather(coords: Dict[str, float], api_key: str) -> Optional[Dict]:
    params = {"lat": coords["lat"], "lon": coords["lon"], "appid": api_key, "units": "metric", "lang": "ru", "exclude": "minutely,alerts"}
    try:
        response = requests.get(OPENWEATHER_API_URL, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе погоды: {e}")
        return None

def format_precipitation_forecast(weather_data: Dict) -> List[str]:
    try:
        hourly = weather_data.get('hourly', [])
        offset = weather_data.get('timezone_offset', 0)
        current_ts = weather_data.get('current', {}).get('dt')
        if not hourly or not current_ts: return ["Осадков не ожидается"]

        rainy_hours_data = []
        for hour in hourly[:48]:
            if hour.get('dt', 0) > current_ts and hour.get('pop', 0) > 0.35:
                rainy_hours_data.append(hour)

        if not rainy_hours_data: return ["Осадков не ожидается"]

        intervals, i = [], 0
        while i < len(rainy_hours_data):
            start_hour_data = rainy_hours_data[i]
            end_hour_data = start_hour_data
            
            while i + 1 < len(rainy_hours_data) and rainy_hours_data[i+1]['dt'] == end_hour_data['dt'] + 3600:
                end_hour_data = rainy_hours_data[i+1]
                i += 1
            intervals.append((start_hour_data, end_hour_data))
            i += 1
        
        output_lines = []
        for start_hour, end_hour in intervals[:2]:
            start_dt = datetime.datetime.fromtimestamp(start_hour['dt'], tz=datetime.timezone.utc)
            end_dt = datetime.datetime.fromtimestamp(end_hour['dt'], tz=datetime.timezone.utc)
            
            max_rain_volume = 0
            intensity_description = "Дождь"
            
            interval_hours = [h for h in hourly if start_hour['dt'] <= h['dt'] <= end_hour['dt']]
            for hour in interval_hours:
                rain_volume = hour.get('rain', {}).get('1h', 0)
                if rain_volume > max_rain_volume:
                    max_rain_volume = rain_volume
                    intensity_description = hour.get('weather', [{}])[0].get('description', 'Дождь').capitalize()

            local_start = start_dt + datetime.timedelta(seconds=offset)
            local_end_display = end_dt + datetime.timedelta(hours=1) + datetime.timedelta(seconds=offset)

            start_day_abbr = DAY_ABBREVIATIONS[local_start.weekday()]
            end_day_abbr = DAY_ABBREVIATIONS[local_end_display.weekday()]

            if local_start.day == local_end_display.day or local_end_display.strftime('%H:%M') == '00:00':
                 if local_end_display.strftime('%H:%M') == '00:00':
                     end_time_str = "24:00"
                 else:
                     end_time_str = local_end_display.strftime('%H:%M')
                 output_lines.append(f"• {start_day_abbr}, {local_start.strftime('%H:%M')} - {end_time_str} ({intensity_description})")
            else:
                output_lines.append(f"• {start_day_abbr}, {local_start.strftime('%H:%M')} - {end_day_abbr}, {local_end_display.strftime('%H:%M')} ({intensity_description})")
        
        return output_lines

    except Exception as e:
        logger.error(f"Ошибка при форматировании прогноза: {e}")
        return ["Прогноз недоступен"]


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    lines, words = [], text.split()
    if not words: return ""
    current_line = words[0]
    for word in words[1:]:
        if font.getlength(current_line + " " + word) <= max_width:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    return "\n".join(lines)

def create_weather_frame(city_name: str, weather_data: Dict, precipitation_forecast_lines: List[str]) -> Optional[Image.Image]:
    background_path = get_random_background_image(city_name)
    if not background_path: return None
    try:
        img = Image.open(background_path).convert("RGB")
        target_width = 800
        w_percent = (target_width / float(img.size[0]))
        h_size = int((float(img.size[1]) * float(w_percent)))
        img = img.resize((target_width, h_size), Image.Resampling.LANCZOS)
        
        current = weather_data['current']
        width, height = img.size
        draw = ImageDraw.Draw(img)
        
        plaque_width, padding, border_radius = int(width * 0.9), int(width * 0.04), int(width * 0.03)
        font_size = int(width / 22)
        font = get_font(font_size)
        
        weather_description_and_humidity = f"{current['weather'][0]['description'].capitalize()}, влажность: {current['humidity']}%"

        main_info_lines = [
            f"Погода в г. {city_name}\n",
            f"Температура: {current['temp']:.1f}°C (ощущ. {current['feels_like']:.1f}°C)",
            weather_description_and_humidity,
            f"Ветер: {get_wind_direction_abbr(current['wind_deg'])}, {current['wind_speed']:.1f} м/с",
        ]
        
        final_forecast_lines = []
        for line in precipitation_forecast_lines:
            wrapped_line = wrap_text(line, font, plaque_width - padding * 2)
            final_forecast_lines.append(wrapped_line)

        text_lines = main_info_lines + ["\nПрогноз осадков:"] + final_forecast_lines
        weather_text = "\n".join(text_lines)
        
        bbox = draw.textbbox((0, 0), weather_text, font=font, spacing=10)
        text_h = bbox[3] - bbox[1]
        plaque_h = text_h + 2 * padding
        
        plaque_x = (width - plaque_width) // 2
        plaque_y = height - plaque_h - padding
        
        if plaque_y < padding:
            plaque_y = padding

        plaque_img = Image.new('RGBA', img.size, (0,0,0,0))
        plaque_draw = ImageDraw.Draw(plaque_img)
        round_rectangle(plaque_draw, (plaque_x, plaque_y, plaque_x + plaque_width, plaque_y + plaque_h), border_radius, (0, 0, 0, 160))
        img.paste(plaque_img, (0,0), plaque_img)
        
        draw = ImageDraw.Draw(img)
        text_bbox_final = draw.textbbox((plaque_x, plaque_y), weather_text, font=font, spacing=10)
        text_w = text_bbox_final[2] - text_bbox_final[0]
        text_x = plaque_x + (plaque_width - text_w) // 2
        draw.multiline_text((text_x, plaque_y + padding), weather_text, fill=(255, 255, 255), font=font, spacing=10, align="center")
        
        return img
    except Exception as e:
        logger.error(f"Ошибка при создании кадра для {city_name}: {e}")
        return None

def create_weather_video(frames: List[Image.Image], output_path: str = "weather_report.mp4") -> str:
    if not frames: return ""
    fps, hold_sec, steps = 20, 3, 15
    hold_frames = fps * hold_sec
    try:
        params = {'fps': fps, 'codec': 'libx264', 'quality': 8, 'pixelformat': 'yuv420p', 'output_params': ['-an']}
        with imageio.get_writer(output_path, **params) as writer:
            for i in range(len(frames)):
                current, nxt = frames[i], frames[(i + 1) % len(frames)]
                main_frame = np.array(add_watermark(current.copy()))
                for _ in range(hold_frames): writer.append_data(main_frame)
                for step in range(1, steps + 1):
                    blended = np.array(add_watermark(Image.blend(current, nxt, alpha=step/steps)))
                    writer.append_data(blended)
        logger.info(f"Видео MP4 создано: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Ошибка при создании MP4: {e}")
        return ""

def save_message_id(message_id: int):
    new_message = [{'message_id': message_id, 'sent_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}]
    with open(MESSAGE_IDS_FILE, 'w') as f: yaml.dump(new_message, f)

# --- Вспомогательные функции ---
def get_wind_direction_abbr(deg: int) -> str:
    return ["С", "ССВ", "СВ", "ВСВ", "В", "ВЮВ", "ЮВ", "ЮЮВ", "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ", "З", "ЗСЗ", "СЗ", "ССЗ"][round(deg / 22.5) % 16]
def get_random_background_image(city_name: str) -> str | None:
    city_folder = os.path.join(BACKGROUNDS_FOLDER, city_name)
    if os.path.isdir(city_folder):
        import random
        files = [f for f in os.listdir(city_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if files: return os.path.join(city_folder, random.choice(files))
    return None
def round_rectangle(draw, xy, r, fill):
    x1, y1, x2, y2 = xy
    draw.rectangle((x1+r, y1, x2-r, y2), fill=fill); draw.rectangle((x1, y1+r, x2, y2-r), fill=fill)
    for T in [(x1,y1,x1+2*r,y1+2*r,180,270),(x2-2*r,y1,x2,y1+2*r,270,360),(x1,y2-2*r,x1+2*r,y2,90,180),(x2-2*r,y2-2*r,x2,y2,0,90)]:
        draw.pieslice(T[:4], T[4], T[5], fill=fill)
def get_font(size: int) -> ImageFont.FreeTypeFont:
    if size in font_cache: return font_cache[size]
    try: font = ImageFont.truetype("arial.ttf", size)
    except IOError: font = ImageFont.load_default()
    font_cache[size] = font
    return font
def add_watermark(img: Image.Image) -> Image.Image:
    try:
        base = img.convert("RGBA")
        if not os.path.exists(WATERMARK_FILE): return base.convert("RGB")
        watermark = Image.open(WATERMARK_FILE).convert("RGBA")
        w, h = base.size
        target_w = int(w * WATERMARK_SCALE_FACTOR)
        h_size = int(watermark.height * (target_w / watermark.width))
        watermark = watermark.resize((target_w, h_size), Image.Resampling.LANCZOS)
        padding = int(w * 0.02)
        pos = (w - watermark.width - padding, padding)
        transparent = Image.new('RGBA', base.size, (0,0,0,0)); transparent.paste(base, (0,0))
        transparent.paste(watermark, pos, mask=watermark)
        return transparent.convert("RGB")
    except Exception as e:
        logger.error(f"Ошибка при добавлении вотермарки: {e}")
        return img.convert("RGB")

# --- Основной исполняемый блок ---
async def main():
    logger.info("--- Запуск основного процесса ---")
    openweather_api_key = os.getenv("OPENWEATHER_API_KEY")
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    target_chat_id = os.getenv("TARGET_CHAT_ID")
    if not all([telegram_bot_token, target_chat_id, openweather_api_key]):
        logger.error("ОШИБКА: Отсутствуют переменные окружения.")
        return
    bot = Bot(token=telegram_bot_token)
    await delete_old_messages(bot, target_chat_id)
    frames = []
    for city_name, coords in CITIES.items():
        logger.info(f"Обработка города: {city_name}...")
        weather_data = await get_current_weather(coords, openweather_api_key)
        if weather_data:
            precipitation_forecast_lines = format_precipitation_forecast(weather_data)
            frame = create_weather_frame(city_name, weather_data, precipitation_forecast_lines)
            if frame: frames.append(frame)
        else:
            logger.warning(f"Нет данных для {city_name}.")
        await asyncio.sleep(0.5)
    if not frames:
        logger.error("Не удалось создать ни одного кадра.")
        return
    video_path = "weather_report.mp4"
    create_weather_video(frames, video_path)
    if os.path.exists(video_path):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(AD_BUTTON_TEXT, url=AD_BUTTON_URL), InlineKeyboardButton(NEWS_BUTTON_TEXT, url=NEWS_BUTTON_URL)]])
        try:
            with open(video_path, 'rb') as video_file:
                message = await bot.send_animation(
                    chat_id=target_chat_id, animation=video_file,
                    disable_notification=True, reply_markup=keyboard
                )
            save_message_id(message.message_id)
            logger.info(f"Анимация MP4 отправлена. ID: {message.message_id}.")
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
