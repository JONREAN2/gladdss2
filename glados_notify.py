import requests
import json
import os
import logging
import datetime
from typing import List, Dict
from pypushdeer import PushDeer

# ================== 北京时间日志 ==================
def beijing_time_converter(timestamp):
    utc_dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
    bj_tz = datetime.timezone(datetime.timedelta(hours=8))
    return utc_dt.astimezone(bj_tz).timetuple()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
for h in logging.getLogger().handlers:
    if h.formatter:
        h.formatter.converter = beijing_time_converter
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

HEADERS = {
    "origin": "https://glados.cloud",
    "referer": "https://glados.cloud/console/checkin",
    "user-agent": "Mozilla/5.0",
    "content-type": "application/json;charset=UTF-8"
}

EXCHANGE_POINTS = {
    "plan100": 100,
    "plan200": 200,
    "plan500": 500
}

# ================== 读取账号 ==================
def load_accounts() -> List[Dict[str, str]]:
    accounts = []
    idx = 1
    while True:
        email = os.environ.get(f"GLADOS_EMAILS_{idx}")
        cookie = os.environ.get(f"GLADOS_COOKIES_{idx}")
        if not email or not cookie:
            break
        accounts.append({
            "email": email.strip(),
            "cookie": cookie.strip()
        })
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

    logger.info(f"加载账号数量: {len(accounts)}")
    logger.info(f"兑换功能: {'开启' if enable_exchange else '关闭'}")

    return push_key, exchange_plan, tg_token, tg_chat_id, accounts, enable_exchange

# ================== HTTP ==================
def request(url, method="GET", data=None, cookie=""):
    h = HEADERS.copy()
    h["cookie"] = cookie
    try:
        if method == "POST":
            r = requests.post(url, headers=h, data=json.dumps(data))
        else:
            r = requests.get(url, headers=h)
        return r if r.ok else None
    except Exception as e:
        logger.error(f"请求异常: {e}")
        return None

# ================== 单账号处理 ==================
def process_account(acc, exchange_plan, do_exchange):
    cookie = acc["cookie"]

    status = "签到失败"
    points = "0"
    total = "0 积分"

    r = request(CHECKIN_URL, "POST", CHECKIN_DATA, cookie)
    if r:
        j = r.json()
        msg = j.get("message", "")
        points = str(j.get("points", 0))
        if "Got" in msg:
            status = "签到成功"
        elif "Repeats" in msg:
            status = "重复签到，明天再来"
            points = "0"

    current_points = 0
    r = request(POINTS_URL, cookie=cookie)
    if r:
        try:
            current_points = int(float(r.json().get("points", 0)))
            total = f"{current_points} 积分"
        except:
            pass

    return {
        "email": acc["email"],
        "status": status,
        "points": points,
        "total": total,
        "total_num": current_points
    }

# ================== 排序 ==================
def sort_by_total_points(results):
    return sorted(results, key=lambda x: x.get("total_num", 0), reverse=True)

# ================== 消息格式 ==================
def format_message(results):
    results = sort_by_total_points(results)

    title = f"GLaDOS 签到结果（{len(results)} 账号）"
    blocks = []

    for r in results:
        mark = " ✅" if r["total_num"] >= 500 else ""
        block = (
            f"📧 {r['email']}\n"
            f"【总积分:{r['total']}】{mark}\n"
            f"P:{r['points']}  {r['status']}"
        )
        blocks.append(block)

    return title, "\n\n".join(blocks)

# ================== Telegram ==================
def send_tg(token, chat_id, text):
    if not token or not chat_id:
        return
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text
        }
    )

# ================== MAIN ==================
def main():
    push_key, exchange_plan, tg_token, tg_chat_id, accounts, enable_exchange = load_config()
    results = []

    for acc in accounts:
        results.append(process_account(acc, exchange_plan, enable_exchange))

    title, content = format_message(results)

    if push_key:
        PushDeer(pushkey=push_key).send_text(title, desp=content)

    send_tg(tg_token, tg_chat_id, f"{title}\n\n{content}")

if __name__ == "__main__":
    main()
