
import os
import sys
import time
import random
import requests
from pypushdeer import PushDeer

CHECKIN_URL = "https://glados.space/api/user/checkin"
STATUS_URL = "https://glados.space/api/user/status"

HEADERS_BASE = {
    "origin": "https://glados.space",
    "referer": "https://glados.space/console/checkin",
    "user-agent": "GLaDOS-Checkin/1.0",
    "content-type": "application/json;charset=UTF-8",
}

PAYLOAD = {"token": "glados.one"}
TIMEOUT = 15
MAX_ATTEMPTS = 3


def push(key, title, content):
    if not key:
        print("未配置 SENDKEY，跳过通知")
        return

    try:
        PushDeer(pushkey=key).send_text(
            title, desp=content
        )
        print("推送请求已发送")
    except Exception as exc:
        print(f"推送失败: {type(exc).__name__}")


def request_json(session, method, url, headers, **kwargs):
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = session.request(
                method,
                url,
                headers=headers,
                timeout=TIMEOUT,
                **kwargs
            )

            # 仅对临时 HTTP 错误进行重试
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(2 ** attempt + random.random())
                    continue

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, dict):
                raise ValueError("接口返回格式异常")

            return data

        except (requests.RequestException, ValueError):
            if attempt == MAX_ATTEMPTS - 1:
                raise
            time.sleep(2 ** attempt + random.random())


def get_status(session, headers):
    try:
        data = request_json(
            session, "GET", STATUS_URL, headers
        ).get("data") or {}

        email = str(data.get("email") or "unknown")
        left = data.get("leftDays")

        if left is None:
            days = "-"
        else:
            days = f"{int(float(left))} 天"

        return email, days

    except Exception as exc:
        print(f"状态查询失败: {type(exc).__name__}")
        return "unknown", "-"


def checkin(session, headers):
    try:
        data = request_json(
            session,
            "POST",
            CHECKIN_URL,
            headers,
            json=PAYLOAD
        )

        code = data.get("code")
        reason = str(data.get("reason") or "").lower()
        message = str(data.get("message") or "")
        lower = message.lower()

        # Cloudflare 验证失败：不重复发送相同请求
        if reason == "turnstile":
            return "blocked", 0, "需要 Cloudflare 验证"

        # 已签到
        if "repeat" in lower or "already" in lower:
            return "repeat", 0, "今日已签到"

        # 保留旧版成功响应兼容性
        # 成功条件仍需通过实际成功响应确认
        if "got" in lower and code in (0, 1, None):
            points = data.get("points") or 0
            return "success", points, "签到成功"

        print(
            f"接口业务响应: code={code}, "
            f"reason={reason}, message={message[:150]}"
        )
        return "failed", 0, "接口未确认签到成功"

    except Exception as exc:
        print(f"签到异常: {type(exc).__name__}")
        return "failed", 0, "请求异常"


def main():
    sendkey = os.getenv("SENDKEY", "").strip()
    cookies_env = os.getenv("COOKIES", "")

    cookies = [
        item.strip()
        for item in cookies_env.split("&")
        if item.strip()
    ]

    if not cookies:
        print("错误：未配置 COOKIES")
        push(sendkey, "GLaDOS 签到失败", "未配置 COOKIES")
        return 1

    counts = {
        "success": 0,
        "repeat": 0,
        "blocked": 0,
        "failed": 0,
    }

    lines = []

    for idx, cookie in enumerate(cookies, 1):
        print(f"开始处理账号 {idx}")

        headers = dict(HEADERS_BASE)
        headers["cookie"] = cookie

        # 每个账号使用独立 Session
        with requests.Session() as session:
            result, points, detail = checkin(
                session, headers
            )

            email, days = get_status(
                session, headers
            )

        counts[result] += 1

        symbols = {
            "success": "✅",
            "repeat": "🔁",
            "blocked": "🔐",
            "failed": "❌",
        }

        line = (
            f"{idx}. {email} | "
            f"{symbols[result]} {detail} | "
            f"积分:{points} | 剩余:{days}"
        )

        print(line)
        lines.append(line)

        if idx < len(cookies):
            time.sleep(random.uniform(1, 2))

    title = (
        f"GLaDOS 签到 "
        f"成功{counts['success']} "
        f"已签{counts['repeat']} "
        f"验证{counts['blocked']} "
        f"失败{counts['failed']}"
    )

    content = "\n".join(lines)

    print("\n===== 签到汇总 =====")
    print(content)

    push(sendkey, title, content)

    if counts["blocked"] or counts["failed"]:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
