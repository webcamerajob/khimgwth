import os
import json
import asyncio
from datetime import datetime, timedelta
from telegram import Bot
import subprocess # Для выполнения команд Git

# --- Конфигурация из переменных окружения ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MESSAGES_FILE = os.getenv('MESSAGES_TO_DELETE_FILE_NAME', 'messages_to_delete.json')
DELETE_AFTER_HOURS_STR = os.getenv('DELETE_AFTER_HOURS_SETTING', '3')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN') # Токен для авто-коммита
GIT_COMMIT_EMAIL = os.getenv('GIT_COMMIT_EMAIL', 'github-actions[bot]@users.noreply.github.com')
GIT_COMMIT_NAME = os.getenv('GIT_COMMIT_NAME', 'github-actions[bot]')
# --- Конец конфигурации ---


async def delete_messages_and_commit():
    """
    Асинхронная функция для чтения файла с ID сообщений, их удаления,
    и последующего коммита обновленного файла обратно в репозиторий.
    """
    if not TELEGRAM_BOT_TOKEN:
        print('TELEGRAM_BOT_TOKEN не установлен. Пропускаю удаление.')
        return

    # Загружаем текущие данные из файла
    current_data = []
    if os.path.exists(MESSAGES_FILE):
        try:
            with open(MESSAGES_FILE, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
            print(f'Загружено {len(current_data)} записей из {MESSAGES_FILE}.')
        except (json.JSONDecodeError, FileNotFoundError):
            print(f'Ошибка чтения или файл {MESSAGES_FILE} пуст/поврежден. Начинаю с пустого списка.')
            current_data = []
    else:
        print(f'Файл {MESSAGES_FILE} не найден. Создам новый, если будут сообщения для сохранения.')

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    messages_to_keep = [] # Сообщения, которые еще не нужно удалять
    changes_made = False # Флаг, чтобы отслеживать, были ли изменения в файле

    # Преобразуем DELETE_AFTER_HOURS_STR в int
    try:
        delete_after_hours = int(DELETE_AFTER_HOURS_STR)
    except ValueError:
        print(f'Предупреждение: Неверное значение DELETE_AFTER_HOURS_SETTING: {DELETE_AFTER_HOURS_STR}. Использую значение по умолчанию: 3 часа.')
        delete_after_hours = 3

    for entry in current_data:
        try:
            entry_time = datetime.fromisoformat(entry['timestamp'])
            chat_id = entry['chat_id']
            message_ids = entry['message_ids']

            # Проверяем, прошло ли достаточно времени для удаления сообщения
            if datetime.now() - entry_time >= timedelta(hours=delete_after_hours):
                print(f'Попытка удалить сообщения в чате {chat_id} (отправлены в {entry_time.strftime("%Y-%m-%d %H:%M:%S")}): {message_ids}') 
                for msg_id in message_ids:
                    try:
                        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                        print(f'Удалено сообщение ID {msg_id} в чате {chat_id}.')
                        await asyncio.sleep(0.1) # Небольшая задержка
                        changes_made = True # Было изменение
                    except Exception as e:
                        # Логируем ошибки (например, сообщение уже удалено)
                        print(f'Ошибка при удалении сообщения ID {msg_id} в чате {chat_id}: {e}')
            else:
                messages_to_keep.append(entry) # Оставляем запись
        except KeyError as e:
            print(f'Пропущена поврежденная запись в {MESSAGES_FILE} (отсутствует ключ: {e}).')
        except ValueError as e:
            print(f'Пропущена запись с неверным форматом даты в {MESSAGES_FILE}: {e}.')

    # Если changes_made True ИЛИ количество записей изменилось (например, все удалены)
    # ИЛИ файл был создан заново (len(current_data) != len(messages_to_keep))
    if changes_made or (len(current_data) != len(messages_to_keep)):
        print(f"Обнаружены изменения, или файл {MESSAGES_FILE} требует обновления. Перезаписываю.")
        try:
            with open(MESSAGES_FILE, 'w', encoding='utf-8') as f:
                json.dump(messages_to_keep, f, ensure_ascii=False, indent=4)
            print(f'Файл {MESSAGES_FILE} обновлен. Осталось записей: {len(messages_to_keep)}.')
            
            # --- Логика авто-коммита ---
            if GITHUB_TOKEN:
                print("Начинаю процесс авто-коммита...")
                try:
                    # Настройка Git пользователя
                    subprocess.run(['git', 'config', 'user.email', GIT_COMMIT_EMAIL], check=True)
                    subprocess.run(['git', 'config', 'user.name', GIT_COMMIT_NAME], check=True)

                    # Добавляем изменённый файл
                    subprocess.run(['git', 'add', MESSAGES_FILE], check=True)

                    # Проверяем, есть ли что коммитить (может быть, файл перезаписан, но содержание то же)
                    result = subprocess.run(['git', 'diff', '--staged', '--quiet'], check=False)
                    if result.returncode == 0:
                        print('Нет новых изменений для коммита в файле сообщений после перезаписи.')
                        return # Нет изменений, выходим
                    
                    # Коммитим изменения
                    commit_message = f'chore: Auto-commit updated {MESSAGES_FILE} after message cleanup'
                    subprocess.run(['git', 'commit', '-m', commit_message], check=True)
                    print(f'Изменения закоммичены: "{commit_message}"')

                    # Отправляем изменения на GitHub
                    repo_url = f"https://{GITHUB_TOKEN}@github.com/{os.getenv('GITHUB_REPOSITORY')}.git"
                    subprocess.run(['git', 'push', repo_url], check=True)
                    print('Изменения успешно отправлены на GitHub.')

                except subprocess.CalledProcessError as e:
                    print(f'Ошибка выполнения Git-команды: {e}')
                    print(f'Вывод Git (stdout): {e.stdout.decode()}')
                    print(f'Вывод Git (stderr): {e.stderr.decode()}')
                except Exception as e:
                    print(f'Непредвиденная ошибка при авто-коммите: {e}')
            else:
                print("GITHUB_TOKEN не установлен, авто-коммит пропущен.")
            # --- Конец логики авто-коммита ---

        except Exception as e:
            print(f'Ошибка при перезаписи файла {MESSAGES_FILE}: {e}')
    else:
        print(f'Нет изменений в файле {MESSAGES_FILE}. Пропускаю перезапись и коммит.')

if __name__ == '__main__':
    asyncio.run(delete_messages_and_commit())
