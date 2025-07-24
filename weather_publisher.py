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
WATERMARK_SCALE_FACTOR = 0.25  # Масштаб вотермарки (например, 0.25 означает 25% от ширины основного изображения)

# Настройки кнопок
AD_BUTTON_TEXT = "Новости"
AD_BUTTON_URL = "https://t.me/cambodiacriminal"
NEWS_BUTTON_TEXT = "Реклама"
NEWS_BUTTON_URL = "https://t.me/mister1dollar"

# Путь к папке с фонами
BACKGROUNDS_FOLDER = "backgrounds"

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

def get_font(font_size: int):
    """
    Пытается загрузить шрифт, подходящий для кириллицы.
    Возвращает объект шрифта или None, если ни один шрифт не загружен.
    """
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

def create_weather_image(city_name: str, weather_data: Dict) -> str | None:
    """
    Создает изображение с информацией о погоде на фоне с полупрозрачной плашкой.
    Возвращает путь к изображению с вотермаркой или None в случае ошибки.
    """
    background_path = get_random_background_image(city_name)
    if not background_path:
        return None

    try:
        img = Image.open(background_path).convert("RGB")
        width, height = img.size
        
        draw = ImageDraw.Draw(img) 

        # Исправлено: Правильный доступ к данным о ветре
        wind_direction_text = weather_data['Wind']['Direction']['Localized']
        wind_direction_abbr = get_wind_direction_abbr(wind_direction_text)

        # Исправлено: Правильное форматирование f-строк и доступ к данным
        weather_text_lines = [
            f"Погода в городе {city_name}:",
            f"Температура: {weather_data['Temperature']['Metric']['Value']:.1f}°C",
            f"Ощущается как: {weather_data['RealFeelTemperature']['Metric']['Value']:.1f}°C",
            f"{weather_data['WeatherText']}",
            f"Влажность: {weather_data['RelativeHumidity']}%",
            f"Ветер: {wind_direction_abbr}, {weather_data['Wind']['Speed']['Metric']['Value']:.1f} км/ч",
        ]
        weather_text = "\n".join(weather_text_lines)

        # Рассчитываем размер плашки (85% ширины от полного кадра)
        plaque_width = int(width * 0.85)
        
        # Определяем размер шрифта на основе 75% от ширины плашки
        target_text_width_ratio = 0.75
        max_text_width_for_font_sizing = int(plaque_width * target_text_width_ratio)
        
        current_font_size = 15  # Начинаем с разумного размера
        best_font = get_font(current_font_size)  # Инициализируем с начальным шрифтом
        
        # Итеративно увеличиваем размер шрифта, пока текст не достигнет 75% ширины плашки
        while True:
            test_font = get_font(current_font_size + 1)
            if test_font is None:  # Если шрифт не загрузился или не увеличивается
                break
            
            max_line_width = 0
            for line in weather_text_lines:
                # Исправлено: Правильный расчет ширины линии
                left, top, right, bottom = draw.textbbox((0,0), line, font=test_font)
                line_width = right - left
                max_line_width = max(max_line_width, line_width)

            if max_line_width <= max_text_width_for_font_sizing:
                best_font = test_font
                current_font_size += 1
            else:
                break

        font = best_font  # Используем найденный оптимальный шрифт
        
        # Пересчитываем размер текста с финальным шрифтом
        # Исправлено: Правильный расчет ширины и высоты текста из bbox
        left, top, right, bottom = draw.textbbox((0, 0), weather_text, font=font, spacing=10)
        text_width = right - left
        text_height = bottom - top

        # Высота плашки подстраивается под текст с отступами
        padding = int(width * 0.03)  # Отступы от текста до краев плашки
        border_radius = int(width * 0.02)  # Радиус скругления углов
        
        plaque_height = text_height + 2 * padding

        # Позиционирование плашки (по центру по горизонтали и вертикали)
        plaque_x1 = (width - plaque_width) // 2
        plaque_y1 = (height - plaque_height) // 2  # Вертикальное центрирование
        plaque_x2 = plaque_x1 + plaque_width
        plaque_y2 = plaque_y1 + plaque_height

        # Создаем прозрачное изображение для плашки
        plaque_img = Image.new('RGBA', img.size, (0, 0, 0, 0))  # Полностью прозрачная основа
        plaque_draw = ImageDraw.Draw(plaque_img)

        # Рисуем скругленный прямоугольник на плашке
        round_rectangle(plaque_draw, (plaque_x1, plaque_y1, plaque_x2, plaque_y2), border_radius, (0, 0, 0, 150))  # Черный, полупрозрачный

        # Накладываем плашку на основное изображение
        img.paste(plaque_img, (0, 0), plaque_img)

        # Рисуем текст по центру плашки
        text_x = plaque_x1 + (plaque_width - text_width) // 2
        text_y = plaque_y1 + (plaque_height - text_height) // 2  # Вертикальное центрирование текста
        
        draw.multiline_text((text_x, text_y), weather_text, fill=(255, 255, 255), font=font, spacing=10, align="center")

        original_output_path = f"weather_{city_name.lower().replace(' ', '_')}.png"
        img.save(original_output_path)
        
        # Добавляем вотермарку к сгенерированному изображению
        watermarked_path = add_watermark(original_output_path)
        
        # Возвращаем путь к вотермаркированному изображению, если оно было создано, иначе к оригиналу
        return watermarked_path if watermarked_path else original_output_path
    
    except Exception as e:
        logger.error(f"Ошибка при создании изображения для {city_name}: {e}")
        return None

def save_message_id(message_id: int):
    """
    Сохраняет ID отправленного сообщения и время его отправки в YAML файл.
    """
    try:
        # Загружаем существующие ID сообщений
        messages = []  # Исправлено: Инициализация пустого списка
        if os.path.exists(MESSAGE_IDS_FILE):
            with open(MESSAGE_IDS_FILE, 'r') as f:
                try:
                    loaded_data = yaml.safe_load(f)
                    if isinstance(loaded_data, list):
                        messages = loaded_data
                    else:
                        logger.warning(f"Файл {MESSAGE_IDS_FILE} содержит некорректный формат данных. Будет создан новый список.")
                except yaml.YAMLError as e:
                    logger.error(f"Ошибка при парсинге YAML файла {MESSAGE_IDS_FILE}: {e}. Будет создан новый список.")
        
        # Добавляем новое сообщение
        current_time_utc = datetime.datetime.now(datetime.timezone.utc)
        messages.append({
            'message_id': message_id,
            'sent_at': current_time_utc.isoformat()  # Сохраняем время в ISO формате (UTC)
        })

        # Сохраняем обновленный список
        with open(MESSAGE_IDS_FILE, 'w') as f:
            yaml.dump(messages, f, default_flow_style=False)
        logger.info(f"Сообщение ID {message_id} сохранено в {MESSAGE_IDS_FILE}.")
    except Exception as e:
        logger.error(f"Ошибка при сохранении ID сообщения {message_id} в файл: {e}")

async def main():
    print("DEBUG: --- Запуск функции main() ---")
    global city_to_process
    cities_to_publish = ["Пномпень", "Сиануквиль", "Сиемреап"]
    generated_image_paths = []

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    accuweather_api_key = os.getenv("ACCUWEATHER_API_KEY")
    target_chat_id = os.getenv("TARGET_CHAT_ID")

    print(f"DEBUG: TEST_MODE установлен в: {TEST_MODE}")
    print(f"DEBUG: TELEGRAM_BOT_TOKEN есть: {bool(telegram_bot_token)}")
    print(f"DEBUG: TARGET_CHAT_ID есть: {bool(target_chat_id)}")
    if not TEST_MODE:
        print(f"DEBUG: ACCUWEATHER_API_KEY есть: {bool(accuweather_api_key)}")

    if not all([telegram_bot_token, target_chat_id]) or (not TEST_MODE and not accuweather_api_key):
        logger.error("ОШИБКА: Отсутствуют необходимые переменные окружения.")
        if not TEST_MODE and not accuweather_api_key:
            logger.error("ACCUWEATHER_API_KEY также необходим, когда TEST_MODE=False.")
        if telegram_bot_token and target_chat_id:
            try:
                bot_for_error = Bot(token=telegram_bot_token)
                await bot_for_error.send_message(chat_id=target_chat_id,
                                                 text="❌ <b>Ошибка конфигурации бота!</b> Отсутствуют API-ключи или ID чата.",
                                                 parse_mode='HTML')
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение об ошибке конфигурации: {e}")
        return

    bot = Bot(token=telegram_bot_token)
    print("DEBUG: Бот Telegram инициализирован.")

    if not os.path.exists(BACKGROUNDS_FOLDER):
        os.makedirs(BACKGROUNDS_FOLDER)
        logger.info(f"Создана папка для фонов: {BACKGROUNDS_FOLDER}")
    for city in cities_to_publish:
        city_folder = os.path.join(BACKGROUNDS_FOLDER, city)
        if not os.path.exists(city_folder):
            os.makedirs(city_folder)
            logger.info(f"Создана папка для фонов города: {city_folder}")

    logger.warning(f"Убедитесь, что файлы изображений присутствуют в папках '{BACKGROUNDS_FOLDER}/<Город>'")
    logger.warning(f"Убедитесь, что файл '{WATERMARK_FILE}' находится в корне проекта.")
    print("DEBUG: Проверки папок и файлов завершены.")

    for city in cities_to_publish:
        city_to_process = city
        logger.info(f"Получаю данные для {city}...")
        print(f"DEBUG: Начало обработки города: {city}")

        weather_data = None
        if TEST_MODE:
            weather_data = PRESET_WEATHER_DATA.get(city)
            if not weather_data:
                logger.error(f"Нет предустановленных данных для города {city}")
        else:
            location_key = await get_location_key(city)
            if location_key:
                weather_data = await get_current_weather(location_key)
            else:
                logger.warning(f"Не удалось получить Location Key для {city}. Пропускаю.")
                continue

        if weather_data:
            print(f"DEBUG: Данные о погоде получены. Генерация изображения.")
            image_path = create_weather_image(city, weather_data)
            if image_path:
                generated_image_paths.append(image_path)
                print(f"DEBUG: Изображение создано: {image_path}")
            else:
                logger.error(f"Не удалось создать изображение для {city}")
                print(f"DEBUG: Ошибка при создании изображения для {city}")
        else:
            logger.warning(f"Нет погодных данных для {city}. Пропускаю.")
            print(f"DEBUG: Нет данных о погоде для {city}")
        await asyncio.sleep(0.5)

    print(f"DEBUG: Сгенерировано изображений: {len(generated_image_paths)}")

    if generated_image_paths:
        print("DEBUG: Начинаю отправку изображений в Telegram.")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(AD_BUTTON_TEXT, url=AD_BUTTON_URL),
             InlineKeyboardButton(NEWS_BUTTON_TEXT, url=NEWS_BUTTON_URL)]
        ])

        for i, path in enumerate(generated_image_paths):
            print(f"DEBUG: Отправка {i+1}/{len(generated_image_paths)}: {path}")
            message = None
            try:
                with open(path, 'rb') as f:
                    caption = None
                    reply_markup = keyboard if i == len(generated_image_paths) - 1 else None

                    message = await bot.send_photo(
                        chat_id=target_chat_id,
                        photo=f,
                        caption=caption,
                        reply_markup=reply_markup
                    )
                    logger.info(f"Фото отправлено: {path}")
                    print(f"DEBUG: Фото отправлено: {path}")
            except FileNotFoundError:
                logger.error(f"Файл не найден: {path}")
                print(f"DEBUG: ОШИБКА: файл не найден: {path}")
            except Exception as e:
                logger.error(f"Ошибка при отправке фото {path}: {e}")
                print(f"DEBUG: ОШИБКА при отправке фото {path}: {e}")

            if message:
                try:
                    save_message_id(message.message_id)
                    logger.info(f"Message ID сохранён: {message.message_id}")
                    print(f"DEBUG: Message ID сохранён: {message.message_id}")
                except Exception as e:
                    logger.error(f"Ошибка при сохранении Message ID {message.message_id}: {e}")
                    print(f"DEBUG: ОШИБКА при сохранении Message ID: {e}")

            await asyncio.sleep(1)
    else:
        await bot.send_message(chat_id=target_chat_id,
                               text="Не удалось сгенерировать изображения погоды для отправки.",
                               parse_mode='HTML')
        print("DEBUG: Нет изображений для отправки.")

    print("DEBUG: Очистка временных файлов.")
    for path in generated_image_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"Удалён файл: {path}")
            if path.endswith("_watermarked.png"):
                original_path = path.replace("_watermarked.png", ".png")
                if os.path.exists(original_path):
                    os.remove(original_path)
                    logger.info(f"Удалён оригинал: {original_path}")
        except Exception as e:
            logger.error(f"Ошибка при удалении файла {path}: {e}")
            print(f"DEBUG: ОШИБКА при удалении файла {path}: {e}")
    print("DEBUG: --- Завершение функции main() ---")

if __name__ == "__main__":
    asyncio.run(main())
