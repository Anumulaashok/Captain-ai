"""GitHub watcher — monitors PRs and CI status."""
import logging
import os

from watchers.base import WatchEvent, WatcherBase

log = logging.getLogger(__name__)


class GitHubWatcher(WatcherBase):
    id = "github_watcher"
    name = "GitHub Watcher"
    interval_minutes = 30

    async def watch(self) -> list[WatchEvent]:
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            from integrations.credentials import credentials_store
            t = await credentials_store.get_token("github")
            token = (t or {}).get("access_token", "")

        if not token:
            return []

        events: list[WatchEvent] = []
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.github.com/notifications",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                    },
                    params={"per_page": 10},
                )
                if resp.status_code != 200:
                    return []
                for notif in resp.json():
                    reason = notif.get("reason", "")
                    subject = notif.get("subject", {})
                    title = subject.get("title", "GitHub notification")
                    priority = 3 if reason in ("review_requested", "assign") else 5
                    events.append(WatchEvent(
                        category="prs",
                        title=title[:120],
                        summary=f"{reason}: {title}",
                        priority=priority,
                        meta={"url": notif.get("repository", {}).get("html_url", "")},
                        source=self.id,
                    ))
        except Exception as e:
            log.debug(f"GitHub watcher: {e}")

        return events[:5]
