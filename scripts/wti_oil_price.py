#!/usr/bin/env python3
"""Fetch and format the front-month WTI future (Yahoo Finance CL=F)."""

import json
import os
import subprocess
import sys
import time
import urllib.request


URL = "https://query1.finance.yahoo.com/v8/finance/chart/CL=F?interval=1m&range=1d"
ALERT_THRESHOLD_PERCENT = 1.5
ALERT_COOLDOWN_SECONDS = 600
STATE_FILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "omarchy-wti-oil-price-alert.json")


def emit(text, tooltip):
    print(json.dumps({"text": text, "tooltip": tooltip}))


def read_market_data():
    request = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)

    result = data["chart"]["result"][0]
    meta = result["meta"]
    current_price = float(meta["regularMarketPrice"])
    previous_close = float(meta["previousClose"])
    trade_time = int(meta["regularMarketTime"])
    timestamps = result.get("timestamp", [])
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    points = [(timestamp, price) for timestamp, price in zip(timestamps, closes) if price is not None]
    return current_price, previous_close, trade_time, points or [(trade_time, current_price)]


def ten_minute_change(points):
    latest_time, latest_price = points[-1]
    target_time = latest_time - 600
    historical_time, historical_price = min(points, key=lambda point: abs(point[0] - target_time))
    if latest_time - historical_time < 300:
        return 0.0
    return (latest_price - historical_price) / historical_price * 100


def should_alert(latest_price, change):
    if abs(change) < ALERT_THRESHOLD_PERCENT:
        return False
    try:
        with open(STATE_FILE, encoding="utf-8") as state:
            previous = json.load(state)
    except (OSError, ValueError):
        previous = {}

    elapsed = time.time() - float(previous.get("time", 0))
    old_price = float(previous.get("price", 0))
    movement = abs((latest_price - old_price) / old_price * 100) if old_price else 100
    if elapsed <= ALERT_COOLDOWN_SECONDS and movement < 1.0:
        return False

    try:
        with open(STATE_FILE, "w", encoding="utf-8") as state:
            json.dump({"time": time.time(), "price": latest_price}, state)
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
        emit("WTI —", f"Could not fetch WTI price: {error}")
        return

    change_10m = ten_minute_change(points)
    if should_alert(current_price, change_10m):
        notify(current_price, change_10m)

    daily_change = (current_price - previous_close) / previous_close * 100
    color = "#2ecc71" if daily_change > 0 else "#e74c3c" if daily_change < 0 else "#7f8c8d"
    sign = "+" if daily_change > 0 else ""
    text = f"WTI ${current_price:.2f} <font color='{color}'>{sign}{daily_change:.2f}%</font>"
    tooltip = (
        f"WTI Crude Oil front-month future (Yahoo Finance): ${current_price:.2f} USD\n"
        f"Previous close: ${previous_close:.2f}\n"
        f"Daily change: {sign}{daily_change:.2f}%\n"
        f"10-minute change: {change_10m:+.2f}%\n"
        f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(trade_time))}\n\n"
        "Click to refresh. Alerts fire for a 1.5% move over roughly 10 minutes."
    )
    emit(text, tooltip)


if __name__ == "__main__":
    main()
