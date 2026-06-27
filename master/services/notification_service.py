from typing import List
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from models import NotificationSetting
from services.email_service import send_email


def get_or_create_notification_settings(db: Session) -> NotificationSetting:
    settings = db.query(NotificationSetting).filter(NotificationSetting.id == 1).first()
    if not settings:
        settings = NotificationSetting(id=1, emails=[])
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def get_notification_emails(db: Session) -> List[str]:
    settings = get_or_create_notification_settings(db)
    return settings.emails or []


def update_notification_emails(db: Session, emails: List[str]) -> NotificationSetting:
    settings = get_or_create_notification_settings(db)
    settings.emails = emails
    settings.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)
    return settings


def send_notification_email(db: Session, subject: str, message: str) -> bool:
    recipients = get_notification_emails(db)
    if not recipients:
        print("No notification emails configured. Skipping email.")
        return False
    return send_email(recipients, subject, message)


