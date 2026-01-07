"""
Shortcut API client for creating and updating stories.

Used for theme-based ticket creation when issues reach threshold.
"""

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

# Load .env file if present
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.app.shortcut.com/api/v3"


@dataclass
class Story:
    """A Shortcut story."""

    id: str
    name: str
    description: str
    story_type: str  # "bug", "feature", "chore"
    workflow_state_id: Optional[int] = None


class ShortcutClient:
    """Client for Shortcut API."""

    def __init__(
        self,
        api_token: Optional[str] = None,
        dry_run: bool = False,
        backlog_state_id: Optional[int] = None,
        done_state_id: Optional[int] = None,
    ):
        self.api_token = api_token or os.getenv("SHORTCUT_API_TOKEN")
        self.dry_run = dry_run

        # Workflow state IDs from env or params
        self.backlog_state_id = backlog_state_id or self._get_env_int("SHORTCUT_BACKLOG_STATE_ID")
        self.done_state_id = done_state_id or self._get_env_int("SHORTCUT_DONE_STATE_ID")

        if not self.api_token and not self.dry_run:
            logger.warning("SHORTCUT_API_TOKEN not set - operations will be logged only")

    @staticmethod
    def _get_env_int(key: str) -> Optional[int]:
        """Get an integer from environment variable."""
        val = os.getenv(key)
        if val:
            try:
                return int(val)
            except ValueError:
                logger.warning(f"Invalid integer for {key}: {val}")
        return None

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Shortcut-Token": self.api_token or "",
        }

    def _post(self, endpoint: str, data: dict) -> Optional[dict]:
        """Make a POST request to Shortcut API."""
        if self.dry_run or not self.api_token:
            logger.info(f"[DRY RUN] POST {endpoint}: {data}")
            return {"id": "dry-run-id"}

        try:
            response = requests.post(
                f"{BASE_URL}{endpoint}",
                json=data,
                headers=self._headers(),
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Shortcut API error: {e}")
            return None

    def _put(self, endpoint: str, data: dict) -> Optional[dict]:
        """Make a PUT request to Shortcut API."""
        if self.dry_run or not self.api_token:
            logger.info(f"[DRY RUN] PUT {endpoint}: {data}")
            return {"id": "dry-run-id"}

        try:
            response = requests.put(
                f"{BASE_URL}{endpoint}",
                json=data,
                headers=self._headers(),
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Shortcut API error: {e}")
            return None

    def _get(self, endpoint: str) -> Optional[dict]:
        """Make a GET request to Shortcut API."""
        if self.dry_run or not self.api_token:
            logger.info(f"[DRY RUN] GET {endpoint}")
            return None

        try:
            response = requests.get(
                f"{BASE_URL}{endpoint}",
                headers=self._headers(),
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Shortcut API error: {e}")
            return None

    def create_story(
        self,
        name: str,
        description: str,
        story_type: str = "bug",
        project_id: Optional[int] = None,
        workflow_state_id: Optional[int] = None,
    ) -> Optional[str]:
        """
        Create a new story in Shortcut.

        Args:
            name: Story title (will include count prefix like "[3] ...")
            description: Story description with excerpts
            story_type: "bug", "feature", or "chore"
            project_id: Optional project to add story to
            workflow_state_id: Workflow state (required if no project_id)

        Returns:
            Story ID if successful, None otherwise.
        """
        data = {
            "name": name,
            "description": description,
            "story_type": story_type,
        }
        if project_id:
            data["project_id"] = project_id
        if workflow_state_id:
            data["workflow_state_id"] = workflow_state_id

        result = self._post("/stories", data)
        if result:
            story_id = str(result.get("id"))
            logger.info(f"Created Shortcut story: {story_id}")
            return story_id
        return None

    def update_story(
        self,
        story_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> bool:
        """
        Update an existing story.

        Args:
            story_id: ID of story to update
            name: New title (optional)
            description: New description (optional)

        Returns:
            True if successful.
        """
        data = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description

        if not data:
            return True  # Nothing to update

        result = self._put(f"/stories/{story_id}", data)
        if result:
            logger.info(f"Updated Shortcut story: {story_id}")
            return True
        return False

    def get_story(self, story_id: str) -> Optional[Story]:
        """Get a story by ID."""
        result = self._get(f"/stories/{story_id}")
        if result:
            return Story(
                id=str(result["id"]),
                name=result["name"],
                description=result.get("description", ""),
                story_type=result.get("story_type", "bug"),
                workflow_state_id=result.get("workflow_state_id"),
            )
        return None

    def update_story_count(self, story_id: str, new_count: int) -> bool:
        """
        Update the count prefix in a story's title.

        Changes "[3] Title" to "[5] Title" (or adds prefix if missing).
        """
        story = self.get_story(story_id)
        if not story:
            logger.warning(f"Could not fetch story {story_id} to update count")
            # In dry run mode, just log and return success
            if self.dry_run:
                logger.info(f"[DRY RUN] Would update story {story_id} count to [{new_count}]")
                return True
            return False

        # Update count prefix in title
        current_name = story.name
        count_pattern = r"^\[\d+\]\s*"

        if re.match(count_pattern, current_name):
            # Replace existing count
            new_name = re.sub(count_pattern, f"[{new_count}] ", current_name)
        else:
            # Add count prefix
            new_name = f"[{new_count}] {current_name}"

        return self.update_story(story_id, name=new_name)

    def append_to_description(
        self,
        story_id: str,
        new_content: str,
        section_header: str = "## Additional Customer Reports",
    ) -> bool:
        """
        Append content to a story's description.

        If the section header exists, appends under it.
        Otherwise, adds the section at the end.
        """
        story = self.get_story(story_id)
        if not story:
            if self.dry_run:
                logger.info(f"[DRY RUN] Would append to story {story_id}: {new_content[:100]}...")
                return True
            return False

        current_desc = story.description or ""

        if section_header in current_desc:
            # Append to existing section
            new_desc = current_desc + "\n\n" + new_content
        else:
            # Add new section
            new_desc = current_desc + f"\n\n{section_header}\n\n" + new_content

        return self.update_story(story_id, description=new_desc)

    def move_to_done(self, story_id: str, done_state_id: Optional[int] = None) -> bool:
        """
        Move a story to the 'Done' workflow state.

        If done_state_id not provided, attempts to find a 'Done' or 'Completed' state.
        """
        if self.dry_run or not self.api_token:
            logger.info(f"[DRY RUN] Would move story {story_id} to Done")
            return True

        # If no state ID provided, try to get workflows and find Done state
        if done_state_id is None:
            done_state_id = self._find_done_state_id()
            if done_state_id is None:
                logger.warning("Could not find Done state - story not moved")
                return False

        result = self._put(f"/stories/{story_id}", {"workflow_state_id": done_state_id})
        if result:
            logger.info(f"Moved story {story_id} to Done state")
            return True
        return False

    def _find_done_state_id(self) -> Optional[int]:
        """Find the ID of a 'Done' or 'Completed' workflow state."""
        result = self._get("/workflows")
        if not result:
            return None

        for workflow in result:
            for state in workflow.get("states", []):
                name = state.get("name", "").lower()
                if name in ("done", "completed", "closed"):
                    return state.get("id")
        return None

    def add_comment(self, story_id: str, text: str) -> bool:
        """Add a comment to a story."""
        result = self._post(f"/stories/{story_id}/comments", {"text": text})
        if result:
            logger.info(f"Added comment to story {story_id}")
            return True
        return False
