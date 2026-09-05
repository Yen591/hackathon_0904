import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def send_daily_report(csv_path: str = None, html_path: str = None) -> bool:
    """寄送每日分析報告與附件"""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SENDER_EMAIL", smtp_user)
    receiver_email = os.getenv("RECEIVER_EMAIL")

    if not all([smtp_user, smtp_password, receiver_email]):
        logger.error("缺少寄信環境變數：請在 .env 確保 SMTP_USER, SMTP_PASSWORD, RECEIVER_EMAIL 都有設定")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = "📊 Market Sentinel - 最新 AI 市場監控報告"

    table_html = ""
    if csv_path and os.path.exists(csv_path):
        import csv
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                if not rows:
                    table_html = "<p>目前沒有新的分析結果。</p>"
                else:
                    table_html = '<table border="1" style="border-collapse: collapse; width: 100%; font-size: 14px;">'
                    table_html += '<tr style="background-color: #f2f2f2;"><th style="padding: 8px;">股票名稱</th><th style="padding: 8px;">新聞標題</th><th style="padding: 8px;">情緒</th><th style="padding: 8px;">分類</th><th style="padding: 8px;">AI 分析筆記</th></tr>'
                    for row in rows:
                        sentiment = row.get("Sentiment", "")
                        color = "green" if sentiment.lower() == "positive" else "red" if sentiment.lower() == "negative" else "gray"
                        table_html += f"<tr>"
                        table_html += f"<td style='padding: 8px;'>{row.get('股票名稱', '')}</td>"
                        table_html += f"<td style='padding: 8px;'>{row.get('新聞標題', '')}</td>"
                        table_html += f"<td style='padding: 8px; color: {color}; font-weight: bold;'>{sentiment}</td>"
                        table_html += f"<td style='padding: 8px;'>{row.get('Classification', '')}</td>"
                        table_html += f"<td style='padding: 8px;'>{row.get('AI 分析筆記', '')}</td>"
                        table_html += f"</tr>"
                    table_html += "</table>"
        except Exception as e:
            logger.error(f"讀取 CSV 產生 HTML 表格失敗: {e}")
            table_html = "<p>產生結果表格時發生錯誤。</p>"
    else:
        table_html = "<p>找不到分析資料 (CSV)。</p>"

    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #007bff;">Market Sentinel 財經新聞分析完成</h2>
        <p>您好，以下是最新出爐的 AI 分析結果：</p>
        {table_html}
        <br/>
        <p>完整詳細資料（包含各項情緒分數等）請參考附件的 <strong>CSV 檔案</strong>，或透過 <strong>dashboard.html</strong> 預覽。</p>
        <hr style="border: none; border-top: 1px solid #eee;" />
        <p style="font-size: 0.9em; color: #888;">此為系統自動發送的信件，請勿直接回覆。</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(body, 'html', 'utf-8'))

    # 附加 CSV
    if csv_path and os.path.exists(csv_path):
        with open(csv_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(csv_path))
            part['Content-Disposition'] = f'attachment; filename="{os.path.basename(csv_path)}"'
            msg.attach(part)
            
    # 附加 HTML
    if html_path and os.path.exists(html_path):
        with open(html_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(html_path))
            part['Content-Disposition'] = f'attachment; filename="{os.path.basename(html_path)}"'
            msg.attach(part)

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        logger.info(f"✅ 分析報告已成功寄送至 {receiver_email}")
        return True
    except Exception as e:
        logger.error(f"❌ 寄送報告失敗: {e}")
        return False
