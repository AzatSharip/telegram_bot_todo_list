import psycopg2
from psycopg2 import sql
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import json
import logging
from logging.handlers import RotatingFileHandler

# Установка ротации логов
log_handler = RotatingFileHandler(
    'todo_list_bot.log',         # Имя файла для логов
    maxBytes=5*1024*1024,  # Максимальный размер файла лога (5 MB)
    backupCount=3         # Количество резервных копий файлов логов
)

logging.basicConfig(
    handlers=[log_handler],
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

stand = 'prod'
if stand == 'prod':
    with open("prod_config.json", "r") as config_file:
        config = json.load(config_file)
elif stand == 'dev':
    with open("dev_config.json", "r") as config_file:
        config = json.load(config_file)


DB_HOST = config["DB_HOST"]
DB_NAME = config["DB_NAME"]
DB_USER = config["DB_USER"]
DB_PASSWORD = config["DB_PASSWORD"]
token = config["token"]
admins = config["admins"]


# Подключение к базе данных
def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn

# Функция старта
def start(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    user_first_name = update.message.from_user.first_name
    user_name = update.message.from_user.username

    if user_id in admins:
        reply_keyboard = [['Вывести список'], ['Удалить запись'], ['Статистика']]
    else:
        reply_keyboard = [['Вывести список'], ['Удалить запись']]

    # Логирование начала команды
    logger.info(f'Пользователь {user_first_name} - {user_name} - ({user_id}) начал сессию.')


    update.message.reply_text(
        'Привет! Отправь мне сообщение, и я запишу его в базу данных. Номер перед записью писать не надо, только текст!',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True, one_time_keyboard=False)
    )

# Функция для записи сообщения в базу данных
def save_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    user_name = update.message.from_user.username
    message_text = update.message.text
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO checklist (entry, user_id, username) VALUES (%s, %s, %s)", (message_text, user_id, user_name))
    conn.commit()
    cursor.execute(f"SELECT reorder_entry_id({user_id})")
    conn.commit()
    update.message.reply_text('Запись сохранена!')

    cursor.execute(f"SELECT entry_id, entry FROM checklist WHERE user_id = {user_id} ORDER BY entry_id")
    results = cursor.fetchall()
    conn.commit()

    task_list = "\n".join([f"{task[0]}. {task[1]}" for task in results])
    task_list = "`" + task_list + "`"
    update.message.reply_text(task_list, parse_mode='MarkdownV2')

    cursor.close()
    conn.close()

# Функция для вывода списка сообщений
def list_messages(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT entry_id, entry FROM checklist WHERE user_id = {user_id} ORDER BY entry_id")
    results = cursor.fetchall()
    conn.commit()

    if results:
        task_list = "\n".join([f"{task[0]}. {task[1]}" for task in results])
        task_list = "`" + task_list + "`"
        update.message.reply_text(task_list, parse_mode='MarkdownV2')

        cursor.close()
        conn.close()
    else:
        update.message.reply_text('Список дел пока пуст', parse_mode='MarkdownV2')

# Функция для удаления сообщения
def delete_message(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Введите № записи, которую хотите удалить или напишите "Отмена":')
    context.user_data['awaiting_delete_id'] = True

# Функция админа
def statistic(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id in admins:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
                            SELECT user_id, count(entry_id)
                            FROM checklist
                            group by user_id
                            order by count(entry_id) desc
                                            """)
        results = cursor.fetchall()
        conn.commit()
        if results:
            results = "\n".join([f"{r[0]} - {r[1]}" for r in results])
            results = "`" + str(results) + "`"
            update.message.reply_text(results, parse_mode='MarkdownV2')
        else:
            update.message.reply_text("Данных нет...")
    else:
        update.message.reply_text("Доступа нет!")



# Обработка текстовых сообщений
def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    user_first_name = update.message.from_user.first_name
    user_last_name = update.message.from_user.last_name
    user_name = update.message.from_user.username
    text = update.message.text

    logger.info(f'Получено сообщение от {user_first_name} {user_last_name} (@{user_name}): {text}')


    if text == 'Вывести список':
        list_messages(update, context)
    elif text == 'Удалить запись':
        delete_message(update, context)
    elif context.user_data.get('awaiting_delete_id'):
        while True:
            if is_numeric(text):
                message_id = int(text)
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM checklist WHERE entry_id = %s AND user_id = %s', (message_id, user_id))
                if cursor.rowcount == 0:
                    update.message.reply_text(f'Запись №{message_id} не найдена. Попробуйте еще раз.')
                    update.message.reply_text('Введите № записи для удаления или напишите "Отмена":')
                    return
                conn.commit()
                cursor.execute(f"SELECT reorder_entry_id(%s)", (user_id,))
                conn.commit()

                update.message.reply_text(f'Запись №{message_id} удалена')

                cursor.execute(f"SELECT entry_id, entry FROM checklist WHERE user_id = %s ORDER BY entry_id", (user_id,))
                results = cursor.fetchall()

                task_list = "\n".join([f"{task[0]}. {task[1]}" for task in results])
                task_list = "`" + task_list + "`"
                update.message.reply_text(task_list, parse_mode='MarkdownV2')

                cursor.close()
                conn.close()
                context.user_data['awaiting_delete_id'] = False
                break
            elif text == 'Отмена':
                update.message.reply_text('Удаление отменено.')
                context.user_data['awaiting_delete_id'] = False
                break
            else:
                update.message.reply_text('Пожалуйста, введите корректный номер!')
                update.message.reply_text('Введите № записи для удаления или напишите "Отмена":')
                return
    elif text == 'Статистика':
        statistic(update, context)
    else:
        save_message(update, context)

def is_numeric(s):
    try:
        int(s)
        return True
    except ValueError:
        return False



def main() -> None:
    logger.info('Запуск бота')

    # Создание updater и диспетчера
    updater = Updater(token)
    dispatcher = updater.dispatcher
    

    # Обработчики команд и сообщений
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    # Запуск бота
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
