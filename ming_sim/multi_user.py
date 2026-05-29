from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bootstrap_admin_email() -> str:
    return (os.environ.get("MING_SIM_BOOTSTRAP_ADMIN_EMAIL", "") or "").strip().lower()


@dataclass
class UserContext:
    id: str
    email: str
    role: str
    status: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class MultiUserService:
    """Supabase-backed auth/profile/admin facade."""

    def __init__(self) -> None:
        self.supabase_url = os.environ.get("SUPABASE_URL", "").strip()
        self.supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
        self.supabase_service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        self._anon_client: Optional[Client] = None
        self._service_client: Optional[Client] = None

    def enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

    def _require_enabled(self) -> None:
        if not self.enabled():
            raise RuntimeError("Supabase 未配置：请设置 SUPABASE_URL / SUPABASE_ANON_KEY。")

    def anon_client(self) -> Client:
        self._require_enabled()
        if self._anon_client is None:
            self._anon_client = create_client(self.supabase_url, self.supabase_anon_key)
        return self._anon_client

    def service_client(self) -> Client:
        if not self.supabase_service_role_key:
            raise RuntimeError("缺少 SUPABASE_SERVICE_ROLE_KEY，管理员操作不可用。")
        if self._service_client is None:
            self._service_client = create_client(self.supabase_url, self.supabase_service_role_key)
        return self._service_client

    def _profile_client(self) -> Client:
        if self.supabase_service_role_key:
            return self.service_client()
        return self.anon_client()

    def verify_bearer_token(self, token: str) -> UserContext:
        token = (token or "").strip()
        if not token:
            raise RuntimeError("缺少 token。")
        user_resp = self.anon_client().auth.get_user(token)
        user = getattr(user_resp, "user", None)
        if user is None:
            raise RuntimeError("token 无效或已过期。")
        user_id = str(getattr(user, "id", "") or "").strip()
        if not user_id:
            raise RuntimeError("用户标识无效。")
        email = str(getattr(user, "email", "") or "")
        profile = self.ensure_profile(user_id=user_id, email=email)
        role = str(profile.get("role") or "user")
        status = str(profile.get("status") or "active")
        return UserContext(id=user_id, email=email, role=role, status=status)

    def ensure_profile(self, user_id: str, email: str = "") -> Dict[str, Any]:
        """读取或创建 profile。已存在时只更新 email，不覆盖 role/status。"""
        fallback = {"user_id": user_id, "email": email, "role": "user", "status": "active"}
        try:
            client = self._profile_client()
            query = client.table("profiles").select("*").eq("user_id", user_id).limit(1).execute()
            rows = list(getattr(query, "data", None) or [])
            if rows:
                profile = dict(rows[0])
                if email and email != str(profile.get("email") or ""):
                    client.table("profiles").update(
                        {"email": email, "updated_at": _utc_now_iso()}
                    ).eq("user_id", user_id).execute()
                    profile["email"] = email
                return profile

            role = "admin" if _bootstrap_admin_email() and email.lower() == _bootstrap_admin_email() else "user"
            payload = {
                "user_id": user_id,
                "email": email,
                "role": role,
                "status": "active",
                "updated_at": _utc_now_iso(),
            }
            client.table("profiles").insert(payload).execute()
            return payload
        except Exception as exc:
            logger.warning("ensure_profile failed for %s: %s", user_id, exc)
            return fallback

    def set_auth_access(self, user_id: str, allow: bool) -> None:
        """同步 Supabase Auth：allow=False 时禁止登录。"""
        ban_duration = "none" if allow else "876000h"
        try:
            self.service_client().auth.admin.update_user_by_id(
                user_id,
                {"ban_duration": ban_duration},
            )
        except Exception as exc:
            logger.error("set_auth_access failed for %s allow=%s: %s", user_id, allow, exc)
            raise RuntimeError(f"无法更新 Auth 账号状态：{exc}") from exc

    def list_profiles(self) -> List[Dict[str, Any]]:
        result = self.service_client().table("profiles").select("*").order("updated_at", desc=True).execute()
        return list(getattr(result, "data", None) or [])

    def update_user_status(self, user_id: str, status: str) -> Dict[str, Any]:
        if status not in {"active", "disabled", "deleted"}:
            raise RuntimeError("非法 status。")
        self.set_auth_access(user_id, allow=(status == "active"))
        result = (
            self.service_client()
            .table("profiles")
            .update({"status": status, "updated_at": _utc_now_iso()})
            .eq("user_id", user_id)
            .execute()
        )
        rows = list(getattr(result, "data", None) or [])
        return rows[0] if rows else {"user_id": user_id, "status": status}

    def soft_delete_user(self, user_id: str) -> Dict[str, Any]:
        return self.update_user_status(user_id, "deleted")

    def save_progress_record(
        self,
        user_id: str,
        state_payload: Dict[str, Any],
        save_count: int,
    ) -> None:
        turn = state_payload.get("turn") or {}
        metrics = state_payload.get("metrics") or {}
        payload = {
            "user_id": user_id,
            "year": int(turn.get("year") or 0),
            "period": int(turn.get("period") or 0),
            "turn": int(turn.get("turn") or 0),
            "treasury": state_payload.get("treasury") or "",
            "metrics": metrics,
            "save_count": int(save_count),
            "updated_at": _utc_now_iso(),
        }
        try:
            self.service_client().table("user_progress_records").upsert(payload, on_conflict="user_id").execute()
        except Exception as exc:
            logger.warning("save_progress_record failed for %s: %s", user_id, exc)

    def get_user_progress_record(self, user_id: str) -> Dict[str, Any]:
        result = (
            self.service_client()
            .table("user_progress_records")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = list(getattr(result, "data", None) or [])
        return rows[0] if rows else {}

    def add_audit_log(
        self,
        actor_user_id: str,
        action: str,
        target_user_id: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        row = {
            "actor_user_id": actor_user_id,
            "action": action,
            "target_user_id": target_user_id,
            "payload": payload or {},
            "created_at": _utc_now_iso(),
        }
        try:
            self.service_client().table("admin_audit_logs").insert(row).execute()
        except Exception as exc:
            logger.warning("add_audit_log failed action=%s target=%s: %s", action, target_user_id, exc)
