import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import logging

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

    body = """
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #007bff;">Market Sentinel 財經新聞分析完成</h2>
        <p>您好，</p>
        <p>系統已自動爬取最新新聞，並由 <strong>FinBERT</strong> 與 <strong>LLM</strong> 完成情緒判定與影響評估。</p>
        <p>詳細資料請參考附件 <strong>CSV 檔案</strong>，該檔案可直接用於更新您的 <strong>Power BI 地端儀表板</strong>。</p>
        <p>如有需要，您也可以直接點開附件的 <strong>dashboard.html</strong> 預覽本次分析結果。</p>
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
