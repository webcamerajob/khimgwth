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

async def get_current_weather(location_key: str, city_name_for_test: str) -> Dict | None:
    """
    Получает текущие погодные условия для заданного Location Key.
    Параметр city_name_for_test используется только в тестовом режиме.
    """
    if TEST_MODE:
        if city_name_for_test in PRESET_WEATHER_DATA:
            logger.info(f"Используются предустановленные данные для: {city_name_for_test}")
            return PRESET_WEATHER_DATA.get(city_name_for_test)
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

def get_random_background_image(city_name: str = "Общий") -> str | None:
    """
    Возвращает случайный путь к файлу изображения фона.
    Если есть папка 'Общий', берет из нее, иначе из папки первого города.
    """
    common_folder = os.path.join(BACKGROUNDS_FOLDER, "Общий")
    if os.path.isdir(common_folder):
        image_files = [f for f in os.listdir(common_folder) if os.path.isfile(os.path.join(common_folder, f)) and f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
        if image_files:
            return os.path.join(common_folder, random.choice(image_files))
    
    # Если общей папки нет или она пуста, попробуем взять из папки Пномпеня (как основной для фона)
    phnom_penh_folder = os.path.join(BACKGROUNDS_FOLDER, "Пномпень")
    if os.path.isdir(phnom_penh_folder):
        image_files = [f for f in os.listdir(phnom_penh_folder) if os.path.isfile(os.path.join(phnom_penh_folder, f)) and f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
        if image_files:
            logger.warning(f"Используется фон из папки 'Пномпень', так как папка 'Общий' отсутствует или пуста.")
            return os.path.join(phnom_penh_folder, random.choice(image_files))

    logger.error(f"Папки для фонов 'Общий' и 'Пномпень' не найдены или пусты. Невозможно сгенерировать изображение.")
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

def create_combined_weather_image(all_weather_data: Dict[str, Dict]) -> str | None:
    """
    Создает одно изображение с информацией о погоде для всех городов.
    """
    background_path = get_random_background_image() # Используем общую папку для фона
    if not background_path:
        return None

    try:
        img = Image.open(background_path).convert("RGB")
        width, height = img.size
        
        draw = ImageDraw.Draw(img) 

        # Параметры макета
        num_cities = len(all_weather_data)
        
        # Общая ширина, которую займут плашки (около 90% от ширины изображения)
        total_plaque_area_width = int(width * 0.90)
        
        # Отступы и интервалы
        horizontal_padding_img = (width - total_plaque_area_width) // 2 # Отступ от краев изображения до плашек
        vertical_padding_img = int(height * 0.04) # Отступ сверху и снизу изображения
        plaque_spacing_y = int(height * 0.02) # Вертикальный интервал между плашками

        # Ширина каждой плашки
        plaque_width_individual = total_plaque_area_width
        
        # Начальная позиция Y для первой плашки
        current_y = vertical_padding_img

        # Список для хранения данных о плашках (для дальнейшего рендеринга)
        plaque_info_list = []

        # Предварительный проход для определения размера шрифта и высоты плашек
        # Это нужно, чтобы равномерно распределить их по вертикали
        # Для простоты, сначала определим базовый размер шрифта, а затем
        # рассчитаем высоту каждой плашки.
        
        # Максимальная высота, доступная для каждой плашки
        max_available_height_per_plaque = (height - 2 * vertical_padding_img - (num_cities - 1) * plaque_spacing_y) / num_cities

        # Определение оптимального размера шрифта
        # Мы хотим, чтобы текст был читабельным и вписывался в ширину плашки
        max_text_width_in_plaque = int(plaque_width_individual * 0.90) # Текст занимает 90% ширины плашки
        
        # Определяем максимальный font_size, который поместится в max_text_width_in_plaque
        # и будет иметь адекватную высоту
        optimal_font_size = 1 # Начинаем с очень маленького
        temp_font = get_font(optimal_font_size)
        if temp_font is None: # Запасной вариант, если даже маленький шрифт не грузится
            logger.error("Не удалось загрузить ни один шрифт для расчета размера текста.")
            return None

        test_text_longest_line = "Температура: 99.9°C" # Пример самой длинной строки
        
        while True:
            temp_font = get_font(optimal_font_size + 1)
            if temp_font is None: break # Невозможно увеличить шрифт
            
            # Используем getbbox для определения ширины строки с текущим шрифтом
            bbox = draw.textbbox((0, 0), test_text_longest_line, font=temp_font)
            current_line_width = bbox[2] - bbox[0]

            if current_line_width < max_text_width_in_plaque:
                optimal_font_size += 1
            else:
                break
        
        # Используем найденный оптимальный размер шрифта для всех плашек
        font = get_font(optimal_font_size)
        if font is None:
            logger.error("Не удалось загрузить оптимальный шрифт.")
            return None

        # Собираем данные для каждой плашки
        for city_name, weather_data in all_weather_data.items():
            wind_direction_abbr = get_wind_direction_abbr(weather_data['Wind']['Direction']['Localized'])
            pressure_kpa = weather_data['Pressure']['Metric']['Value'] * 0.1

            weather_text_lines = [
                f"{city_name.capitalize()}:",
                f"Температура: {weather_data['Temperature']['Metric']['Value']:.1f}°C",
                f"Ощущается как: {weather_data['RealFeelTemperature']['Metric']['Value']:.1f}°C",
                f"{weather_data['WeatherText']}",
                f"Влажность: {weather_data['RelativeHumidity']}%",
                f"Ветер: {wind_direction_abbr}, {weather_data['Wind']['Speed']['Metric']['Value']:.1f} км/ч",
                f"Давление: {pressure_kpa:.1f} кПа",
            ]
            weather_text = "\n".join(weather_text_lines)

            # Получаем размеры текста
            bbox = draw.textbbox((0, 0), weather_text, font=font, spacing=5) # Меньший spacing для компактности
            text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            
            # padding внутри плашки
            plaque_inner_padding = int(plaque_width_individual * 0.05) # 5% от ширины плашки для отступов
            
            plaque_height_individual = text_height + 2 * plaque_inner_padding
            
            # Проверяем, не выходит ли плашка за рамки доступной высоты
            if plaque_height_individual > max_available_height_per_plaque:
                # Если плашка слишком высокая, уменьшаем внутренний отступ или шрифт
                # В данном случае, просто обрезаем, если очень сильно вылезает
                logger.warning(f"Плашка для {city_name} слишком высокая ({plaque_height_individual:.0f}px), обрезана до {max_available_height_per_plaque:.0f}px.")
                plaque_height_individual = max_available_height_per_plaque

            plaque_info_list.append({
                "city_name": city_name,
                "text": weather_text,
                "text_width": text_width,
                "text_height": text_height,
                "plaque_height": plaque_height_individual,
                "inner_padding": plaque_inner_padding,
            })

        # Общая высота, занимаемая всеми плашками и промежутками
        total_content_height = sum(p['plaque_height'] for p in plaque_info_list) + \
                               (num_cities - 1) * plaque_spacing_y
        
        # Центрируем весь блок плашек по вертикали
        start_y = (height - total_content_height) // 2
        if start_y < vertical_padding_img: # Если блок слишком большой, начинаем с верхнего отступа
            start_y = vertical_padding_img

        current_y_render = start_y

        # Рисуем каждую плашку
        for plaque_info in plaque_info_list:
            plaque_x1 = horizontal_padding_img
            plaque_y1 = current_y_render
            plaque_x2 = plaque_x1 + plaque_width_individual
            plaque_y2 = plaque_y1 + plaque_info['plaque_height']

            # Создаем изображение для плашки с прозрачностью
            plaque_img = Image.new('RGBA', img.size, (0, 0, 0, 0))
            plaque_draw = ImageDraw.Draw(plaque_img)

            border_radius = int(plaque_width_individual * 0.02)
            round_rectangle(plaque_draw, (plaque_x1, plaque_y1, plaque_x2, plaque_y2), border_radius, (0, 0, 0, 150))
            img.paste(plaque_img, (0, 0), plaque_img)

            # Рисуем текст по центру плашки
            text_x = plaque_x1 + (plaque_width_individual - plaque_info['text_width']) // 2
            text_y = plaque_y1 + plaque_info['inner_padding']
            
            draw.multiline_text((text_x, text_y), plaque_info['text'], fill=(255, 255, 255), font=font, spacing=5, align="center")

            current_y_render += plaque_info['plaque_height'] + plaque_spacing_y


        output_path = "weather_summary.png" # Одно имя для итогового файла
        img.save(output_path)
        return output_path

    except Exception as e:
        logger.error(f"Ошибка при создании объединенного изображения погоды: {e}")
        return None

async def format_and_send_weather(bot: Bot, all_weather_data: Dict[str, Dict], target_chat_id: str):
    """
    Форматирует данные о погоде и отправляет ЕДИНОЕ изображение в Telegram.
    """
    image_path = create_combined_weather_image(all_weather_data)
    if image_path:
        try:
            with open(image_path, 'rb') as photo:
                await bot.send_photo(chat_id=target_chat_id, photo=photo)
            os.remove(image_path) # Удаляем файл изображения после отправки
            logger.info(f"Объединенное изображение погоды успешно отправлено.")
        except Exception as e:
            logger.error(f"Ошибка при отправке объединенного изображения: {e}")
            await bot.send_message(chat_id=target_chat_id, text=f"Ошибка при отправке объединенного изображения погоды.", parse_mode='HTML')
    else:
        await bot.send_message(chat_id=target_chat_id, text=f"Не удалось создать объединенное изображение погоды.", parse_mode='HTML')

async def main():
    """
    Главная функция, которая запускается при выполнении скрипта.
    Собирает данные для всех городов и отправляет ОДНО сообщение с изображением.
    """
    cities_to_publish = ["Пномпень", "Сиануквиль", "Сиемреап"]

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    accuweather_api_key = os.getenv("ACCUWEATHER_API_KEY")
    target_chat_id = os.getenv("TARGET_CHAT_ID")

    if not all([telegram_bot_token, target_chat_id]) or (not TEST_MODE and not accuweather_api_key):
        logger.error("ОШИБКА: Отсутствуют необходимые переменные окружения. "
                     "Убедитесь, что TELEGRAM_BOT_TOKEN и TARGET_CHAT_ID установлены.")
        if not TEST_MODE and not accuweather_api_key:
            logger.error("ACCUWEATHER_API_KEY также необходим, когда TEST_MODE=False.")
        
        if telegram_bot_token and target_chat_id:
            bot = Bot(token=telegram_bot_token)
            await bot.send_message(chat_id=target_chat_id,
                                   text="❌ <b>Ошибка конфигурации бота!</b> Отсутствуют API-ключи или ID чата.",
                                   parse_mode='HTML')
        return

    bot = Bot(token=telegram_bot_token)

    # Создаем папку backgrounds и подпапку "Общий", а также подпапки для городов, если их нет
    if not os.path.exists(BACKGROUNDS_FOLDER):
        os.makedirs(BACKGROUNDS_FOLDER)
        logger.info(f"Создана папка для фонов: {BACKGROUNDS_FOLDER}")
    
    common_bg_folder = os.path.join(BACKGROUNDS_FOLDER, "Общий")
    if not os.path.exists(common_bg_folder):
        os.makedirs(common_bg_folder)
        logger.info(f"Создана папка для общих фонов: {common_bg_folder}")

    # Подпапки для городов теперь не строго обязательны для фонов, но могут использоваться
    # для организации, или если вы захотите вернуться к отдельным изображениям.
    # Оставим их создание на случай, если вы захотите положить туда фон для Пномпеня
    # на случай отсутствия "Общего"
    for city in cities_to_publish:
        city_folder = os.path.join(BACKGROUNDS_FOLDER, city)
        if not os.path.exists(city_folder):
            os.makedirs(city_folder)
            logger.info(f"Создана папка для фонов города: {city_folder} (для использования в качестве запасного фонда)")
    
    logger.warning(f"Убедитесь, что в папке '{BACKGROUNDS_FOLDER}/Общий' есть изображения для использования в качестве общего фона.")
    logger.warning(f"Если папка '{BACKGROUNDS_FOLDER}/Общий' пуста, скрипт попытается использовать фон из '{BACKGROUNDS_FOLDER}/Пномпень'.")


    all_weather_data = {}
    for city in cities_to_publish:
        logger.info(f"Получаю данные для {city}...")
        
        weather_data = None
        if TEST_MODE:
            weather_data = PRESET_WEATHER_DATA.get(city)
            if not weather_data:
                logger.error(f"Предустановленные данные для города {city} не найдены.")
        else:
            location_key = await get_location_key(city)
            if location_key:
                weather_data = await get_current_weather(location_key, city) # Передаем city для тестового режима
            else:
                logger.warning(f"Не удалось получить Location Key для города: {city}. Данные для него не будут включены.")
        
        if weather_data:
            all_weather_data[city] = weather_data
        else:
            await bot.send_message(chat_id=target_chat_id,
                                   text=f"❌ Не удалось получить данные о погоде для <b>{city}</b>. Он не будет включен в сводку.",
                                   parse_mode='HTML')

    if all_weather_data:
        await format_and_send_weather(bot, all_weather_data, target_chat_id)
    else:
        await bot.send_message(chat_id=target_chat_id,
                               text=f"❌ Не удалось получить данные о погоде ни для одного из городов.",
                               parse_mode='HTML')

if __name__ == "__main__":
    asyncio.run(main())
