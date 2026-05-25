```python
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
ENV_TG_TOKEN = "TG_BOT_TOKEN"
ENV_TG_CHAT_ID = "TG_CHAT_ID"

# ================== 写死兑换配置 ==================
ENABLE_EXCHANGE = True
EXCHANGE_PLAN = "plan500"

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
    tg_token = os.environ.get(ENV_TG_TOKEN, "")
    tg_chat_id = os.environ.get(ENV_TG_CHAT_ID, "")

    accounts = load_accounts()

    logger.info(f"加载账号数量: {len(accounts)}")
    logger.info(f"兑换功能: {'开启' if ENABLE_EXCHANGE else '关闭'}")
    logger.info(f"兑换套餐: {EXCHANGE_PLAN}")

    return push_key, tg_token, tg_chat_id, accounts

# ================== HTTP ==================
def request(url, method="GET", data=None, cookie=""):
    h = HEADERS.copy()
    h["cookie"] = cookie

    try:
        if method == "POST":
            r = requests.post(
                url,
                headers=h,
                data=json.dumps(data),
                timeout=15
            )
        else:
            r = requests.get(
                url,
                headers=h,
                timeout=15
            )

        return r if r.ok else None

    except Exception as e:
        logger.error(f"请求异常: {e}")
        return None

# ================== 单账号处理 ==================
def process_account(acc, do_exchange=False):
    cookie = acc["cookie"]

    status = "签到失败"
    points = "0"
    total = "0 积分"
    exchange_status = "未执行兑换"

    # 签到
    r = request(CHECKIN_URL, "POST", CHECKIN_DATA, cookie)

    if r:
        try:
            j = r.json()

            msg = j.get("message", "")
            points = str(j.get("points", 0))

            if "Got" in msg:
                status = "签到成功"

            elif "Repeats" in msg:
                status = "重复签到，明天再来"
                points = "0"

            else:
                status = msg or status

        except Exception:
            status = "签到解析失败"

    # 查询积分
    current_points = 0

    r = request(POINTS_URL, cookie=cookie)

    if r:
        try:
            current_points = int(float(r.json().get("points", 0)))
            total = f"{current_points} 积分"

        except Exception:
            pass

    # ================== 兑换 ==================
    if do_exchange and ENABLE_EXCHANGE:

        need_points = EXCHANGE_POINTS.get(EXCHANGE_PLAN, 500)

        if current_points >= need_points:

            r = request(
                EXCHANGE_URL,
                "POST",
                {"planType": EXCHANGE_PLAN},
                cookie
            )

            if r:
                try:
                    j = r.json()

                    code = j.get("code", -1)
                    msg = str(j.get("message", ""))

                    if code == 0:
                        exchange_status = f"兑换{need_points}成功"

                    else:
                        exchange_status = (
                            f"兑换{need_points}失败({code}) {msg}"
                        )

                except Exception:
                    exchange_status = "兑换解析失败"

            else:
                exchange_status = "兑换请求失败"

        else:
            exchange_status = f"积分不足{need_points}"

    return {
        "email": acc["email"],
        "cookie": cookie,
        "status": status,
        "points": points,
        "total": total,
        "total_num": current_points,
        "exchange_status": exchange_status
    }

# ================== 排序 ==================
def sort_by_total_points(results):
    return sorted(
        results,
        key=lambda x: x.get("total_num", 0),
        reverse=True
    )

# ================== 消息格式 ==================
def format_message(results):
    title = f"GLaDOS 签到结果（{len(results)} 账号）"

    blocks = []

    for idx, r in enumerate(results, 1):

        crown = "🏆 排名第一\n" if idx == 1 else ""

        mark = " ✅" if r["total_num"] >= 500 else ""

        block = (
            f"{crown}"
            f"📧 {r['email']}\n"
            f"【总积分:{r['total']}】{mark}\n"
            f"P:{r['points']}  {r['status']}\n"
            f"兑换状态:{r['exchange_status']}"
        )

        blocks.append(block)

    return title, "\n\n".join(blocks)

# ================== Telegram ==================
def send_tg(token, chat_id, text):

    if not token or not chat_id:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text
            },
            timeout=10
        )

    except Exception:
        pass

# ================== MAIN ==================
def main():

    push_key, tg_token, tg_chat_id, accounts = load_config()

    results = []

    # ================== 先全部查询 ==================
    for acc in accounts:
        results.append(process_account(acc, False))

    # ================== 按积分排序 ==================
    results = sort_by_total_points(results)

    # ================== 只给第一名兑换 ==================
    if ENABLE_EXCHANGE and results:

        top_acc = {
            "email": results[0]["email"],
            "cookie": results[0]["cookie"]
        }

        results[0] = process_account(
            top_acc,
            True
        )

        # 兑换后重新排序
        results = sort_by_total_points(results)

    # ================== 推送 ==================
    title, content = format_message(results)

    print(title)
    print(content)

    # PushDeer
    if push_key:
        try:
            PushDeer(
                pushkey=push_key
            ).send_text(
                title,
                desp=content
            )

        except Exception:
            pass

    # Telegram
    send_tg(
        tg_token,
        tg_chat_id,
        f"{title}\n\n{content}"
    )

if __name__ == "__main__":
    main()
```
