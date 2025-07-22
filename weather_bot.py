import json
import os
import logging
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot

# Настройки
USE_PRESET = True
PRESET_FILE = "preset_weather.json"
IMAGE_NAME = f"/tmp/weather_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"

# Логирование
logging.basicConfig(level=logging.INFO)

def fetch_weather():
    if USE_PRESET:
        if not os.path.exists(PRESET_FILE):
            raise FileNotFoundError(f"Файл пресета '{PRESET_FILE}' не найден.")
        with open(PRESET_FILE) as f:
            return json.load(f)
    return {}

def generate_weather_image(weather):
    try:
        background = Image.open("pp.jpg").convert("RGBA").resize((600, 400))
    except Exception as e:
        raise RuntimeError(f"Ошибка загрузки pp.jpg: {e}")

    img = background.copy()
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 28)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 20)
    except:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Прозрачная плашка
    draw.rectangle([(10, 20), (590, 270)], fill=(0, 0, 0, 100))

    # Основной текст
    draw.text((30, 40), "🌤 Погода в Пномпене", font=font, fill="white")
    draw.text((30, 100), f"{weather['desc']}, {weather['temp']}", font=font, fill="white")
    draw.text((30, 160), f"Влажность: {weather['humidity']}", font=font, fill="white")
    draw.text((30, 220), f"Ветер: {weather['wind']}", font=font, fill="white")

    # Водяной знак
    draw.text((400, 360), "Phnom Penh Bot", font=font_small, fill=(255, 255, 255, 180))

    final_img = Image.alpha_composite(img, overlay).convert("RGB")
    final_img.save(IMAGE_NAME)
    logging.info(f"Картинка сохранена: {IMAGE_NAME}")
    return IMAGE_NAME

def post_to_telegram(image_path):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHANNEL_NAME")

    if not token or not chat_id:
        raise EnvironmentError("Отсутствуют переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHANNEL_NAME.")

    bot = Bot(token=token)
    with open(image_path, "rb") as image:
        bot.send_photo(chat_id=chat_id, photo=image, caption="⛅ Автоматический прогноз")

def run():
    try:
        weather = fetch_weather()
        image_path = generate_weather_image(weather)
        post_to_telegram(image_path)
        logging.info("Готово! Прогноз отправлен в Telegram.")
    except Exception as e:
        logging.error(f"Ошибка выполнения: {e}")

if __name__ == "__main__":
    run()
