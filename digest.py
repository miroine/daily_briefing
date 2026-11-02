"""Daily digest: builds the morning brief and sends it by email and/or Telegram.

Usage:
    python digest.py --dry-run          # writes out/brief.html, sends nothing
    python digest.py                    # sends to whatever is configured (SMTP_*, TELEGRAM_*)
    python digest.py --ai               # also adds a Claude summary (needs ANTHROPIC_API_KEY)
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

from core import brief, config, notify, pipeline, storage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="build the brief but do not send")
    ap.add_argument("--ai", action="store_true", help="add a Claude-written summary")
    ap.add_argument("--out", default="out/brief.html")
    args = ap.parse_args()

    settings = storage.load_settings(config.DEFAULT_SETTINGS)
    ctx = pipeline.collect(settings)

    ai = None
    key = notify.get_secret("ANTHROPIC_API_KEY")
    if args.ai or (settings.get("ai_enabled") and key):
        if key:
            try:
                ai = brief.ai_summary(ctx, key, settings.get("ai_model", "claude-sonnet-5-5"))
            except Exception as e:
                print(f"AI summary skipped: {e}", file=sys.stderr)
        else:
            print("AI summary skipped: ANTHROPIC_API_KEY not set", file=sys.stderr)

    html_doc = brief.build_brief_html(ctx, "light", ai)
    text = brief.to_text(ctx, ai)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    print(f"Brief written to {out} ({len(html_doc)} bytes)")

    if args.dry_run:
        return 0

    today = dt.date.today().isoformat()
    sent = False
    errors = []
    if notify.email_configured():
        try:
            notify.send_email(f"Morning brief {today}", html_doc, text)
            print("Email sent")
            sent = True
        except Exception as e:
            errors.append(f"email: {e}")
    if notify.telegram_configured():
        try:
            notify.send_telegram(text, html_doc, f"morning_brief_{today}.html")
            print("Telegram sent")
            sent = True
        except Exception as e:
            errors.append(f"telegram: {e}")
    if not sent and not errors:
        print("Nothing sent: configure SMTP_* and/or TELEGRAM_* environment variables.", file=sys.stderr)
    for err in errors:
        print(f"FAILED {err}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
