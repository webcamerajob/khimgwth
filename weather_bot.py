import json
import os
import logging
from telegram import Bot
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# Настройки
USE_PRESET = True
PRESET_FILE = "preset_weather.json"
IMAGE_NAME = f"/tmp/weather_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

# Логирование
logging.basicConfig(level=logging.INFO)

def fetch_weather():
    if USE_PRESET:
        if not os.path.exists(PRESET_FILE):
            raise FileNotFoundError(f"Файл пресета '{PRESET_FILE}' не найден.")
        with open(PRESET_FILE) as f:
            return json.load(f)
    # Здесь можно добавить реальный запрос к AccuWeather API
    return {}

def generate_weather_image(weather):
    img = Image.new('RGB', (600, 400), color='skyblue')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 28)
    except:
        font = ImageFont.load_default()

    draw.text((20, 40), "🌤 Погода в Пномпене", font=font, fill="black")
    draw.text((20, 100), f"{weather['desc']}, {weather['temp']}", font=font, fill="black")
    draw.text((20, 160), f"Влажность: {weather['humidity']}", font=font, fill="black")
    draw.text((20, 220), f"Ветер: {weather['wind']}", font=font, fill="black")

    img.save(IMAGE_NAME)
    logging.info(f"Изображение сохранено: {IMAGE_NAME}")
    return IMAGE_NAME

def post_to_telegram(image_path):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHANNEL_NAME")
    if not token or not chat_id:
        raise EnvironmentError("Отсутствует TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_NAME в окружении.")

    bot = Bot(token=token)
    with open(image_path, "rb") as image:
        bot.send_photo(chat_id=chat_id, photo=image, caption="⛅ Автоматический прогноз")

def run():
    try:
        weather = fetch_weather()
        image_path = generate_weather_image(weather)
        post_to_telegram(image_path)
        logging.info("Успешно отправлено в Telegram.")
    except Exception as e:
        logging.error(f"Ошибка при выполнении бота: {e}")

if __name__ == "__main__":
    run()
