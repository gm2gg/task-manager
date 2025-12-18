import sqlite3
import telebot
import threading
import schedule
import time
from datetime import datetime
from telebot import types
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
bot = telebot.TeleBot(ENTER_BOT_TOKEN)
USER_IDS = set()
HOST = '0.0.0.0'
PORT = 5000


def init_database():
    try:
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_settings'")
        if not cursor.fetchone():
            cursor.execute('''
                CREATE TABLE user_settings (
                    user_id INTEGER PRIMARY KEY,
                    theme TEXT DEFAULT 'light',
                    notifications_enabled BOOLEAN DEFAULT 1,
                    notification_time TEXT DEFAULT '12:00',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            print("Created user_settings table")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        if not cursor.fetchone():
            cursor.execute('''
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    priority TEXT CHECK(priority IN ('low', 'medium', 'high')) DEFAULT 'medium',
                    start_date DATE,
                    end_date DATE,
                    complexity TEXT CHECK(complexity IN ('easy', 'medium', 'hard')) DEFAULT 'medium',
                    assignee TEXT,
                    status TEXT CHECK(status IN ('new', 'progress', 'done')) DEFAULT 'new',
                    task_group TEXT DEFAULT 'no-group',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            print("Created tasks table")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_groups'")
        if not cursor.fetchone():
            cursor.execute('''
                CREATE TABLE task_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    group_name TEXT NOT NULL,
                    description TEXT,
                    color TEXT DEFAULT '#3498db',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, group_name)
                )
            ''')
            print("Created task_groups table")

        conn.commit()
        conn.close()
        print("Database checked")
    except Exception as e:
        print(f"Database check error: {e}")


def save_task(user_id, title, description, priority, start_date, end_date, complexity, assignee, status,
              task_group='no-group'):
    try:
        print(f"Saving task for user_id: {user_id}")

        if not title or not title.strip():
            print(f"Empty task title for user {user_id}")
            return False

        def validate_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.strptime(date_str, '%Y-%m-%d').date().isoformat()
            except ValueError:
                print(f"Invalid date format: {date_str}")
                return None

        start_date = validate_date(start_date)
        end_date = validate_date(end_date)

        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('''
                INSERT INTO tasks (user_id, title, description, priority, start_date, end_date, complexity, assignee, status, task_group)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
            user_id,
            title.strip(),
            description.strip() if description else '',
            priority if priority in ['low', 'medium', 'high'] else 'medium',
            start_date,
            end_date,
            complexity if complexity in ['easy', 'medium', 'hard'] else 'medium',
            assignee.strip() if assignee else '',
            status if status in ['new', 'progress', 'done'] else 'new',
            task_group
        ))
        conn.commit()
        task_id = cursor.lastrowid
        print(f"Task saved with ID: {task_id}")
        conn.close()
        return True

    except Exception as e:
        print(f"Error saving task: {e}")
        return False


def get_tasks_by_user(user_id):
    try:
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
        tasks = cursor.fetchall()
        conn.close()
        print(f"Found tasks for user {user_id}: {len(tasks)}")
        return tasks
    except Exception as e:
        print(f"Error getting tasks: {e}")
        return []


def update_task_status(task_id, new_status):
    try:
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            print(f"Task with ID {task_id} not found")
            return False
        cursor.execute('UPDATE tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                       (new_status, task_id))
        conn.commit()
        conn.close()
        print(f"Task {task_id} status updated to: {new_status}")
        return True
    except Exception as e:
        print(f"Error updating status: {e}")
        return False


def delete_task(task_id):
    try:
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            print(f"Task with ID {task_id} not found")
            return False
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
        print(f"Task {task_id} deleted")
        return True
    except Exception as e:
        print(f"Error deleting task: {e}")
        return False


def get_task_statistics(user_id):
    try:
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new
            FROM tasks WHERE user_id = ?
        ''', (user_id,))
        stats = cursor.fetchone()
        cursor.execute('SELECT priority, COUNT(*) FROM tasks WHERE user_id = ? GROUP BY priority', (user_id,))
        priority_stats = dict(cursor.fetchall())
        cursor.execute('SELECT assignee, COUNT(*) FROM tasks WHERE user_id = ? AND assignee != "" GROUP BY assignee',
                       (user_id,))
        assignee_stats = dict(cursor.fetchall())
        conn.close()
        result = {
            'total': stats[0],
            'completed': stats[1],
            'in_progress': stats[2],
            'new': stats[3],
            'completion_rate': round((stats[1] / stats[0] * 100) if stats[0] > 0 else 0, 1),
            'by_priority': priority_stats,
            'by_assignee': assignee_stats
        }
        print(f"Statistics for user {user_id}: {result}")
        return result
    except Exception as e:
        print(f"Error getting statistics: {e}")
        return {'total': 0, 'completed': 0, 'in_progress': 0, 'new': 0, 'completion_rate': 0, 'by_priority': {},
                'by_assignee': {}}


def get_user_settings(user_id):
    try:
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM user_settings WHERE user_id = ?', (user_id,))
        settings = cursor.fetchone()
        conn.close()

        if settings:
            return {
                'user_id': settings[0],
                'theme': settings[1],
                'notifications_enabled': bool(settings[2]),
                'notification_time': settings[3]
            }
        else:
            return {
                'user_id': user_id,
                'theme': 'light',
                'notifications_enabled': True,
                'notification_time': '12:00'
            }
    except Exception as e:
        print(f"Error getting settings: {e}")
        return None


def save_user_settings(user_id, theme, notifications_enabled, notification_time):
    try:
        if notification_time:
            try:
                datetime.strptime(notification_time, '%H:%M')
            except ValueError:
                notification_time = '12:00'
                print(f"Invalid time, set to default: 12:00")

        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_settings
            (user_id, theme, notifications_enabled, notification_time, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, theme, 1 if notifications_enabled else 0, notification_time))
        conn.commit()
        conn.close()
        print(f"Settings saved for user {user_id}")
        return True
    except Exception as e:
        print(f"Error saving settings for {user_id}: {e}")
        return False


def send_daily_reminders():
    try:
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()

        cursor.execute('''
            SELECT us.user_id, us.notification_time
            FROM user_settings us
            WHERE us.notifications_enabled = 1
        ''')
        users = cursor.fetchall()

        print(f"Users with notifications: {len(users)}")

        for user_id, notification_time in users:
            print(f"Checking user {user_id}")

            cursor.execute('''
                SELECT COUNT(*)
                FROM tasks
                WHERE user_id = ? AND status IN ('new', 'progress')
            ''', (user_id,))

            active_tasks_count = cursor.fetchone()[0]

            if active_tasks_count == 0:
                print(f"User {user_id} has no active tasks - skipping")
                continue

            print(f"User {user_id} active tasks: {active_tasks_count}")

            current_time = datetime.now().strftime('%H:%M')

            if current_time == notification_time:
                print(f"Time matched! Sending notification to user {user_id}")

                try:
                    chat = bot.get_chat(user_id)
                    user_language = chat.language_code if hasattr(chat, 'language_code') else 'en'
                except:
                    user_language = 'en'

                if user_language and user_language.startswith('ru'):
                    message = f"У вас остались не законченные задачи\n\nВсего активных задач: {active_tasks_count}\nНе забудьте поработать над ними!"
                else:
                    message = f"You have unfinished tasks\n\nTotal active tasks: {active_tasks_count}\nDon't forget to work on them!"

                try:
                    bot.send_message(user_id, message)
                    print(f"Notification sent to user {user_id}")
                except Exception as e:
                    print(f"Error sending to user {user_id}: {e}")
            else:
                print(f"Time not matched: {current_time} != {notification_time}")

        conn.close()

    except Exception as e:
        print(f"Reminder system error: {e}")


def run_scheduler():
    schedule.every(1).minutes.do(send_daily_reminders)

    print("Notification scheduler started")

    while True:
        schedule.run_pending()
        time.sleep(1)


@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    global USER_IDS

    user_language = message.from_user.language_code if message.from_user.language_code else 'en'

    if user_language.startswith('ru'):
        welcome_msg = "Привет! Добро пожаловать в Do-Lister!\n\nНажми кнопку ниже чтобы начать:"
        welcome_back_msg = "С возвращением! Do-Lister готов к работе!"
    else:
        welcome_msg = "Hello! Welcome to Do-Lister!\n\nClick button below to start:"
        welcome_back_msg = "Welcome back! Do-Lister is ready to work!"

    if user_id in USER_IDS:
        print(f"User {user_id} already exists, updating keyboard")

        keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        button2 = types.KeyboardButton("Do-Lister", web_app=types.WebAppInfo(
            url=f"https://gm2gg.github.io/task-manager?user_id={user_id}"
        ))
        keyboard.add(button2)

        bot.send_message(
            message.chat.id,
            welcome_back_msg,
            reply_markup=keyboard
        )
        return

    USER_IDS.add(user_id)
    print(f"NEW user added ID: {user_id}")
    print(f"Total users: {len(USER_IDS)}")

    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    button2 = types.KeyboardButton("Do-Lister", web_app=types.WebAppInfo(
        url=f"https://gm2gg.github.io/task-manager?user_id={user_id}"
    ))
    keyboard.add(button2)

    bot.send_message(
        message.chat.id,
        welcome_msg,
        reply_markup=keyboard
    )

    try:
        settings = get_user_settings(user_id)
        if settings and settings.get('user_id'):
            print(f"Settings for user {user_id} already exist")
        else:
            save_user_settings(user_id, 'light', True, '12:00')
            print(f"Default settings created for user {user_id}")
    except Exception as e:
        print(f"Error creating settings for {user_id}: {e}")


def is_authorized_user(user_id):
    user_id = int(user_id)

    if user_id in USER_IDS:
        return True

    try:
        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()

        cursor.execute('SELECT 1 FROM tasks WHERE user_id = ? LIMIT 1', (user_id,))
        has_tasks = cursor.fetchone()

        if not has_tasks:
            cursor.execute('SELECT 1 FROM user_settings WHERE user_id = ? LIMIT 1', (user_id,))
            has_tasks = cursor.fetchone()

        conn.close()

        if has_tasks:
            USER_IDS.add(user_id)
            return True

    except Exception as e:
        print(f"Error: {e}")

    return False


@app.route('/auth_user', methods=['POST'])
def auth_user():
    try:
        data = request.json
        user_id = data.get('user_id')

        if not user_id:
            return jsonify({'error': 'User ID required'}), 400

        user_id = int(user_id)
        USER_IDS.add(user_id)

        return jsonify({'status': 'success'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/get_tasks', methods=['GET'])
def get_tasks():
    try:
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400

        if not is_authorized_user(user_id):
            return jsonify({'error': 'User not authorized'}), 401

        tasks = get_tasks_by_user(user_id)
        print(f"Loaded tasks for user {user_id}: {len(tasks)}")
        return jsonify(tasks)
    except Exception as e:
        print(f"Error getting tasks: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/save_task', methods=['POST'])
def save_task_from_site():
    try:
        data = request.json
        user_id = data.get('user_id')

        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400

        if not is_authorized_user(user_id):
            return jsonify({'error': 'User not authorized'}), 401

        print(f"Received task data to save: {data}")

        if not data.get('title') or not data.get('title', '').strip():
            return jsonify({'error': 'Title is required'}), 400

        result = save_task(
            user_id=user_id,
            title=data.get('title', ''),
            description=data.get('description', ''),
            priority=data.get('priority', 'medium'),
            start_date=data.get('start_date', ''),
            end_date=data.get('end_date', ''),
            complexity=data.get('complexity', 'medium'),
            assignee=data.get('assignee', ''),
            status=data.get('status', 'new'),
            task_group=data.get('group', 'no-group')
        )

        if result:
            return jsonify({'status': 'success', 'message': 'Task saved successfully'})
        else:
            return jsonify({'error': 'Failed to save task'}), 500

    except Exception as e:
        print(f"Error saving task: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/update_status', methods=['POST'])
def update_task_status_api():
    try:
        data = request.json
        task_id = data.get('task_id')
        new_status = data.get('status')
        user_id = data.get('user_id')

        if not task_id or not new_status or not user_id:
            return jsonify({'error': 'Task ID, status and user ID are required'}), 400

        if not is_authorized_user(user_id):
            return jsonify({'error': 'User not authorized'}), 401

        result = update_task_status(task_id, new_status)
        if result:
            print(f"Task {task_id} status updated to: {new_status}")
            return jsonify({'status': 'success', 'message': 'Status updated successfully'})
        else:
            return jsonify({'error': 'Task not found'}), 404

    except Exception as e:
        print(f"Error updating status: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/delete_task', methods=['POST'])
def delete_task_api():
    try:
        data = request.json
        task_id = data.get('task_id')
        user_id = data.get('user_id')

        if not task_id or not user_id:
            return jsonify({'error': 'Task ID and user ID are required'}), 400

        if not is_authorized_user(user_id):
            return jsonify({'error': 'User not authorized'}), 401

        result = delete_task(task_id)
        if result:
            print(f"Task {task_id} deleted")
            return jsonify({'status': 'success', 'message': 'Task deleted successfully'})
        else:
            return jsonify({'error': 'Task not found'}), 404

    except Exception as e:
        print(f"Error deleting task: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/get_statistics', methods=['GET'])
def get_statistics_api():
    try:
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400

        if not is_authorized_user(user_id):
            return jsonify({'error': 'User not authorized'}), 401

        statistics = get_task_statistics(user_id)
        return jsonify(statistics)
    except Exception as e:
        print(f"Error getting statistics: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/get_settings', methods=['GET'])
def get_settings_api():
    try:
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400

        if not is_authorized_user(user_id):
            return jsonify({'error': 'User not authorized'}), 401

        settings = get_user_settings(user_id)
        return jsonify(settings)
    except Exception as e:
        print(f"Error getting settings: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/save_settings', methods=['POST'])
def save_settings_api():
    try:
        data = request.json
        user_id = data.get('user_id')
        theme = data.get('theme', 'light')
        notifications_enabled = data.get('notifications_enabled', True)
        notification_time = data.get('notification_time', '12:00')

        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400

        if not is_authorized_user(user_id):
            return jsonify({'error': 'User not authorized'}), 401

        print(f"Received settings to save: user_id={user_id}")

        result = save_user_settings(user_id, theme, notifications_enabled, notification_time)
        if result:
            return jsonify({'status': 'success', 'message': 'Settings saved successfully'})
        else:
            return jsonify({'error': 'Failed to save settings'}), 500
    except Exception as e:
        print(f"Error saving settings: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/get_report', methods=['GET'])
def get_report_api():
    try:
        user_id = request.args.get('user_id', type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not user_id or not start_date or not end_date:
            return jsonify({'error': 'User ID, start_date and end_date are required'}), 400

        if not is_authorized_user(user_id):
            return jsonify({'error': 'User not authorized'}), 401

        tasks = get_tasks_by_user(user_id)

        report_tasks = []
        for task in tasks:
            task_data = {
                'id': task[0],
                'title': task[2],
                'description': task[3],
                'priority': task[4],
                'start_date': task[5],
                'end_date': task[6],
                'complexity': task[7],
                'assignee': task[8],
                'status': task[9],
                'group': task[10] if len(task) > 10 else 'no-group'
            }

            task_start = task_data['start_date']
            task_end = task_data['end_date']

            if (task_start and task_start >= start_date and task_start <= end_date) or \
                    (task_end and task_end >= start_date and task_end <= end_date) or \
                    (task_start and task_end and task_start <= start_date and task_end >= end_date):
                report_tasks.append(task_data)

        report_data = {
            'tasks': report_tasks,
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'total_tasks': len(report_tasks),
            'completed_tasks': len([t for t in report_tasks if t['status'] == 'done']),
            'in_progress_tasks': len([t for t in report_tasks if t['status'] == 'progress']),
            'new_tasks': len([t for t in report_tasks if t['status'] == 'new'])
        }

        print(f"Report generated for user {user_id}: {len(report_tasks)} tasks")
        return jsonify(report_data)

    except Exception as e:
        print(f"Error generating report: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/update_task_group', methods=['POST'])
def update_task_group():
    try:
        data = request.json
        task_id = data.get('task_id')
        new_group = data.get('group')
        user_id = data.get('user_id')

        if not task_id or not new_group or not user_id:
            return jsonify({'error': 'Task ID, group and user ID are required'}), 400

        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE tasks SET task_group = ? WHERE id = ? AND user_id = ?',
                       (new_group, task_id, user_id))
        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Task group updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'service': 'Task Manager API', 'active_users': len(USER_IDS)})


@app.route('/test_reminder/<int:user_id>', methods=['GET'])
def test_reminder(user_id):
    try:
        if not is_authorized_user(user_id):
            return jsonify({'error': 'User not authorized'}), 401

        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*)
            FROM tasks
            WHERE user_id = ? AND status IN ('new', 'progress')
        ''', (user_id,))

        active_tasks_count = cursor.fetchone()[0]
        conn.close()

        if active_tasks_count > 0:
            message = "TEST: You have unfinished tasks\n\n"
            message += f"Total active tasks: {active_tasks_count}\n"
            message += "Don't forget to work on them!"

            bot.send_message(user_id, message)
            return jsonify({'status': 'success', 'message': f'Sent reminder about {active_tasks_count} tasks'})
        else:
            return jsonify({'status': 'info', 'message': 'No active tasks found'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/save_group', methods=['POST'])
def save_group():
    try:
        data = request.json
        user_id = data.get('user_id')
        group_name = data.get('group_name')

        if not user_id or not group_name:
            return jsonify({'error': 'User ID and group name are required'}), 400

        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO task_groups (user_id, group_name)
            VALUES (?, ?)
        ''', (user_id, group_name))
        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Group saved'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/delete_group', methods=['POST'])
def delete_group():
    try:
        data = request.json
        user_id = data.get('user_id')
        group_name = data.get('group_name')

        if not user_id or not group_name:
            return jsonify({'error': 'User ID and group name are required'}), 400

        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()

        cursor.execute('UPDATE tasks SET task_group = ? WHERE user_id = ? AND task_group = ?',
                       ('no-group', user_id, group_name))

        cursor.execute('DELETE FROM task_groups WHERE user_id = ? AND group_name = ?',
                       (user_id, group_name))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Group deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/get_groups', methods=['GET'])
def get_groups():
    try:
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400

        conn = sqlite3.connect('tasks.db')
        cursor = conn.cursor()
        cursor.execute('SELECT group_name FROM task_groups WHERE user_id = ?', (user_id,))
        groups = [row[0] for row in cursor.fetchall()]
        conn.close()

        return jsonify(groups)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', 'https://gm2gg.github.io')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


@app.route('/')
def index():
    return jsonify({"message": "Do-Lister API", "status": "running"})


@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.route('/', methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def options_handler(path=None):
    return '', 200


if __name__ == '__main__':
    init_database()

    print("Server starting...")

    flask_thread = threading.Thread(
        target=app.run,
        kwargs={
            'host': HOST,
            'port': PORT,
            'debug': False,
            'use_reloader': False
        }
    )
    flask_thread.daemon = True
    flask_thread.start()

    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    print("Server started!")
    print(f"API available on port {PORT}")
    print("Telegram bot active")
    print("Notification scheduler running")
    print(f"Active users: {len(USER_IDS)}")

    try:
        bot.polling(none_stop=True, interval=0)
    except Exception as e:
        print(f"Error in Telegram bot: {e}")
