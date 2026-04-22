import smtplib
import logging
from email.mime.text import MIMEText
from config import Config

logger = logging.getLogger(__name__)


def send_invite_email(to_email: str, invite_url: str):
    body = (
        "Bonjour,\n\n"
        "Vous avez été invité(e) à rejoindre Silence on Joue.\n\n"
        "Cliquez sur ce lien pour créer votre compte :\n\n"
        f"{invite_url}\n\n"
        "Si vous n'attendiez pas cette invitation, ignorez cet e-mail."
    )

    if Config.DEBUG or not Config.SMTP_HOST:
        logger.info("INVITE LINK for %s → %s", to_email, invite_url)
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "Invitation — Silence on Joue"
    msg["From"]    = Config.SMTP_FROM
    msg["To"]      = to_email

    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(Config.SMTP_USER, Config.SMTP_PASS)
        smtp.sendmail(Config.SMTP_FROM, [to_email], msg.as_string())


def send_reset_email(to_email: str, reset_url: str):
    body = (
        "Bonjour,\n\n"
        "Cliquez sur ce lien pour réinitialiser votre mot de passe :\n\n"
        f"{reset_url}\n\n"
        "Ce lien expire dans 1 heure.\n\n"
        "Si vous n'avez pas demandé cette réinitialisation, ignorez cet e-mail."
    )

    if Config.DEBUG or not Config.SMTP_HOST:
        logger.info("PASSWORD RESET LINK for %s → %s", to_email, reset_url)
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "Réinitialisation de mot de passe — Silence on Joue"
    msg["From"]    = Config.SMTP_FROM
    msg["To"]      = to_email

    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(Config.SMTP_USER, Config.SMTP_PASS)
        smtp.sendmail(Config.SMTP_FROM, [to_email], msg.as_string())
