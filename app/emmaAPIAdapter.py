from app.cred import EMMA_ACCOUNT_ID, EMMA_PUBLIC_KEY, EMMA_PRIVATE_KEY
import requests
from requests.auth import HTTPBasicAuth

class EmmaAPIAdapter:

    def __init__(self, account_id=None, public_key=None, private_key=None):
        self.account_id = EMMA_ACCOUNT_ID
        self.public_key = EMMA_PUBLIC_KEY
        self.private_key = EMMA_PRIVATE_KEY
        self.base_url = f"https://api.e2ma.net/{self.account_id}"
        self.auth = HTTPBasicAuth(self.public_key, self.private_key)

    def _get_all_pages(self, path, params=None):
        """Internal helper to retrieve all pages of results (Emma returns up to 500 per page)."""
        params = params or {}
        start = 0
        all_items = []

        while True:
            params["start"] = start
            response = requests.get(f"{self.base_url}{path}", auth=self.auth, params=params)
            response.raise_for_status()
            page_items = response.json()

            if not page_items:
                break  # No more data
            all_items.extend(page_items)
            start += len(page_items)

            # If less than 500 returned, this was the last page
            if len(page_items) < 500:
                break

        return all_items

    def get_groups(self):
        """Fetch all Emma groups (handles pagination)"""
        return self._get_all_pages("/groups")

    def get_group_members(self, group_id):
        """Fetch all members of a specific group (handles pagination)"""
        return self._get_all_pages(f"/groups/{group_id}/members")

    def get_members(self):
        """Fetch all members across the account (handles pagination)"""
        return self._get_all_pages("/members")
