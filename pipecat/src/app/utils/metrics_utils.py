from collections import defaultdict
from typing import Any


class MetricsAccumulator:
    """Accumulates metrics across a pipeline session.

    - Aggregates token usage and TTS character counts across processors
    - Tracks latest TTFB and processing-time per processor
    - Produces a JSON-safe dictionary for persistence
    """

    def __init__(self):
        self._processors: defaultdict[str, dict[str, Any]] = defaultdict(dict)
        self._totals: dict[str, Any] = {
            "llm_prompt_tokens": 0,
            "llm_completion_tokens": 0,
            "tts_characters": 0,
        }
        # Category totals for timing by service type
        self._category_totals: dict[str, dict[str, float]] = {
            "llm": {"processing_seconds": 0.0, "ttfb_seconds": 0.0},
            "stt": {"processing_seconds": 0.0, "ttfb_seconds": 0.0},
            "tts": {"processing_seconds": 0.0, "ttfb_seconds": 0.0},
        }
        # Track first TTFB observed (best indicator of perceived responsiveness)
        self._first_ttfb_overall_s: float | None = None
        self._first_ttfb_by_category: dict[str, float | None] = {"llm": None, "stt": None, "tts": None}
        self._smart_turn_metrics: list[dict[str, Any]] = []

    def _classify_processor(self, processor: str) -> str:
        name = (processor or "").lower()
        if "stt" in name:
            return "stt"
        if "tts" in name:
            return "tts"
        if "llm" in name:
            return "llm"
        return "other"

    def add_ttfb_seconds(self, processor: str, ttfb_s: float):
        self._processors[processor]["last_ttfb_s"] = float(ttfb_s)
        category = self._classify_processor(processor)
        if category in self._category_totals:
            self._category_totals[category]["ttfb_seconds"] += float(ttfb_s)
            # Record first/lowest TTFB per category and overall
            cat_first = self._first_ttfb_by_category.get(category)
            if cat_first is None or float(ttfb_s) < cat_first:
                self._first_ttfb_by_category[category] = float(ttfb_s)
            if self._first_ttfb_overall_s is None or float(ttfb_s) < self._first_ttfb_overall_s:
                self._first_ttfb_overall_s = float(ttfb_s)

    def add_processing_seconds(self, processor: str, processing_s: float):
        self._processors[processor]["last_processing_s"] = float(processing_s)
        category = self._classify_processor(processor)
        if category in self._category_totals:
            self._category_totals[category]["processing_seconds"] += float(processing_s)

    def add_llm_usage(self, processor: str, prompt_tokens: int, completion_tokens: int):
        entry = self._processors[processor]
        entry["llm_prompt_tokens"] = int(entry.get("llm_prompt_tokens", 0) + (prompt_tokens or 0))
        entry["llm_completion_tokens"] = int(entry.get("llm_completion_tokens", 0) + (completion_tokens or 0))
        self._totals["llm_prompt_tokens"] += prompt_tokens or 0
        self._totals["llm_completion_tokens"] += completion_tokens or 0

    def add_tts_characters(self, processor: str, characters: int):
        entry = self._processors[processor]
        entry["tts_characters"] = int(entry.get("tts_characters", 0) + (characters or 0))
        self._totals["tts_characters"] += characters or 0

    def add_smart_turn_metrics(self, processor: str, metrics: dict[str, Any]):
        self._smart_turn_metrics.append({"processor": processor, **metrics})

    def to_dict(self) -> dict[str, Any]:
        processors_list: list[dict[str, Any]] = []
        for name, metrics in self._processors.items():
            processors_list.append({"processor": name, **metrics})
        return {
            "token_usage": {
                "prompt_tokens": self._totals["llm_prompt_tokens"],
                "completion_tokens": self._totals["llm_completion_tokens"],
            },
            "tts_usage": {"characters": self._totals["tts_characters"]},
            "ttfb_metrics": {
                "first_response_seconds": self._first_ttfb_overall_s,
                "by_category_first_seconds": self._first_ttfb_by_category,
                "by_category_total_seconds": {k: v["ttfb_seconds"] for k, v in self._category_totals.items()},
            },
            "timing_totals": {k: v["processing_seconds"] for k, v in self._category_totals.items()},
            "smart_turn_predictions": self._smart_turn_metrics,
            "processors": processors_list,
        }


def accumulate_metrics_from_frame(accumulator: "MetricsAccumulator", metrics_frame: Any) -> None:
    """Add metrics from a MetricsFrame into the accumulator using duck-typing.

    This avoids importing internal metrics classes directly. We only rely on
    the presence of attributes used by Pipecat's MetricsData types.
    """
    try:
        items = getattr(metrics_frame, "data", [])
        for item in items:
            processor = getattr(item, "processor", None) or "unknown"
            value = getattr(item, "value", None)
            # TTFB and Processing use float seconds
            if isinstance(value, (int, float)):
                # Heuristic: if attribute name contains 'ttfb' use TTFB; otherwise processing
                cls_name = item.__class__.__name__.lower()
                if "ttfb" in cls_name:
                    accumulator.add_ttfb_seconds(processor, float(value))
                else:
                    accumulator.add_processing_seconds(processor, float(value))
            else:
                # LLM tokens usage: object with prompt_tokens and completion_tokens
                prompt = getattr(value, "prompt_tokens", None)
                completion = getattr(value, "completion_tokens", None)
                if prompt is not None or completion is not None:
                    accumulator.add_llm_usage(processor, int(prompt or 0), int(completion or 0))
                    continue
                # TTS usage: value is int characters already caught above, but if
                # wrapped differently, try attribute 'value'
                characters = getattr(item, "value", None)
                if isinstance(characters, int):
                    accumulator.add_tts_characters(processor, characters)

                # Smart turn metrics
                if hasattr(item, "is_complete") and hasattr(item, "probability"):
                    accumulator.add_smart_turn_metrics(
                        processor,
                        {
                            "is_complete": item.is_complete,
                            "probability": item.probability,
                            "inference_time_ms": getattr(item, "inference_time_ms", 0),
                            "server_total_time_ms": getattr(item, "server_total_time_ms", 0),
                            "e2e_processing_time_ms": getattr(item, "e2e_processing_time_ms", 0),
                        },
                    )
    except Exception:
        # Best-effort; ignore parsing errors
        pass
