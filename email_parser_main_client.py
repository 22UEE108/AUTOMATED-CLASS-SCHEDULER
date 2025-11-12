import asyncio
import aioimaplib
import email
import heapq
import json
import mysql.connector
import os
from datetime import datetime
from openai import OpenAI
import httpx
import logging

# -----------------------------
# CONFIG
# -----------------------------
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
BATCH_SIZE = 5  # number of students per async batch
OPENAI_MODEL = "gpt-3.5-turbo"
BACKEND_URL = os.getenv("BACKEND_URL", "https://your-backend-url.com/update")

# OpenAI client (API key from env variable)
openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# -----------------------------
# IN-MEMORY CACHE
# -----------------------------
email_cache = {}  # {student_id: set(email_uids)}

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def get_students_from_db():
    """Fetch student IDs, emails, and passwords directly from MySQL."""
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "your_user"),
            password=os.getenv("DB_PASSWORD", "your_password"),
            database=os.getenv("DB_NAME", "your_db")
        )
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT student_id, email, password FROM Student")
        students = cursor.fetchall()
        conn.close()
        return students
    except mysql.connector.Error as e:
        logging.error(f"DB connection error: {e}")
        return []

async def fetch_emails(student):
    """Fetch unseen emails via IMAP, skip duplicates in this run."""
    student_id = student["student_id"]
    if student_id not in email_cache:
        email_cache[student_id] = set()

    try:
        imap_client = aioimaplib.IMAP4_SSL(host=IMAP_HOST, port=IMAP_PORT)
        await imap_client.wait_hello_from_server()
        await imap_client.login(student["email"], student.get("password"))
        await imap_client.select("INBOX")
        typ, data = await imap_client.search("UNSEEN")

        if not data or not data[0]:
            await imap_client.logout()
            return []

        email_ids = data[0].split()
        emails_content = []

        for e_id in email_ids:
            e_id_str = e_id.decode()
            if e_id_str in email_cache[student_id]:
                continue  # skip duplicates

            typ, msg_data = await imap_client.fetch(e_id, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            content = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            content += part.get_payload(decode=True).decode()
                        except Exception:
                            continue
            else:
                content = msg.get_payload(decode=True).decode(errors="ignore")

            emails_content.append((e_id_str, content))
            email_cache[student_id].add(e_id_str)

        await imap_client.logout()
        return emails_content

    except Exception as e:
        logging.warning(f"IMAP error for {student['email']}: {e}")
        return []

async def parse_email_ai(email_text):
    """Send email text to OpenAI and return structured dictionary."""
    try:
        response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": f"""
                    Extract the company name and interview date/time from this email.
                    Respond ONLY in JSON format:
                    {{
                        "company_name": "...",
                        "interview_datetime": "..."
                    }}
                    Email text:
                    {email_text}
                    """
                }
            ]
        )
        result = response.choices[0].message.content
        parsed = json.loads(result)
    except Exception as e:
        logging.warning(f"AI parse error: {e}")
        parsed = {"company_name": None, "interview_datetime": None, "raw_text": email_text}
    return parsed

# -----------------------------
# PRIORITY QUEUE
# -----------------------------
class StudentTask:
    def __init__(self, priority, student_id, parsed_emails):
        self.priority = priority
        self.student_id = student_id
        self.parsed_emails = parsed_emails

    def __lt__(self, other):
        return self.priority > other.priority  # max-heap behavior

# -----------------------------
# PROCESSING
# -----------------------------
async def process_student(student):
    emails = await fetch_emails(student)
    parsed_emails = []
    for _, content in emails:
        parsed = await parse_email_ai(content)
        parsed_emails.append(parsed)
    priority = len(parsed_emails)
    return StudentTask(priority, student["student_id"], parsed_emails)

async def process_all_students(students):
    pq = []
    semaphore = asyncio.Semaphore(10)  # limit concurrent IMAP connections

    async def sem_task(student):
        async with semaphore:
            return await process_student(student)

    for i in range(0, len(students), BATCH_SIZE):
        batch = students[i:i + BATCH_SIZE]
        tasks = [sem_task(s) for s in batch]
        results = await asyncio.gather(*tasks)
        for res in results:
            heapq.heappush(pq, res)

    output = {}
    while pq:
        task = heapq.heappop(pq)
        interviews = []
        for email_dict in task.parsed_emails:
            if email_dict.get("interview_datetime") and email_dict.get("company_name"):
                interviews.append({
                    "company_name": email_dict["company_name"],
                    "interview_datetime": email_dict["interview_datetime"]
                })
        if interviews:
            output[task.student_id] = interviews
    return output

# -----------------------------
# SEND TO BACKEND
# -----------------------------
async def send_to_backend(data):
    """Send the processed dictionary to backend via HTTP POST."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(BACKEND_URL, json=data)
            response.raise_for_status()
            logging.info(f"Data sent to backend, status: {response.status_code}")
            return response.status_code
        except httpx.RequestError as e:
            logging.error(f"Failed to send data: {e}")
        except httpx.HTTPStatusError as e:
            logging.error(f"Backend returned error: {e}")
        return None

# -----------------------------
# MAIN
# -----------------------------
async def main():
    logging.info("Fetching students from DB...")
    students = get_students_from_db()
    if not students:
        logging.warning("No students fetched. Exiting.")
        return

    logging.info(f"Processing {len(students)} students...")
    final_dict = await process_all_students(students)

    if final_dict:
        await send_to_backend(final_dict)
    else:
        logging.info("No interviews found to send.")

if __name__ == "__main__":
    asyncio.run(main())
