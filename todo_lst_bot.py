import logging
import psycopg2
from psycopg2 import sql
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import json


# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
stand = 'dev'

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
    reply_keyboard = [['Вывести список'], ['Удалить запись']]
    update.message.reply_text(
        'Привет! Отправь мне сообщение, и я запишу его в базу данных.',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=False)
    )

# Функция для записи сообщения в базу данных
def save_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    message_text = update.message.text
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO checklist (entry, user_id) VALUES (%s, %s)", (message_text, user_id))
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
    update.message.reply_text('Введите № записи, которую хотите удалить:')
    context.user_data['awaiting_delete_id'] = True
    

# Обработка текстовых сообщений
def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    text = update.message.text

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
                    update.message.reply_text('Введите № записи для удаления:')
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
            else:
                update.message.reply_text('Пожалуйста, введите корректный номер!')
                update.message.reply_text('Введите ID записи для удаления:')
                return
    else:
        save_message(update, context)

def is_numeric(s):
    try:
        int(s)
        return True
    except ValueError:
        return False



def main() -> None:
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
