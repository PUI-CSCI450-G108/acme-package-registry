import json
import boto3
from typing import Optional, List

from src.user_management import User, UserRepository


class S3UserRepository(UserRepository):
    """User repository backed by S3 JSON file."""

    def __init__(self, bucket: str, key: str):
        self.s3 = boto3.client("s3")
        self.bucket = bucket
        self.key = key

        self.users: List[User] = self._load_users()

    # ------------------------------
    # Internal Helper Methods
    # ------------------------------

    def _load_users(self) -> List[User]:
        """Load users from S3 as User objects."""
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=self.key)
            raw_json = response["Body"].read().decode("utf-8")
            data = json.loads(raw_json)

            # Convert dictionaries to User objects
            return [User(**u) for u in data]

        except self.s3.exceptions.NoSuchKey:
            # If file does not exist yet
            return []
        except Exception as e:
            print("ERROR loading users.json from S3:", e)
            return []

    def _save_users(self):
        """Save the in-memory user list back to S3."""
        try:
            serializable_users = [u.dict() for u in self.users]

            self.s3.put_object(
                Bucket=self.bucket,
                Key=self.key,
                Body=json.dumps(serializable_users, indent=2),
                ContentType="application/json"
            )
        except Exception as e:
            print("ERROR saving users.json to S3:", e)

    # ------------------------------
    # Required UserRepository Methods
    # ------------------------------

    def add_user(self, user: User) -> None:
        """Add a user, ensuring no duplicates."""
        if self.get_user(user.username):
            raise ValueError(f"User '{user.username}' already exists")

        self.users.append(user)
        self._save_users()

    def get_user(self, username: str) -> Optional[User]:
        """Retrieve a user by username."""
        for user in self.users:
            if user.username == username:
                return user
        return None

    def delete_user(self, username: str) -> bool:
        """Delete a user from the repo."""
        before = len(self.users)
        self.users = [u for u in self.users if u.username != username]

        if len(self.users) != before:
            self._save_users()
            return True
        return False