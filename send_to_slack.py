import os
import sys
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import date, timedelta

MENTIONS = {
    "Karthik Naidu": "U0C9C403FFX",
}

end = date.today() - timedelta(days=1)    
start = end - timedelta(days=2)           

DEFAULT_MESSAGE = f"Daily AWS Cost Summary Bill From {start.strftime('%d %b')} - {end.strftime('%d %b')}"

def build_message(message):
    tags = " ".join(f"<@{uid}>" for uid in MENTIONS.values())
    return f"{message}\ncc: {tags}"            

def send_image(path, message=DEFAULT_MESSAGE):
    token = ""
    channel = ""
    if not token or not channel:
        raise SystemExit("Set SLACK_BOT_TOKEN and SLACK_CHANNEL_ID environment variables.")
    if not os.path.isfile(path):
        raise SystemExit(f"Image not found: {path}")
    if any("XXXX" in uid for uid in MENTIONS.values()):
        raise SystemExit("Replace the placeholder member IDs in MENTIONS first.")

    client = WebClient(token=token)
    try:
        resp = client.files_upload_v2(
            channel=channel,
            file=path,
            filename=os.path.basename(path),
            title=message,                       
            initial_comment=build_message(message),  
        )
    except SlackApiError as e:
        raise SystemExit(f"Slack error: {e.response['error']}")
    print("Uploaded:", resp["file"]["permalink"])


if __name__ == "__main__":
    img = sys.argv[1] if len(sys.argv) > 1 else "cost-breakdown.png"
    msg = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MESSAGE
    send_image(img, msg)