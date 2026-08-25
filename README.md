# WTI Oil Price for Omarchy

A compact Omarchy bar widget for the front-month WTI crude-oil future (`CL=F`). It shows the latest price and daily percentage change, refreshes every 30 seconds, and sends an urgent desktop notification after a rapid 10-minute move of at least 1.5%.

Market data is fetched from Yahoo Finance. The widget uses only Python's standard library; no packages or API key are required.

## Install

```bash
omarchy plugin add https://github.com/17xHW/omarchy-wti-oil-price.git --enable
omarchy bar move io.github.17xhw.wti-oil-price --section center
```

If the widget is not automatically placed on the bar, use Omarchy's bar settings to add **WTI Oil Price**. Click the price to refresh it immediately.

## Configuration

The only setting is `refreshSeconds`, which defaults to 30 seconds and has a 15-second minimum. The notification threshold is intentionally fixed at a 1.5% move over approximately 10 minutes, with a 10-minute cooldown unless the price moves another 1%.

## Dependencies

- Omarchy Quattro with the shell-plugin system
- `python3`
- Network access to `query1.finance.yahoo.com`
- Optional: `notify-send` and `pw-play` for rapid-move notifications and sound

## Remove

```bash
omarchy plugin remove io.github.17xhw.wti-oil-price
```

This removes the installed plugin. No persistent configuration or credentials are created.

## Data notice

`CL=F` is Yahoo Finance's front-month WTI crude-oil futures symbol. Prices may be delayed, unavailable outside active sessions, or unsuitable for trading decisions.

## License

MIT. See [LICENSE](LICENSE).
