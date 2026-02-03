import requests
import json
import os
import logging
import datetime
from typing import Dict, List, Optional, Tuple
from pypushdeer import PushDeer

# ================== 时间（北京时间日志） ==================
def beijing_time_converter(timestamp):
    utc_dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
    beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
    beijing_dt = utc_dt.astimezone(beijing_tz)
    return beijing_dt.timetuple()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    if hasattr(handler, 'formatter') and handler.formatter:
        handler.formatter.converter = beijing_time_converter

logger = logging.getLogger(__name__)

# ================== ENV ==================
ENV_PUSH_KEY = "PUSHDEER_SENDKEY"
ENV_EXCHANGE_PLAN = "GLADOS_EXCHANGE_PLAN"
ENV_ENABLE_EXCHANGE = "GLADOS_ENABLE_EXCHANGE"
ENV_TG_TOKEN = "TG_BOT_TOKEN"
ENV_TG_CHAT_ID = "TG_CHAT_ID"

# ================== API ==================
CHECKIN_URL = "https://glados.cloud/api/user/checkin"
STATUS_URL = "https://glados.cloud/api/user/status"
POINTS_URL = "https://glados.cloud/api/user/points"
EXCHANGE_URL = "https://glados.cloud/api/user/exchange"

CHECKIN_DATA = {"token": "glados.cloud"}

HEADERS_TEMPLATE = {
    'referer': 'https://glados.cloud/console/checkin',
    'origin': "https://glados.cloud",
    'user-agent': "Mozilla/5.0",
    'content-type': 'application/json;charset=UTF-8'
}

EXCHANGE_POINTS = {"plan100": 100, "plan200": 200, "plan500": 500}

# ================== 读取账号（_1 _2 _3） ==================
def load_accounts() -> List[Dict[str, str]]:
    accounts = []
    idx = 1
    while True:
        email = os.environ.get(f"GLADOS_EMAILS_{idx}")
        cookie = os.environ.get(f"GLADOS_COOKIES_{idx}")
        if not email or not cookie:
            break
        accounts.append({"email": email.strip(), "cookie": cookie.strip()})
        idx += 1
    return accounts

# ================== 配置 ==================
def load_config():
    push_key = os.environ.get(ENV_PUSH_KEY, "")
    exchange_plan = os.environ.get(ENV_EXCHANGE_PLAN, "plan500")
    tg_token = os.environ.get(ENV_TG_TOKEN, "")
    tg_chat_id = os.environ.get(ENV_TG_CHAT_ID, "")

    enable_exchange_env = os.environ.get(ENV_ENABLE_EXCHANGE, "false").lower()
    enable_exchange = enable_exchange_env in ("1", "true", "yes")

    accounts = load_accounts()

    logger.info(f"账号数量: {len(accounts)}")
    logger.info(f"兑换开关: {'开启' if enable_exchange else '关闭'}")

    return push_key, exchange_plan, tg_token, tg_chat_id, accounts, enable_exchange

# ================== HTTP ==================
def make_request(url, method, headers, data=None, cookie=""):
    h = headers.copy()
    h["cookie"] = cookie
    try:
        if method == "POST":
            r = requests.post(url, headers=h, data=json.dumps(data))
        else:
            r = requests.get(url, headers=h)
        return r if r.ok else None
    except Exception as e:
        logger.error(f"请求失败: {e}")
        return None

# ================== 单账号处理 ==================
def process_account(account, exchange_plan, do_exchange):
    cookie = account["cookie"]

    status, points, days, total_points, exchange = "签到失败", "0", "-", "-", "未执行兑换"

    r = make_request(CHECKIN_URL, "POST", HEADERS_TEMPLATE, CHECKIN_DATA, cookie)
    if r:
        j = r.json()
        msg = j.get("message", "")
        points = str(j.get("points", 0))
        if "Got" in msg:
            status = f"签到成功"
        elif "Repeats" in msg:
            status = "重复签到，明天再来"
            points = "0"
        else:
            status = f"签到失败"

    r = make_request(STATUS_URL, "GET", HEADERS_TEMPLATE, cookie=cookie)
    if r:
        try:
            days = f"{int(float(r.json()['data']['leftDays']))} 天"
        except:
            pass

    r = make_request(POINTS_URL, "GET", HEADERS_TEMPLATE, cookie=cookie)
    current_points = 0
    if r:
        try:
            current_points = int(float(r.json().get("points", 0)))
            total_points = f"{current_points} 积分"
        except:
            pass

    if do_exchange:
        need = EXCHANGE_POINTS.get(exchange_plan, 500)
        if current_points >= need:
            r = make_request(EXCHANGE_URL, "POST", HEADERS_TEMPLATE,
                             {"planType": exchange_plan}, cookie)
            if r and r.json().get("code") == 0:
                exchange = f"兑换成功：{exchange_plan}"
            else:
                exchange = f"兑换失败：{exchange_plan}"
        else:
            exchange = f"积分不足，未兑换：{exchange_plan}"

    return status, points, days, total_points, exchange

# ================== 推送格式 ==================
def format_message(results):
    title = f"GLaDOS 签到结果（{len(results)} 账号）"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"📧 {r['email']} | P:{r['points']} 剩余天数:{r['days']} "
            f"总积分:{r['total']} | {r['status']}; {r['exchange']}"
        )
    return title, "\n".join(lines)

# ================== TG ==================
def send_tg(token, chat_id, text):
    if not token or not chat_id:
        return
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )

# ================== MAIN ==================
def main():
    push_key, exchange_plan, tg_token, tg_chat_id, accounts, enable_exchange = load_config()
    results = []

    for acc in accounts:
        status, points, days, total, exchange = process_account(
            acc, exchange_plan, enable_exchange
        )
        results.append({
            "email": acc["email"],
            "status": status,
            "points": points,
            "days": days,
            "total": total,
            "exchange": exchange
        })

    title, content = format_message(results)

    if push_key:
        PushDeer(pushkey=push_key).send_text(title, desp=content)

    send_tg(tg_token, tg_chat_id, f"{title}\n\n{content}")

if __name__ == "__main__":
    main()
