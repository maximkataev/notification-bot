import os
import httpx
from datetime import datetime
from typing import Optional, List
import logging

from src.db.models import Task
from src.utils.doppler import get_secret

logger = logging.getLogger(__name__)

TODOIST_PROJECT_NAME = "Личное"
TODOIST_API_URL = "https://api.todoist.com/api/v1"


async def get_todoist_token() -> Optional[str]:
    """Get Todoist API token from environment or Doppler."""
    token = os.getenv("TODOIST_API_KEY") or get_secret("TODOIST_API_KEY")
    if not token:
        logger.error("TODOIST_API_KEY not found in environment or Doppler")
    return token


async def get_project_id(token: str) -> Optional[str]:
    """Find 'Личное' project ID in Todoist."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{TODOIST_API_URL}/projects",
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            data = response.json()
            projects = data.get("results", [])

            for project in projects:
                if project.get("name") == TODOIST_PROJECT_NAME:
                    return project.get("id")

            logger.warning(f"Project '{TODOIST_PROJECT_NAME}' not found in Todoist")
            return None
    except Exception as e:
        logger.error(f"Failed to fetch Todoist projects: {e}")
        return None


async def get_todoist_tasks() -> List[Task]:
    """Fetch tasks from Todoist 'Личное' project for today and earlier."""
    token = await get_todoist_token()
    if not token:
        logger.error("Cannot fetch tasks: TODOIST_API_KEY is missing")
        return []

    project_id = await get_project_id(token)
    if not project_id:
        logger.error("Cannot fetch tasks: 'Личное' project not found")
        return []

    tasks = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{TODOIST_API_URL}/tasks",
                headers={"Authorization": f"Bearer {token}"},
                params={"project_id": project_id}
            )
            response.raise_for_status()
            data = response.json()
            todoist_tasks = data.get("results", [])

            today = datetime.now().date().isoformat()

            for todoist_task in todoist_tasks:
                # Skip completed tasks
                if todoist_task.get("checked", False):
                    continue

                # Extract due date
                due = todoist_task.get("due")
                when_date = None
                when_time = None
                is_recurring = False

                if due:
                    # Check if task is for today or earlier
                    due_date = due.get("date")
                    if due_date:
                        # Extract date part from ISO format (might include time)
                        due_date_only = due_date.split("T")[0]
                        if due_date_only > today:
                            continue  # Skip future tasks
                        when_date = due_date_only

                    # Extract time from the date part if present
                    if due_date and "T" in due_date:
                        try:
                            dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                            when_time = dt.strftime("%H:%M")
                        except Exception as e:
                            logger.debug(f"Failed to parse due date time: {e}")

                    is_recurring = due.get("is_recurring", False)

                # Check if urgent (priority 4)
                is_urgent = todoist_task.get("priority") == 4

                # Check if outdoor (label "outdoor" or "на улице")
                labels = todoist_task.get("labels", [])
                is_outdoor = any(label.lower() in ["outdoor", "на улице"] for label in labels)

                # Convert Todoist string ID to a stable integer
                task_id_str = str(todoist_task.get("id", ""))
                try:
                    # Try to parse as int if it's numeric
                    task_id = int(task_id_str) if task_id_str.isdigit() else abs(hash(task_id_str)) % (2**31)
                except ValueError:
                    task_id = abs(hash(task_id_str)) % (2**31)

                task = Task(
                    id=task_id,
                    user_id=0,
                    raw_text=todoist_task.get("content", ""),
                    what=todoist_task.get("content", ""),
                    when_date=when_date,
                    when_time=when_time,
                    proposed_time=None,
                    is_urgent=is_urgent,
                    is_outdoor=is_outdoor,
                    is_recurring=is_recurring,
                    status="planned",
                )
                tasks.append(task)

            logger.info(f"Fetched {len(tasks)} tasks from Todoist")
            return tasks
    except Exception as e:
        logger.error(f"Failed to fetch Todoist tasks: {e}")
        return []


async def create_todoist_task(content: str) -> Optional[str]:
    """Create a new task in Todoist 'Личное' project."""
    token = await get_todoist_token()
    if not token:
        logger.error("Cannot create task: TODOIST_API_KEY is missing")
        return None

    project_id = await get_project_id(token)
    if not project_id:
        logger.error("Cannot create task: 'Личное' project not found")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{TODOIST_API_URL}/tasks",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "content": content,
                    "project_id": project_id,
                }
            )
            response.raise_for_status()
            task_data = response.json()
            task_id = task_data.get("id")
            logger.info(f"Created Todoist task: {task_id}")

            # Return Todoist web URL
            # Note: Todoist uses task ID strings in URLs
            return f"https://todoist.com/app/task/{task_id}"
    except Exception as e:
        logger.error(f"Failed to create Todoist task: {e}")
        return None
