"""
Email test endpoint — lets you verify SMTP config actually works before
trusting it inside a real renewal campaign or collections reminder.
"""
from fastapi import APIRouter, HTTPException, Depends

from auth import require_staff
import email_service

router = APIRouter(prefix="/api/email", tags=["email"])


@router.post("/test-send")
async def test_send(to: str, user: dict = Depends(require_staff)):
    try:
        await email_service.send_email_async(
            to=to,
            subject="PropWise AI — test email",
            body_text="If you're reading this, your SMTP configuration is working correctly.",
        )
    except email_service.EmailNotConfigured as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except email_service.EmailSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"status": "sent", "to": to}
