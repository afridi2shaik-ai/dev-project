import csv
import io
import time
from typing import Any

from pipecat.frames.frames import MetricsFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed


class PlottingObserver(BaseObserver):
    """
    An observer that captures a time-series of metrics suitable for plotting.
    """

    def __init__(self):
        super().__init__()
        self._metrics: list[dict[str, Any]] = []
        self._start_time = time.time()

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if isinstance(frame, MetricsFrame):
            for item in frame.data:
                processor = getattr(item, "processor", "unknown")
                value = getattr(item, "value", None)
                cls_name = item.__class__.__name__

                metric_type = None
                if "TTFB" in cls_name:
                    metric_type = "ttfb_seconds"
                elif "Processing" in cls_name:
                    metric_type = "processing_seconds"

                if metric_type and isinstance(value, (int, float)):
                    self._metrics.append(
                        {
                            "runtime_seconds": time.time() - self._start_time,
                            "metric_type": metric_type,
                            "processor": processor,
                            "value": float(value),
                        }
                    )

    def get_csv_data(self) -> str | None:
        """Returns the collected metrics as a CSV formatted string."""
        if not self._metrics:
            return None

        output = io.StringIO()
        fieldnames = ["runtime_seconds", "metric_type", "processor", "value"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(self._metrics)

        return output.getvalue()
