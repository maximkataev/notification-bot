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
                headers={"Authorization": f"Bearer {token}"},
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
                params={"project_id": project_id},
            )
            response.raise_for_status()
            data = response.json()
            todoist_tasks = data.get("results", [])

            logger.info(f"📥 Todoist API returned {len(todoist_tasks)} tasks")
            today = datetime.now().date().isoformat()
            logger.info(f"   Today's date: {today}")

            skipped_completed = 0
            skipped_future = 0

            for todoist_task in todoist_tasks:
                # Skip completed tasks
                if todoist_task.get("checked", False):
                    skipped_completed += 1
                    continue

                content = todoist_task.get("content", "")
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
                            skipped_future += 1
                            logger.debug(f"   ⏭️  Skipped future task: {content} (due: {due_date_only})")
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
                else:
                    logger.debug(f"   📌 Task with NO due date: {content}")

                # Check if urgent (priority 4)
                is_urgent = todoist_task.get("priority") == 4

                # Check if outdoor (label "outdoor" or "на улице")
                labels = todoist_task.get("labels", [])
                is_outdoor = any(
                    label.lower() in ["outdoor", "на улице"] for label in labels
                )

                # Convert Todoist string ID to a stable integer
                task_id_str = str(todoist_task.get("id", ""))
                try:
                    # Try to parse as int if it's numeric
                    task_id = (
                        int(task_id_str)
                        if task_id_str.isdigit()
                        else abs(hash(task_id_str)) % (2**31)
                    )
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
                logger.debug(f"   ✓ Added task: {content} (date: {when_date}, time: {when_time})")

            logger.info(f"📊 Todoist fetch summary: {len(tasks)} included | {skipped_completed} completed | {skipped_future} future")
            return tasks
    except Exception as e:
        logger.error(f"Failed to fetch Todoist tasks: {e}", exc_info=True)
        return []


async def get_overdue_tasks() -> List[dict]:
    """Fetch tasks with due dates in the past (today or earlier) from Todoist.

    Returns:
        List of task dicts with id, content, due date info
    """
    token = await get_todoist_token()
    if not token:
        logger.error("Cannot fetch tasks: TODOIST_API_KEY is missing")
        return []

    project_id = await get_project_id(token)
    if not project_id:
        logger.error("Cannot fetch tasks: 'Личное' project not found")
        return []

    overdue_tasks = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{TODOIST_API_URL}/tasks",
                headers={"Authorization": f"Bearer {token}"},
                params={"project_id": project_id},
            )
            response.raise_for_status()
            data = response.json()
            todoist_tasks = data.get("results", [])

            today = datetime.now().date().isoformat()
            logger.info(f"📥 Fetching overdue tasks (today: {today})")

            for todoist_task in todoist_tasks:
                # Skip completed tasks
                if todoist_task.get("checked", False):
                    continue

                content = todoist_task.get("content", "")
                due = todoist_task.get("due")

                if not due:
                    continue

                due_date = due.get("date")
                if not due_date:
                    continue

                # Extract date part (YYYY-MM-DD)
                due_date_only = due_date.split("T")[0]

                # Only include tasks with due date in the past (< today)
                if due_date_only < today:
                    overdue_tasks.append({
                        "id": todoist_task.get("id"),
                        "content": content,
                        "due_date": due_date_only,
                        "priority": todoist_task.get("priority"),
                        "labels": todoist_task.get("labels", []),
                    })
                    logger.debug(f"   ⏰ Overdue task: {content} (was due {due_date_only})")

            logger.info(f"📊 Found {len(overdue_tasks)} overdue tasks")
            return overdue_tasks
    except Exception as e:
        logger.error(f"Failed to fetch overdue Todoist tasks: {e}", exc_info=True)
        return []


async def update_todoist_task_due_date(task_id: str, new_due_date: str) -> bool:
    """Update the due date of a Todoist task.

    Args:
        task_id: Todoist task ID
        new_due_date: New due date in YYYY-MM-DD format

    Returns:
        True if successful, False otherwise
    """
    token = await get_todoist_token()
    if not token:
        logger.error("Cannot update task: TODOIST_API_KEY is missing")
        return False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{TODOIST_API_URL}/tasks/{task_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"due_date": new_due_date},
            )
            response.raise_for_status()
            logger.info(f"✓ Updated task {task_id} due date to {new_due_date}")
            return True
    except Exception as e:
        logger.error(f"Failed to update Todoist task {task_id}: {e}")
        return False


async def create_todoist_task(
    content: str,
    due_date: Optional[str] = None,
    priority: int = 1,
    labels: Optional[list] = None,
) -> Optional[str]:
    """Create a new task in Todoist 'Личное' project.

    Args:
        content: Task description
        due_date: Due date in YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format
        priority: 1=Normal, 2=Low, 3=Medium, 4=High (Todoist uses 1-4)
        labels: List of label IDs or names

    Returns:
        Todoist task URL or None on error
    """
    token = await get_todoist_token()
    if not token:
        logger.error("Cannot create task: TODOIST_API_KEY is missing")
        return None

    project_id = await get_project_id(token)
    if not project_id:
        logger.error("Cannot create task: 'Личное' project not found")
        return None

    try:
        task_payload = {
            "content": content,
            "project_id": project_id,
        }

        # Add optional fields
        if due_date:
            task_payload["due_date"] = due_date
        if priority and priority >= 1 and priority <= 4:
            task_payload["priority"] = priority
        if labels:
            task_payload["labels"] = labels

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{TODOIST_API_URL}/tasks",
                headers={"Authorization": f"Bearer {token}"},
                json=task_payload,
            )
            response.raise_for_status()
            task_data = response.json()
            task_id = task_data.get("id")
            logger.info(
                f"Created Todoist task: {task_id} | due_date={due_date} | priority={priority}"
            )

            # Return Todoist web URL
            # Note: Todoist uses task ID strings in URLs
            return f"https://todoist.com/app/task/{task_id}"
    except Exception as e:
        logger.error(f"Failed to create Todoist task: {e}")
        return None
