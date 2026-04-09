import copy
import datetime
import re
from typing import Literal

from loguru import logger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.schemas.log_schema import Artifact, Log, LogType
from app.schemas.session_schema import SessionState

from app.schemas.request_params import LogFilterParams 
class LogManager:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db["logs"]

    def _build_export_query(
        self,
        log_ids: list[str] | None = None,
        session_ids: list[str] | None = None,
        session_states: list[SessionState] | None = None,
        start_date: datetime.datetime | None = None,
        end_date: datetime.datetime | None = None,
        q: str | None = None,
    ) -> dict:
        """Build Mongo query for export endpoints (ids/session_ids/date range)."""
        query: dict = {"agent_type": settings.AGENT_TYPE}

        filter_conditions: list[dict] = []
        if log_ids:
            filter_conditions.append({"_id": {"$in": log_ids}})
        if session_ids:
            filter_conditions.append({"session_id": {"$in": session_ids}})
        if session_states:
            state_vals = [s.value if hasattr(s, "value") else str(s) for s in session_states if s]
            if state_vals:
                state_vals = list(dict.fromkeys(state_vals))
                filter_conditions.append({"session_state": {"$in": state_vals}})
        if start_date and end_date:
            normalized_start = self._to_utc_naive(start_date)
            normalized_end = self._to_utc_naive(end_date)
            filter_conditions.append({"created_at": {"$gte": normalized_start, "$lte": normalized_end}})
        search_condition = self._build_search_condition(q or "")
        if search_condition:
            filter_conditions.append(search_condition)

        if len(filter_conditions) > 1:
            query["$and"] = filter_conditions
        elif len(filter_conditions) == 1:
            query.update(filter_conditions[0])

        return query

    async def save_session_artifacts_log(
        self,
        session_id: str,
        agent_type: str,
        artifacts: list[Artifact],
        transport: str,
        session_state: SessionState,
        duration_seconds: float | None = None,
        assistant_id: str | None = None,
        assistant_name: str | None = None,
        participants: list = [],
    ):
        """Saves a comprehensive log of all artifacts generated during a session.

        Uses upsert pattern to support early logging (PREFLIGHT state) and later updates
        when the session completes. This allows visibility into outbound calls before
        they are answered.
        """
        logger.info(f"Saving log artifacts for session_id: {session_id} into collection '{self.collection.name}'.")

        log_entry = Log(
            session_id=session_id,
            agent_type=agent_type,
            log_type=LogType.SESSION_ARTIFACTS,
            content=artifacts,
            transport=transport,
            assistant_id=assistant_id,
            assistant_name=assistant_name,
            session_state=session_state,
            duration_seconds=duration_seconds,
            participants=participants,
        )

        try:
            update_data = log_entry.model_dump(by_alias=True, exclude_none=True)

            filter_query = {"session_id": session_id, "agent_type": agent_type}
            existing_log = await self.collection.find_one(filter_query, projection={"content": 1})
            if existing_log and existing_log.get("content"):
                update_data["content"] = self._merge_artifact_lists(existing_log["content"], update_data["content"])

            # The `_id` and `created_at` fields are immutable and should only be set when
            # the document is first created. We move them to a `$setOnInsert` block.
            on_insert_data = {"_id": update_data.pop("_id"), "created_at": update_data.pop("created_at")}

            # Update the updated_at timestamp for every save operation
            update_data["updated_at"] = datetime.datetime.now(datetime.UTC)

            # The remaining fields, including the new `updated_at`, will be set on every update.
            await self.collection.update_one(filter_query, {"$set": update_data, "$setOnInsert": on_insert_data}, upsert=True)
            logger.info(f"Successfully saved log artifacts for session_id: {session_id}.")
        except Exception as e:
            logger.error(f"Failed to save log artifacts for session_id: {session_id}. Error: {e}")
            raise

    async def get_log(self, log_id: str) -> Log | None:
        query = {"_id": log_id, "agent_type": settings.AGENT_TYPE}
        log_data = await self.collection.find_one(query)
        return Log(**log_data) if log_data else None

    async def get_logs_for_session(self, session_id: str) -> list[Log]:
        query = {"session_id": session_id, "agent_type": settings.AGENT_TYPE}
        cursor = self.collection.find(query)
        logs_data = await cursor.to_list(length=None)  # Get all logs for the session
        return [Log(**log_data) for log_data in logs_data]

    async def get_logs_for_sessions(self, session_ids: list[str]) -> list[Log]:
        if not session_ids:
            return []
        query = {"session_id": {"$in": session_ids}, "agent_type": settings.AGENT_TYPE}
        cursor = self.collection.find(query)
        logs_data = await cursor.to_list(length=None)
        return [Log(**log_data) for log_data in logs_data]

    async def get_logs_by_ids(self, log_ids: list[str]) -> list[Log]:
        if not log_ids:
            return []
        query = {"_id": {"$in": log_ids}, "agent_type": settings.AGENT_TYPE}
        cursor = self.collection.find(query)
        logs_data = await cursor.to_list(length=None)
        return [Log(**log_data) for log_data in logs_data]

    async def get_logs_by_date_range(self, start_date: datetime.datetime, end_date: datetime.datetime) -> list[Log]:
        """Fetch logs whose created_at falls within the inclusive [start_date, end_date] range."""
        normalized_start = self._to_utc_naive(start_date)
        normalized_end = self._to_utc_naive(end_date)

        query = {
            "created_at": {"$gte": normalized_start, "$lte": normalized_end},
            "agent_type": settings.AGENT_TYPE,
        }
        cursor = self.collection.find(query)
        logs_data = await cursor.to_list(length=None)
        return [Log(**log_data) for log_data in logs_data]

    async def get_logs_with_filters(
        self,
        log_ids: list[str] | None = None,
        session_ids: list[str] | None = None,
        session_states: list[SessionState] | None = None,
        start_date: datetime.datetime | None = None,
        end_date: datetime.datetime | None = None,
        q: str | None = None,
    ) -> list[Log]:
        """Fetch logs combining multiple filters into a single database query.
        
        Args:
            log_ids: Optional list of log IDs to filter by
            session_ids: Optional list of session IDs to filter by
            start_date: Optional start date (inclusive) for created_at filter
            end_date: Optional end date (inclusive) for created_at filter
            
        Returns:
            List of Log objects matching all provided filters
        """
        query = self._build_export_query(
            log_ids=log_ids,
            session_ids=session_ids,
            session_states=session_states,
            start_date=start_date,
            end_date=end_date,
            q=q,
        )
        cursor = self.collection.find(query)
        logs_data = await cursor.to_list(length=None)
        return [Log(**log_data) for log_data in logs_data]

    async def count_logs_with_filters(
        self,
        log_ids: list[str] | None = None,
        session_ids: list[str] | None = None,
        session_states: list[SessionState] | None = None,
        start_date: datetime.datetime | None = None,
        end_date: datetime.datetime | None = None,
        q: str | None = None,
    ) -> int:
        """Count logs matching export filters (no document fetch)."""
        query = self._build_export_query(
            log_ids=log_ids,
            session_ids=session_ids,
            session_states=session_states,
            start_date=start_date,
            end_date=end_date,
            q=q,
        )
        return await self.collection.count_documents(query)

    def _build_list_logs_query(self, filters: LogFilterParams) -> dict:
        """Mongo filter for list/count/stats — same semantics as list_logs pagination."""
        base_query: dict = {"agent_type": settings.AGENT_TYPE}
        and_conditions: list[dict] = []

        def _parse_iso_datetime(value: str | None, *, is_end_bound: bool = False) -> datetime.datetime | None:
            if not value:
                return None
            raw = value.strip()
            if not raw:
                return None
            try:
                # Support trailing 'Z'
                if raw.endswith("Z"):
                    raw = raw[:-1] + "+00:00"
                return datetime.datetime.fromisoformat(raw)
            except Exception:
                # Support date-only input (YYYY-MM-DD).
                # For end bound, expand to end-of-day to keep range inclusive.
                try:
                    parsed_date = datetime.date.fromisoformat(raw)
                    if is_end_bound:
                        return datetime.datetime.combine(parsed_date, datetime.time.max)
                    return datetime.datetime.combine(parsed_date, datetime.time.min)
                except Exception:
                    return None

        # --- participants filters ---
        user_phones = [v for v in (filters.user_phone_number or []) if v]
        if user_phones:
            and_conditions.append(
                {
                    "participants": {
                        "$elemMatch": {"role": "user", "phone_number": {"$in": user_phones}}
                    }
                }
            )

        agent_phones = [v for v in (filters.agent_phone_number or []) if v]
        if agent_phones:
            and_conditions.append(
                {
                    "participants": {
                        "$elemMatch": {"role": "system", "phone_number": {"$in": agent_phones}}
                    }
                }
            )

        customer_names = [v for v in (filters.customer_name or []) if v]
        if customer_names:
            # Match any provided name (case-insensitive, partial).
            name_or = [{"participants": {"$elemMatch": {"role": "user", "name": {"$regex": n, "$options": "i"}}}} for n in customer_names]
            and_conditions.append({"$or": name_or} if len(name_or) > 1 else name_or[0])

        # --- assistant filters ---
        assistant_ids = [v for v in (filters.assistant_id or []) if v]
        if assistant_ids:
            and_conditions.append({"assistant_id": {"$in": assistant_ids}})

        assistant_names = [v for v in (filters.assistant_name or []) if v]
        if assistant_names:
            name_or = [{"assistant_name": {"$regex": n, "$options": "i"}} for n in assistant_names]
            and_conditions.append({"$or": name_or} if len(name_or) > 1 else name_or[0])

        # --- transport filters ---
        transports = [v for v in (filters.transport or []) if v]
        if transports:
            and_conditions.append({"transport": {"$in": transports}})

        # --- session_state / status filters ---
        state_vals: list[str] = []
        if filters.session_state:
            for s in filters.session_state:
                if s:
                    state_vals.append(s.value if hasattr(s, "value") else str(s))
        if state_vals:
            # De-dupe
            state_vals = list(dict.fromkeys(state_vals))
            and_conditions.append({"session_state": {"$in": state_vals}})

        # --- outcome filters (summary artifact content.outcome) ---
        outcomes = [v for v in (filters.outcome or []) if v]
        if outcomes:
            and_conditions.append(
                {
                    "content": {
                        "$elemMatch": {
                            "artifact_type": "summary",
                            "content.outcome": {"$in": outcomes},
                        }
                    }
                }
            )

        # --- created_at range filters ---
        start_date_dt = _parse_iso_datetime(filters.start_date, is_end_bound=False)
        end_date_dt = _parse_iso_datetime(filters.end_date, is_end_bound=True)
        if start_date_dt or end_date_dt:
            rng: dict = {}
            if start_date_dt:
                rng["$gte"] = self._to_utc_naive(start_date_dt)
            if end_date_dt:
                rng["$lte"] = self._to_utc_naive(end_date_dt)
            and_conditions.append({"created_at": rng})

        # --- global search (q) ---
        search_condition = self._build_search_condition(filters.q or "")
        if search_condition:
            and_conditions.append(search_condition)

        # --- session_id filter (exact match per value) ---
        session_ids = [v for v in (filters.session_id or []) if v]
        if session_ids:
            and_conditions.append({"session_id": {"$in": session_ids}})

        if and_conditions:
            return {"$and": [base_query, *and_conditions]}
        return base_query

    @staticmethod
    def _normalize_phone_search_value(value: str) -> str:
        """Normalize phone-like input by removing separators and preserving optional leading '+'."""
        raw = (value or "").strip()
        if not raw:
            return ""
        has_plus = raw.startswith("+")
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            return ""
        return f"+{digits}" if has_plus else digits

    @staticmethod
    def _classify_search_query(value: str) -> Literal["phone", "log_id", "name"]:
        normalized = LogManager._normalize_phone_search_value(value)
        if re.fullmatch(r"\+?\d{7,15}", normalized):
            return "phone"
        trimmed = (value or "").strip()
        if (
            re.fullmatch(r"[0-9a-fA-F]{24}", trimmed)
            or re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}", trimmed)
            or trimmed.startswith("log_")
        ):
            return "log_id"
        return "name"

    @classmethod
    def _build_search_condition(cls, value: str) -> dict | None:
        """Build reusable Mongo search condition for list + stats queries."""
        search_value = (value or "").strip()
        if not search_value:
            return None

        query_type = cls._classify_search_query(search_value)
        if query_type == "phone":
            normalized = cls._normalize_phone_search_value(search_value)
            digits_only = normalized[1:] if normalized.startswith("+") else normalized
            exact_values = [v for v in dict.fromkeys([search_value, normalized, digits_only, f"+{digits_only}"]) if v]
            prefix_values = [v for v in dict.fromkeys([normalized, digits_only, f"+{digits_only}"]) if v]

            phone_or: list[dict] = []
            for val in exact_values:
                # Legacy flattened fields.
                phone_or.append({"user_phone_number": val})
                phone_or.append({"agent_phone_number": val})
                # Current participant-based fields.
                phone_or.append({"participants": {"$elemMatch": {"phone_number": val}}})
            for val in prefix_values:
                # Legacy flattened fields.
                phone_or.append({"user_phone_number": {"$regex": f"^{re.escape(val)}"}})
                phone_or.append({"agent_phone_number": {"$regex": f"^{re.escape(val)}"}})
                # Current participant-based fields.
                phone_or.append({"participants": {"$elemMatch": {"phone_number": {"$regex": f"^{re.escape(val)}"}}}})

            # Also match when query omits country code but stored numbers include it.
            # Example: query=9876543210 should match +919876543210.
            if digits_only:
                suffix_regex = f"{re.escape(digits_only)}$"
                phone_or.append({"user_phone_number": {"$regex": suffix_regex}})
                phone_or.append({"agent_phone_number": {"$regex": suffix_regex}})
                phone_or.append({"participants": {"$elemMatch": {"phone_number": {"$regex": suffix_regex}}}})
            return {"$or": phone_or}

        if query_type == "log_id":
            return {"$or": [{"_id": search_value}, {"log_id": search_value}, {"session_id": search_value}]}

        escaped = re.escape(search_value)
        return {
            "$or": [
                # Legacy flattened fields.
                {"customer_name": {"$regex": escaped, "$options": "i"}},
                {"username": {"$regex": escaped, "$options": "i"}},
                {"participants": {"$elemMatch": {"role": "user", "name": {"$regex": escaped, "$options": "i"}}}},
                {"assistant_name": {"$regex": escaped, "$options": "i"}},
                {"session_id": {"$regex": escaped, "$options": "i"}},
            ]
        }

    async def search_logs(
        self,
        q: str,
        skip: int,
        limit: int,
        session_states: list[SessionState] | None = None,
    ) -> tuple[list[Log], int]:
        """Search logs by query type:
        - phone: `user_phone_number`/`agent_phone_number` (exact + prefix)
        - log_id: exact on `_id` or `log_id`
        - name: partial, case-insensitive on `customer_name`/`assistant_name`/`username`
        """
        base_query: dict = {"agent_type": settings.AGENT_TYPE}
        search_condition = self._build_search_condition(q)
        conditions: list[dict] = [base_query]
        if search_condition:
            conditions.append(search_condition)
        if session_states:
            state_vals = [s.value if hasattr(s, "value") else str(s) for s in session_states if s]
            if state_vals:
                state_vals = list(dict.fromkeys(state_vals))
                conditions.append({"session_state": {"$in": state_vals}})
        query: dict = {"$and": conditions} if len(conditions) > 1 else base_query

        total_count = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        logs_data = await cursor.to_list(length=limit)
        return [Log(**log_data) for log_data in logs_data], total_count

    async def count_logs(self, filters: LogFilterParams) -> int:
        """Count logs matching filters (no document fetch)."""
        query = self._build_list_logs_query(filters)
        return await self.collection.count_documents(query)

    async def count_logs_by_session_state(self, filters: LogFilterParams) -> tuple[int, dict[str, int]]:
        """Single aggregation: $match + $group by session_state (optimal for breakdown)."""
        query = self._build_list_logs_query(filters)
        pipeline = [
            {"$match": query},
            {
                "$group": {
                    "_id": {
                        "$let": {
                            "vars": {
                                "state": {
                                    "$convert": {
                                        "input": "$session_state",
                                        "to": "string",
                                        "onError": "unknown",
                                        "onNull": "unknown",
                                    }
                                }
                            },
                            "in": {
                                "$cond": [
                                    {"$eq": [{"$trim": {"input": "$$state"}}, ""]},
                                    "unknown",
                                    "$$state",
                                ]
                            },
                        }
                    },
                    "count": {"$sum": 1},
                }
            },
        ]
        cursor = self.collection.aggregate(pipeline)
        rows = await cursor.to_list(length=None)
        by_state: dict[str, int] = {}
        for row in rows:
            key = row["_id"]
            by_state[str(key) if key is not None else "unknown"] = int(row["count"])
        total = sum(by_state.values())
        return total, by_state

    async def list_logs(
        self,
        skip: int,
        limit: int,
        filters: LogFilterParams,
    ) -> tuple[list[Log], int]:
        query = self._build_list_logs_query(filters)
        total_count = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        logs_data = await cursor.to_list(length=limit)
        return [Log(**log_data) for log_data in logs_data], total_count

    async def delete_log(self, log_id: str) -> bool:
        query = {"_id": log_id, "agent_type": settings.AGENT_TYPE}
        result = await self.collection.delete_one(query)
        return result.deleted_count > 0

    async def update_session_state(self, session_id: str, new_state: SessionState, duration_seconds: float | None = None):
        """Update the session state in existing log entries for the session.

        Args:
            session_id: The session ID to update
            new_state: The new session state
            duration_seconds: Optional duration in seconds
        """
        try:
            update_data = {"session_state": new_state, "updated_at": datetime.datetime.now(datetime.UTC)}

            if duration_seconds is not None:
                update_data["duration_seconds"] = duration_seconds

            result = await self.collection.update_many({"session_id": session_id, "agent_type": settings.AGENT_TYPE}, {"$set": update_data})

            if result.modified_count > 0:
                logger.info(f"Updated {result.modified_count} log entries for session {session_id} to state {new_state}")
            else:
                logger.debug(f"No log entries found to update for session {session_id}")

        except Exception as e:
            logger.error(f"Failed to update session state in logs for {session_id}: {e}")
            raise

    @staticmethod
    def _merge_artifact_lists(existing: list[dict], new: list[dict]) -> list[dict]:
        """
        Merge artifact lists while preventing duplicates:
        - File-backed artifacts (with s3_location) are tracked by (type, path)
          so earlier uploads (e.g., audio.wav) are preserved unless superseded.
        - Non-file artifacts are unique per artifact_type. Newer artifacts replace
          older ones only when they add meaningful content; otherwise, the original
          data is retained. Dict contents are deep-merged to accumulate metadata.
        """

        non_file_order: list[str] = []
        non_file_artifacts: dict[str, dict] = {}

        file_order: list[tuple[str | None, str | None]] = []
        file_artifacts: dict[tuple[str | None, str | None], dict] = {}

        def process_artifact(artifact: dict):
            art_type = artifact.get("artifact_type")
            s3_location = artifact.get("s3_location")

            if s3_location:
                key = (art_type, s3_location)
                if key not in file_artifacts:
                    file_order.append(key)
                file_artifacts[key] = artifact
                return

            if art_type not in non_file_order:
                non_file_order.append(art_type)

            if art_type in non_file_artifacts:
                non_file_artifacts[art_type] = LogManager._merge_non_file_artifact(non_file_artifacts[art_type], artifact)
            else:
                non_file_artifacts[art_type] = artifact

        for artifact in existing:
            process_artifact(artifact)

        for artifact in new:
            process_artifact(artifact)

        merged: list[dict] = [non_file_artifacts[art_type] for art_type in non_file_order if art_type in non_file_artifacts]
        merged.extend(file_artifacts[key] for key in file_order if key in file_artifacts)

        return merged

    @staticmethod
    def _merge_non_file_artifact(existing: dict, incoming: dict) -> dict:
        """Merge two non-file artifacts for the same artifact_type."""
        if not LogManager._has_meaningful_content(incoming) and LogManager._has_meaningful_content(existing):
            return existing

        merged_artifact = copy.deepcopy(existing)
        merged_artifact.update(incoming)

        existing_content = existing.get("content")
        incoming_content = incoming.get("content")

        if isinstance(existing_content, dict) and isinstance(incoming_content, dict):
            merged_artifact["content"] = LogManager._deep_merge_dict(existing_content, incoming_content)
        elif LogManager._has_meaningful_content({"content": incoming_content}):
            merged_artifact["content"] = incoming_content

        return merged_artifact

    @staticmethod
    def _deep_merge_dict(base: dict, override: dict) -> dict:
        result = copy.deepcopy(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = LogManager._deep_merge_dict(result[key], value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _has_meaningful_content(artifact: dict) -> bool:
        if artifact is None:
            return False

        if artifact.get("s3_location"):
            return True

        content = artifact.get("content")
        if content is None:
            return False
        if isinstance(content, str):
            return content.strip() != ""
        if isinstance(content, (list, tuple, set)):
            return len(content) > 0
        if isinstance(content, dict):
            return any(LogManager._has_meaningful_content({"content": value}) if isinstance(value, dict) else value not in (None, "", [], {}) for value in content.values())
        return True

    @staticmethod
    def _to_utc_naive(dt: datetime.datetime) -> datetime.datetime:
        """Normalize datetime to naive UTC for Mongo queries."""
        if dt.tzinfo:
            return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
