# backend_final.py
import os
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Enum, DateTime, ForeignKey, select
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# -----------------------------
# CONFIG & LOGGING
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "mysql+aiomysql://user:password@localhost:3306/your_db")
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

# -----------------------------
# TABLES / MODELS
# -----------------------------
class Student(Base):
    __tablename__ = "students"
    student_id = Column(String, primary_key=True)
    name = Column(String)
    email = Column(String)
    password = Column(String)

class Subject(Base):
    __tablename__ = "subjects"
    subject_id = Column(String, primary_key=True)
    subject_name = Column(String)

class SubjectSchedule(Base):
    __tablename__ = "subject_schedule"
    schedule_id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(String, ForeignKey("subjects.subject_id"))
    day = Column(String)
    time = Column(String)

class StudentSubject(Base):
    __tablename__ = "student_subject"
    student_id = Column(String, ForeignKey("students.student_id"), primary_key=True)
    subject_id = Column(String, ForeignKey("subjects.subject_id"), primary_key=True)

class Attendance(Base):
    __tablename__ = "attendance"
    attendance_id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String, ForeignKey("students.student_id"))
    schedule_id = Column(Integer, ForeignKey("subject_schedule.schedule_id"), nullable=True)
    status = Column(Enum("present","absent", name="attendance_status"))

class RescheduledClass(Base):
    __tablename__ = "rescheduled_class"
    reschedule_id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(String, ForeignKey("subjects.subject_id"))
    day = Column(String)
    time = Column(String)
    status = Column(Enum("pending","done", name="reschedule_status"))

class RescheduledClassStudent(Base):
    __tablename__ = "rescheduled_class_student"
    reschedule_id = Column(Integer, ForeignKey("rescheduled_class.reschedule_id"), primary_key=True)
    student_id = Column(String, ForeignKey("students.student_id"), primary_key=True)
    status = Column(Enum("pending","done", name="reschedule_student_status"))

class StudentCompanyDrive(Base):
    __tablename__ = "student_company_drive"
    record_id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String, ForeignKey("students.student_id"))
    company_name = Column(String)
    drive_stage = Column(Enum("OA","Interview", name="drive_stage_enum"))
    drive_datetime = Column(DateTime)
    status = Column(Enum("pending","done", name="drive_status"))

class WeeklySlot(Base):
    __tablename__ = "weekly_slot"
    slot_id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(String)
    time = Column(String)

# -----------------------------
# Pydantic Models
# -----------------------------
class ParsedEmail(BaseModel):
    company_name: str
    interview_datetime: str

class StudentEmails(BaseModel):
    __root__: Dict[str, List[ParsedEmail]]

# -----------------------------
# FASTAPI APP
# -----------------------------
app = FastAPI()

# -----------------------------
# UTILITY FUNCTIONS
# -----------------------------
async def get_free_slots(student_ids: List[str], session: AsyncSession):
    """
    Returns the set of weekly slots where all given students are free.
    Implementation:
      - Fetch all weekly slots from WeeklySlot table.
      - For each student, compute free = all_slots - occupied_by_student.
      - Return intersection of all students' free sets.
    """
    # 1. Fetch all weekly slots
    result = await session.execute(select(WeeklySlot.day, WeeklySlot.time))
    all_slots = set(result.all())
    logger.debug("All weekly slots count: %d", len(all_slots))

    # 2. For each student, compute occupied and thus free slots
    free_sets = []
    for student_id in student_ids:
        result = await session.execute(
            select(SubjectSchedule.day, SubjectSchedule.time)
            .join(StudentSubject, StudentSubject.subject_id == SubjectSchedule.subject_id)
            .where(StudentSubject.student_id == student_id)
        )
        occupied = set(result.all())
        free_for_student = all_slots - occupied
        free_sets.append(free_for_student)
        logger.debug("Student %s occupied: %d, free: %d", student_id, len(occupied), len(free_for_student))

    if not free_sets:
        # no students -> all slots are free
        return all_slots

    # Intersection of free sets => slots where everyone is free
    common_free = set.intersection(*free_sets)
    logger.info("Common free slots count for %d students: %d", len(student_ids), len(common_free))
    return common_free

async def reschedule_class_for_subject(subject_id: str, session: AsyncSession):
    """
    Reschedule a subject for all students enrolled in it:
      - find enrolled students
      - compute common free slots
      - create RescheduledClass and RescheduledClassStudent entries
      - add Attendance rows for rescheduled class (initially absent)
    """
    # Get all students of the subject
    result = await session.execute(
        select(StudentSubject.student_id)
        .where(StudentSubject.subject_id == subject_id)
    )
    students = [row[0] for row in result.all()]
    if not students:
        logger.debug("No students enrolled for subject %s", subject_id)
        return

    # Compute common free slots
    free_slots = await get_free_slots(students, session)
    if not free_slots:
        logger.info("No common free slot found for subject %s", subject_id)
        return  # no available slot

    # Pick earliest slot (sorted by day/time lexicographically; customize if you have order)
    day, time = sorted(free_slots)[0]
    logger.info("Rescheduling subject %s to %s %s", subject_id, day, time)

    # Create rescheduled class
    new_reschedule = RescheduledClass(
        subject_id=subject_id,
        day=day,
        time=time,
        status="pending"
    )
    session.add(new_reschedule)
    await session.flush()  # ensure reschedule_id is populated

    # Assign all students and create attendance rows
    for student_id in students:
        session.add(RescheduledClassStudent(
            reschedule_id=new_reschedule.reschedule_id,
            student_id=student_id,
            status="pending"
        ))
        session.add(Attendance(
            student_id=student_id,
            schedule_id=None,
            status="absent"
        ))

# -----------------------------
# POST ENDPOINT
# -----------------------------
@app.post("/update")
async def update_student_data(data: StudentEmails):
    async with AsyncSessionLocal() as session:
        try:
            # 1. Update company drive info (idempotent)
            for student_id, emails in data.__root__.items():
                for email in emails:
                    # parse datetime safely
                    try:
                        drive_time = datetime.fromisoformat(email.interview_datetime)
                    except Exception as exc:
                        logger.warning("Invalid datetime for student %s: %s (%s)", student_id, email.interview_datetime, exc)
                        # skip this entry if datetime invalid
                        continue

                    # check existing record
                    result = await session.execute(
                        select(StudentCompanyDrive)
                        .where(StudentCompanyDrive.student_id == student_id)
                        .where(StudentCompanyDrive.company_name == email.company_name)
                        .where(StudentCompanyDrive.drive_datetime == drive_time)
                    )
                    existing = result.scalar_one_or_none()
                    if not existing:
                        session.add(StudentCompanyDrive(
                            student_id=student_id,
                            company_name=email.company_name,
                            drive_stage="Interview",
                            drive_datetime=drive_time,
                            status="pending"
                        ))
                        logger.info("Inserted StudentCompanyDrive for %s -> %s at %s", student_id, email.company_name, drive_time)

            # 2. Reschedule classes per subject
            result = await session.execute(select(Subject.subject_id))
            subjects = [row[0] for row in result.all()]
            for subject_id in subjects:
                await reschedule_class_for_subject(subject_id, session)

            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception("Failed to update student data")
            raise HTTPException(status_code=500, detail=str(e))

    return {"status": "success"}
