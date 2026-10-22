"""
Email dispatch service using FastAPI-Mail with HTML templates.
Supports alert notifications, daily digests, and incident summaries.
"""
import os
from typing import List, Optional, Dict, Any
from loguru import logger


_MAIL_CONFIG = None


def _get_mail():
    """Lazy-init FastAPI-Mail to avoid import errors when mail is not configured."""
    global _MAIL_CONFIG
    if _MAIL_CONFIG is None:
        try:
            from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
            from app.core.config import settings

            conf = ConnectionConfig(
                MAIL_USERNAME=settings.MAIL_USERNAME,
                MAIL_PASSWORD=settings.MAIL_PASSWORD,
                MAIL_FROM=settings.MAIL_FROM,
                MAIL_FROM_NAME="Campus Sentinel",
                MAIL_PORT=settings.MAIL_PORT,
                MAIL_SERVER=settings.MAIL_SERVER,
                MAIL_STARTTLS=settings.MAIL_STARTTLS,
                MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
                USE_CREDENTIALS=bool(settings.MAIL_USERNAME),
                VALIDATE_CERTS=True,
            )
            _MAIL_CONFIG = (FastMail(conf), MessageSchema, MessageType)
        except Exception as e:
            logger.warning(f"Email not configured: {e}")
            _MAIL_CONFIG = None
    return _MAIL_CONFIG


def _alert_html(alert: Dict[str, Any]) -> str:
    severity_colors = {
        "critical": "#9333ea",
        "high":     "#ef4444",
        "medium":   "#f59e0b",
        "low":      "#22c55e",
    }
    color = severity_colors.get(alert.get("severity", "medium"), "#6b7280")
    return f"""
    <div style="font-family: -apple-system, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0f1624; color: #e2e8f0; border-radius: 12px; overflow: hidden;">
      <div style="background: {color}; padding: 20px 24px;">
        <h1 style="margin: 0; font-size: 18px; color: white;">
          🚨 Campus Sentinel Alert — {alert.get("severity", "").upper()}
        </h1>
      </div>
      <div style="padding: 24px;">
        <h2 style="margin: 0 0 8px; font-size: 16px; color: white;">{alert.get("title", "Security Alert")}</h2>
        <p style="margin: 0 0 16px; color: #94a3b8; font-size: 14px;">{alert.get("description", "")}</p>
        <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
          <tr style="border-bottom: 1px solid #1e293b;">
            <td style="padding: 8px 0; color: #64748b;">Alert Type</td>
            <td style="padding: 8px 0; color: #e2e8f0;">{alert.get("alert_type", "").replace("_", " ").title()}</td>
          </tr>
          <tr style="border-bottom: 1px solid #1e293b;">
            <td style="padding: 8px 0; color: #64748b;">Camera</td>
            <td style="padding: 8px 0; color: #e2e8f0;">{alert.get("camera_id", "N/A")}</td>
          </tr>
          <tr style="border-bottom: 1px solid #1e293b;">
            <td style="padding: 8px 0; color: #64748b;">Threat Score</td>
            <td style="padding: 8px 0; color: {color}; font-weight: bold;">{alert.get("threat_score", 0):.2f}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #64748b;">Time</td>
            <td style="padding: 8px 0; color: #e2e8f0;">{alert.get("created_at", "")}</td>
          </tr>
        </table>
        <div style="margin-top: 20px; padding: 12px; background: #1e293b; border-radius: 8px; font-size: 12px; color: #94a3b8;">
          <strong style="color: #60a5fa;">AI Analysis:</strong> {alert.get("explanation_summary", "Anomalous behavior detected.")}
        </div>
        <div style="margin-top: 20px; text-align: center;">
          <a href="{os.environ.get('FRONTEND_URL', 'http://localhost:3000')}/alerts"
             style="background: {color}; color: white; padding: 10px 24px; border-radius: 8px; text-decoration: none; font-size: 13px; font-weight: 600;">
            View in Dashboard →
          </a>
        </div>
      </div>
      <div style="padding: 12px 24px; background: #080c14; font-size: 11px; color: #475569; text-align: center;">
        Campus Sentinel · AI Surveillance System · Do not reply to this email
      </div>
    </div>
    """


def _digest_html(data: Dict[str, Any]) -> str:
    return f"""
    <div style="font-family: -apple-system, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0f1624; color: #e2e8f0; border-radius: 12px; overflow: hidden;">
      <div style="background: #1d4ed8; padding: 20px 24px;">
        <h1 style="margin: 0; font-size: 18px; color: white;">📊 Daily Security Digest</h1>
        <p style="margin: 4px 0 0; font-size: 12px; color: #bfdbfe;">{data.get("date", "")}</p>
      </div>
      <div style="padding: 24px;">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;">
          <div style="background: #1e293b; border-radius: 8px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; font-weight: 700; color: #60a5fa;">{data.get("total_alerts", 0)}</div>
            <div style="font-size: 12px; color: #64748b;">Total Alerts</div>
          </div>
          <div style="background: #1e293b; border-radius: 8px; padding: 16px; text-align: center;">
            <div style="font-size: 28px; font-weight: 700; color: #22c55e;">{data.get("avg_csi", 0):.0f}</div>
            <div style="font-size: 12px; color: #64748b;">Avg Safety Score</div>
          </div>
        </div>
        <h3 style="margin: 0 0 12px; font-size: 14px; color: #94a3b8;">Critical & High Alerts</h3>
        {"".join(f'<div style="padding: 10px; margin-bottom: 8px; background: #1e293b; border-radius: 6px; border-left: 3px solid {"#9333ea" if a.get("severity") == "critical" else "#ef4444"}; font-size: 13px;">{a.get("title", "")}</div>' for a in data.get("top_alerts", []))}
      </div>
      <div style="padding: 12px 24px; background: #080c14; font-size: 11px; color: #475569; text-align: center;">
        Campus Sentinel · AI Surveillance System
      </div>
    </div>
    """


async def send_alert_email(recipients: List[str], alert: Dict[str, Any]):
    """Send alert email to a list of recipients."""
    mail_bundle = _get_mail()
    if not mail_bundle:
        logger.info(f"[EMAIL-MOCK] Alert to {recipients}: {alert.get('title')}")
        return

    FastMail, MessageSchema, MessageType = mail_bundle
    try:
        message = MessageSchema(
            subject=f"[{alert.get('severity', 'ALERT').upper()}] Campus Sentinel: {alert.get('title', 'Security Alert')}",
            recipients=recipients,
            body=_alert_html(alert),
            subtype=MessageType.html,
        )
        fm = FastMail(_get_mail()[0].config)
        await fm.send_message(message)
        logger.info(f"Alert email sent to {recipients}")
    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")


def send_alert_email_sync(recipients: List[str], alert: Dict[str, Any]):
    """Synchronous wrapper for use in Celery tasks."""
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(send_alert_email(recipients, alert))
        loop.close()
    except Exception as e:
        logger.error(f"Email dispatch error: {e}")


async def send_digest_email(recipients: List[str], data: Dict[str, Any]):
    """Send daily digest email."""
    mail_bundle = _get_mail()
    if not mail_bundle:
        logger.info(f"[EMAIL-MOCK] Digest to {recipients}: {data.get('date')}")
        return

    FastMail, MessageSchema, MessageType = mail_bundle
    try:
        message = MessageSchema(
            subject=f"Campus Sentinel Daily Digest — {data.get('date', '')}",
            recipients=recipients,
            body=_digest_html(data),
            subtype=MessageType.html,
        )
        fm = FastMail(mail_bundle[0].config)
        await fm.send_message(message)
        logger.info(f"Digest email sent to {recipients}")
    except Exception as e:
        logger.error(f"Failed to send digest email: {e}")
