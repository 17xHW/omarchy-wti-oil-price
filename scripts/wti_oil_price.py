#!/usr/bin/env python3
"""Fetch and format the front-month WTI future (Yahoo Finance CL=F)."""

import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request


URL = "https://query1.finance.yahoo.com/v8/finance/chart/CL=F?interval=1m&range=1d"
ALERT_THRESHOLD_PERCENT = 1.5
ALERT_COOLDOWN_SECONDS = 600
STALE_AFTER_SECONDS = 30 * 60
MAX_RESPONSE_BYTES = 1024 * 1024


def state_file_path():
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return os.path.join(runtime_dir, "omarchy-wti-oil-price-alert.json")
    return os.path.join(tempfile.gettempdir(), f"omarchy-wti-oil-price-alert-{os.getuid()}.json")


STATE_FILE = state_file_path()


def emit(text, tooltip, color="", accent_text=""):
    print(json.dumps({"text": text, "tooltip": tooltip, "color": color, "accentText": accent_text}))


def read_json_response(response):
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            reported_size = int(content_length)
        except (TypeError, ValueError):
            reported_size = None
        if reported_size is not None and reported_size > MAX_RESPONSE_BYTES:
            raise ValueError("Yahoo Finance response is too large")

    payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("Yahoo Finance response is too large")
    return json.loads(payload)


def read_market_data():
    request = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = read_json_response(response)

    result = data["chart"]["result"][0]
    meta = result["meta"]
    current_price = float(meta["regularMarketPrice"])
    previous_close = float(meta["previousClose"])
    trade_time = int(meta["regularMarketTime"])
    timestamps = result.get("timestamp", [])
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    points = [(timestamp, price) for timestamp, price in zip(timestamps, closes) if price is not None]
    return current_price, previous_close, trade_time, points


def format_age(seconds):
    minutes = max(1, int(seconds // 60))
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''}"


def stale_reason(trade_time, points, now=None):
    if not points:
        return "Yahoo returned no intraday price samples"

    checked_at = time.time() if now is None else now
    latest_time = points[-1][0]
    age = max(0, checked_at - latest_time)
    if age > STALE_AFTER_SECONDS:
        return f"Yahoo's latest intraday quote is {format_age(age)} old"

    if trade_time and checked_at - trade_time > STALE_AFTER_SECONDS:
        return f"Yahoo's market timestamp is {format_age(checked_at - trade_time)} old"

    return ""


def ten_minute_change(points):
    latest_time, latest_price = points[-1]
    target_time = latest_time - 600
    historical_time, historical_price = min(points, key=lambda point: abs(point[0] - target_time))
    if latest_time - historical_time < 300:
        return 0.0
    return (latest_price - historical_price) / historical_price * 100


def read_alert_state():
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor = os.open(STATE_FILE, flags)
    try:
        file_info = os.fstat(descriptor)
        unsafe_mode = file_info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        if (
            not stat.S_ISREG(file_info.st_mode)
            or file_info.st_uid != os.getuid()
            or file_info.st_nlink != 1
            or unsafe_mode
        ):
            raise OSError("unsafe alert state file")
        with os.fdopen(descriptor, encoding="utf-8") as state:
            descriptor = -1
            return json.load(state)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def write_alert_state(latest_price):
    directory = os.path.dirname(STATE_FILE)
    prefix = f".{os.path.basename(STATE_FILE)}."
    descriptor, temporary_path = tempfile.mkstemp(prefix=prefix, dir=directory)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as state:
            descriptor = -1
            json.dump({"time": time.time(), "price": latest_price}, state)
            state.flush()
            os.fsync(state.fileno())
        os.replace(temporary_path, STATE_FILE)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def should_alert(latest_price, change):
    if abs(change) < ALERT_THRESHOLD_PERCENT:
        return False
    try:
        previous = read_alert_state()
    except (OSError, ValueError):
        previous = {}

    elapsed = time.time() - float(previous.get("time", 0))
    old_price = float(previous.get("price", 0))
    movement = abs((latest_price - old_price) / old_price * 100) if old_price else 100
    if elapsed <= ALERT_COOLDOWN_SECONDS and movement < 1.0:
        return False

    try:
        write_alert_state(latest_price)
    except OSError:
        pass
    return True


def notify(latest_price, change):
    rising = change > 0
    direction = "jumped 📈" if rising else "dropped 📉"
    color = "#2ecc71" if rising else "#e74c3c"
    message = (
        f"<font color='{color}'><b>WTI Crude Oil has {direction} by "
        f"{change:+.2f}%! Current price: ${latest_price:.2f} USD.</b></font>"
    )
    try:
        subprocess.run(["pw-play", "/usr/share/sounds/alsa/Front_Center.wav"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["notify-send", "-u", "critical", "WTI Crude Oil Alert", message], check=False)
    except OSError:
        pass


def main():
    try:
        current_price, previous_close, trade_time, points = read_market_data()
    except Exception as error:
        emit("WTI unavailable", f"Could not fetch WTI price: {error}")
        return

    stale = stale_reason(trade_time, points)
    if stale:
        color = "#f2c94c"
        text = f"WTI ${current_price:.2f} STALE"
        tooltip = (
            f"WTI Crude Oil front-month future (Yahoo Finance): ${current_price:.2f} USD\n"
            "Status: STALE — market closed or Yahoo data delayed\n"
            f"Reason: {stale}.\n"
            f"Last Yahoo timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(trade_time))}\n\n"
            "The displayed price is the last value Yahoo supplied. Alerts are paused until fresh intraday data returns."
        )
        emit(text, tooltip, color, "STALE")
        return

    change_10m = ten_minute_change(points)
    if should_alert(current_price, change_10m):
        notify(current_price, change_10m)

    daily_change = (current_price - previous_close) / previous_close * 100
    color = "#2ecc71" if daily_change > 0 else "#e74c3c" if daily_change < 0 else "#7f8c8d"
    sign = "+" if daily_change > 0 else ""
    text = f"WTI ${current_price:.2f} {sign}{daily_change:.2f}%"
    tooltip = (
        f"WTI Crude Oil front-month future (Yahoo Finance): ${current_price:.2f} USD\n"
        f"Previous close: ${previous_close:.2f}\n"
        f"Daily change: {sign}{daily_change:.2f}%\n"
        f"10-minute change: {change_10m:+.2f}%\n"
        f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(trade_time))}\n\n"
        "Click to refresh. Alerts fire for a 1.5% move over roughly 10 minutes."
    )
    emit(text, tooltip, color, f"{sign}{daily_change:.2f}%")


if __name__ == "__main__":
    main()
