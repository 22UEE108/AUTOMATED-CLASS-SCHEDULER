from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend import AsyncSessionLocal, StudentCompanyDrive, RescheduledClass, RescheduledClassStudent, Attendance, Student
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import JWTError, jwt
from typing import Optional
from fastapi.security import OAuth2PasswordBearer

# -----------------------------
# JWT CONFIG
# -----------------------------
SECRET_KEY = "your_super_secret_key"  # replace with env var in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# -----------------------------
# Pydantic models
# -----------------------------
class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# -----------------------------
# APIRouter
# -----------------------------
router = APIRouter()

# Dependency: get async DB session
async def get_session():
    async with AsyncSessionLocal() as session:
        yield session

# -----------------------------
# JWT utilities
# -----------------------------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Generate a JWT token for the student."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_student(token: str = Depends(OAuth2PasswordBearer(tokenUrl="login")),
                              session: AsyncSession = Depends(get_session)):
    """Validate JWT token and return the current student object."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        student_id: str = payload.get("sub")
        if student_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await session.execute(select(Student).where(Student.student_id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise credentials_exception
    return student

# -----------------------------
# LOGIN ENDPOINT
# -----------------------------
@router.post("/login", response_model=TokenResponse)
async def login(login_req: LoginRequest, session: AsyncSession = Depends(get_session)):
    """Authenticate student and return JWT token."""
    result = await session.execute(select(Student).where(Student.email == login_req.email))
    student = result.scalar_one_or_none()
    if not student or student.password != login_req.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    
    access_token = create_access_token(data={"sub": student.student_id})
    return {"access_token": access_token, "token_type": "bearer"}

# -----------------------------
# DASHBOARD ENDPOINT (protected)
# -----------------------------
@router.get("/dashboard")
async def get_user_dashboard(current_student: Student = Depends(get_current_student),
                             session: AsyncSession = Depends(get_session)):
    """Fetch the dashboard for the logged-in student including:
       - Company drives/interviews
       - Rescheduled classes
       - Attendance status
    """
    student_id = current_student.student_id

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

    ##Rescheduled classes for this student
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

    ##Attendance
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
        "name": current_student.name,
        "drives": drives,
        "rescheduled_classes": reschedules,
        "attendance": attendance
    }
