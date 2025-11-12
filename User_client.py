from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend import AsyncSessionLocal, StudentCompanyDrive, RescheduledClass, RescheduledClassStudent, Attendance, Student

router = APIRouter()

# Dependency: get async DB session
async def get_session():
    async with AsyncSessionLocal() as session:
        yield session

# -----------------------------
# Dashboard endpoint
# -----------------------------
@router.get("/dashboard/{student_id}")
async def get_user_dashboard(student_id: str, session: AsyncSession = Depends(get_session)):
    """
    Returns:
        - Company drives/interviews for the student
        - Rescheduled classes for that student
        - Attendance status (optional)
    """
    # Verify student exists
    result = await session.execute(select(Student).where(Student.student_id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    ##Company drives/interviews
    drives_result = await session.execute(
        select(
            StudentCompanyDrive.company_name,
            StudentCompanyDrive.drive_stage,
            StudentCompanyDrive.drive_datetime,
            StudentCompanyDrive.status
        ).where(StudentCompanyDrive.student_id == student_id)
    )
    drives = [dict(row._mapping) for row in drives_result.all()]

    ##Rescheduled classes (filtered per student)
    resched_result = await session.execute(
        select(
            RescheduledClass.subject_id,
            RescheduledClass.day,
            RescheduledClass.time,
            RescheduledClass.status
        ).join(
            RescheduledClassStudent,
            RescheduledClass.reschedule_id == RescheduledClassStudent.reschedule_id
        ).where(
            RescheduledClassStudent.student_id == student_id
        )
    )
    reschedules = [dict(row._mapping) for row in resched_result.all()]

    ##Attendance (optional)
    attendance_result = await session.execute(
        select(
            Attendance.student_id,
            Attendance.schedule_id,
            Attendance.status
        ).where(Attendance.student_id == student_id)
    )
    attendance = [dict(row._mapping) for row in attendance_result.all()]

    return {
        "student_id": student_id,
        "name": student.name,
        "drives": drives,
        "rescheduled_classes": reschedules,
        "attendance": attendance
    }
