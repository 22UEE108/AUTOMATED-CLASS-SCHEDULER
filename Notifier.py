from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend import AsyncSessionLocal, Notification, StudentCompanyDrive, RescheduledClassStudent, RescheduledClass

router = APIRouter()

# -----------------------------
# DB SESSION DEPENDENCY
# -----------------------------
async def get_session():
    async with AsyncSessionLocal() as session:
        yield session

# -----------------------------
# USER CLIENT ENDPOINT
# -----------------------------
@router.get("/notifications/{student_id}")
async def get_notifications(student_id: str, session: AsyncSession = Depends(get_session)):
    """
    Fetch all notifications for a student (both interviews and rescheduled classes)
    ordered by newest first.
    """
    result = await session.execute(
        select(Notification)
        .where(Notification.student_id == student_id)
        .order_by(Notification.created_at.desc())
    )
    notifications = [dict(row._mapping) for row in result.all()]
    return {"notifications": notifications}

# -----------------------------
# HELPER FUNCTIONS TO CREATE NOTIFICATIONS
# -----------------------------
async def notify_interview(student_id: str, company_name: str, drive_stage: str, drive_datetime: str, session: AsyncSession):
    """
    Called from main backend after IMAP + AI POST is processed.
    Inserts an interview notification for the student.
    """
    message = f"Upcoming {drive_stage} at {company_name} on {drive_datetime}"
    session.add(Notification(student_id=student_id, type="interview", message=message))
    await session.flush()  # ensures notification is saved in DB

async def notify_reschedule(student_id: str, subject_id: str, day: str, time: str, session: AsyncSession):
    """
    Called from main backend after a class is rescheduled.
    Inserts a reschedule notification for the student.
    """
    message = f"Your {subject_id} class has been rescheduled to {day} {time}"
    session.add(Notification(student_id=student_id, type="reschedule", message=message))
    await session.flush()
