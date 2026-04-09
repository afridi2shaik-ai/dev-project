# # app/core/metrics.py

# from prometheus_client import Gauge

# ACTIVE_CALLS = Gauge(
#     "vagent_active_calls",
#     "Current number of active voice calls / sessions across the whole application",
#     []   # ← no labels
# )


# app/core/metrics.py
from prometheus_client import Gauge

ACTIVE_CALLS = Gauge(
    "vagent_active_calls",
    "Number of active voice calls/sessions currently running",
)
