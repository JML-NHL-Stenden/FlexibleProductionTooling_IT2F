from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


@dataclass(frozen=True)
class ArkiteClient:
    """Tiny Arkite REST client to avoid duplicating request/URL/error logic."""

    api_base: str
    api_key: str
    verify_ssl: bool = False
    timeout_sec: int = 20

    def _url(self, path: str) -> str:
        return f"{self.api_base.rstrip('/')}/{path.lstrip('/')}"

    def get_json(self, path: str) -> Any:
        resp = requests.get(
            self._url(path),
            params={"apiKey": self.api_key},
            verify=self.verify_ssl,
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        return resp.json()

    def get_bytes(self, path: str) -> bytes:
        resp = requests.get(
            self._url(path),
            params={"apiKey": self.api_key},
            verify=self.verify_ssl,
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        return resp.content or b""

    # -------- Project-scoped helpers --------

    def list_project_images(self, project_id: str) -> List[Dict[str, Any]]:
        data = self.get_json(f"projects/{project_id}/images/")
        return data if isinstance(data, list) else []

    def get_project_materials(self, project_id: str) -> List[Dict[str, Any]]:
        data = self.get_json(f"projects/{project_id}/materials/")
        return data if isinstance(data, list) else []

    def download_image_bytes(self, project_id: str, image_id: str) -> Optional[bytes]:
        """Return image bytes if available, else None.

        Arkite returns actual bytes at: GET /projects/{projectId}/images/{imageId}/show/
        """
        image_id = str(image_id or "").strip()
        if not image_id or image_id == "0":
            return None

        # Preferred endpoint per API docs.
        candidates = [
            f"projects/{project_id}/images/{image_id}/show/",
            # Fallbacks (some deployments might differ)
            f"projects/{project_id}/images/{image_id}/",
            f"projects/{project_id}/images/{image_id}",
        ]

        for path in candidates:
            try:
                data = self.get_bytes(path)
                if data:
                    return data
            except Exception:
                continue

        # Some servers might respond with a JSON envelope containing base64 bytes.
        for path in candidates:
            try:
                payload = self.get_json(path)
            except Exception:
                continue
            if isinstance(payload, dict):
                for key in ("Data", "data", "Content", "content", "Bytes", "bytes", "Base64", "base64"):
                    raw = payload.get(key)
                    if raw:
                        try:
                            return base64.b64decode(raw)
                        except Exception:
                            pass

        return None

