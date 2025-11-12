# Automated Class Scheduler

## Project Overview
This project automates tracking and management of student interviews, company drives, class schedules, and attendance. It also provides notifications to students about upcoming interviews and rescheduled classes. The system is designed for **high scalability** and can efficiently handle thousands of students asynchronously.

---

## Key Features

- **Automated Email Parsing (IMAP + AI)**
  - Fetches students’ emails asynchronously using `aioimaplib`.
  - Uses OpenAI GPT to extract company name and interview date/time.
  - Avoids duplicates with in-memory caching.
  - Scalable via batch processing and concurrency control.

- **Backend System (FastAPI + MySQL)**
  - Stores students, subjects, schedules, attendance, company drives, and rescheduled classes.
  - Automatically updates DB when new interviews or reschedules are detected.
  - Handles rescheduling of classes based on available slots.
  - Uses **async SQLAlchemy** and **aiomysql** for non-blocking database operations.

- **User Dashboard (Future / Optional)**
  - Provides an endpoint to fetch student-specific dashboard data.
  - Shows upcoming interviews, rescheduled classes, and attendance.
  - Fully async, integrated with the main backend.

- **Notifications**
  - Notifications are generated for new interviews or rescheduled classes.
  - User client can fetch notifications via a lightweight endpoint.
  - Minimal overhead; read-only fetching ensures high performance.

---

## Technical Stack

- **Backend:** FastAPI (Python), Async SQLAlchemy, MySQL (aiomysql)  
- **Email Parsing:** `aioimaplib`, OpenAI GPT API  
- **HTTP Client:** `httpx` for async backend communication  
- **Data Storage:** MySQL database with normalized tables for students, subjects, schedules, attendance, drives, and rescheduled classes  
- **Async / Concurrency:** `asyncio`, `Semaphore` for limiting concurrent IMAP connections  

---

## Database Structure

**Main Tables**
- `students` — Stores student info (ID, name, email, password).  
- `subjects` — Subject info.  
- `subject_schedule` — Schedule for each subject.  
- `student_subject` — Mapping of students to subjects.  
- `attendance` — Student attendance records.  
- `rescheduled_class` & `rescheduled_class_student` — Stores rescheduled classes and assignments per student.  
- `student_company_drive` — Stores student interview/OA info.  
- `weekly_slot` — Predefined weekly slots for rescheduling classes.  

---

## Optimizations & Scalability

- **Async Operations:** IMAP email fetching, AI parsing, and DB writes are fully asynchronous to prevent blocking I/O.  
- **Batch Processing:** Students are processed in configurable batches (`BATCH_SIZE`) with semaphore limits.  
- **Priority Queue:** Students with the most new emails are processed first.  
- **Database Efficiency:** Only inserts new or updated records; tables are indexed for quick lookups.  
- **Notification System:** Lightweight fetch-only notifications for the user client.  
- **Memory Management:** In-memory cache ensures duplicate emails are not reprocessed; batched operations minimize memory spikes.

> **Note:** This project has been fully implemented and the code has been fixed and optimized for deployment.  
> It is designed to run with MySQL, FastAPI, and OpenAI API keys, but it has not been deployed end-to-end.  
> Minor environment-specific adjustments may be required.
  


