from __future__ import annotations

from enum import Enum

from pydantic import Field

from app.schemas.base_schema import BaseSchema


class CRMActionType(str, Enum):
    """Type of CRM action to perform after call completion."""

    CREATE_INTERACTION = "create_interaction"  # Log call as new interaction/activity record
    UPDATE_CONTACT = "update_contact"  # Update existing contact with call outcome
    CREATE_LEAD = "create_lead"  # Create new lead if customer doesn't exist
    UPDATE_DEAL = "update_deal"  # Update sales opportunity/deal pipeline
    CUSTOM = "custom"  # Custom action defined by business tool


class ActionExecutionCondition(str, Enum):
    """Condition that determines when a post-call action should execute."""

    ALWAYS = "always"  # Always execute this action
    ON_CUSTOMER_EXISTS = "on_customer_exists"  # Only if pre-call enrichment found customer data
    ON_CUSTOMER_NEW = "on_customer_new"  # Only if pre-call enrichment found NO customer
    ON_CALL_SUCCESS = "on_call_success"  # Only if call completed successfully (not abandoned)


class PostCallRetryConfig(BaseSchema):
    """Configuration for retry behavior of post-call actions.

    Controls how the system handles failures when executing post-call CRM actions,
    including automatic parameter fixing using LLM.
    """

    enabled: bool = Field(True, description="Enable or disable retries for this action. When disabled, actions fail immediately on first error.")

    max_retries: int = Field(3, ge=0, le=10, description="Maximum number of retry attempts (0-10). Default: 3 attempts.")

    retry_on_validation_errors: bool = Field(True, description="Retry on parameter validation failures (e.g., missing required parameters). When enabled, LLM will attempt to fix missing/invalid parameters.")

    retry_on_api_errors: bool = Field(True, description="Retry on API/timeout errors (5xx, timeouts, network errors). Uses exponential backoff.")

    use_llm_for_parameter_fixing: bool = Field(True, description="Use LLM to automatically fix missing or invalid parameters. Generates missing parameters from call summary and context.")

    llm_model: str = Field("gpt-4o-mini", description="LLM model to use for parameter fixing. Default: gpt-4o-mini for cost-effectiveness.")

    llm_temperature: float = Field(0.3, ge=0.0, le=2.0, description="LLM temperature for parameter generation (0.0-2.0). Lower values produce more consistent results. Default: 0.3.")

    llm_system_prompt: str | None = Field(None, description="Custom system prompt template for LLM parameter fixing. Uses constants default if not provided. Supports placeholders: {tool_name}, {tool_description}, {parameter_descriptions}, {validation_errors}, {cleaned_parameters}, {context_text}.")


class PostCallAction(BaseSchema):
    """Configuration for a single post-call CRM action.

    Actions are executed after call completion to update CRM systems with call data.
    Multiple actions can be configured with priority ordering and conditional execution.
    """

    tool_id: str = Field(..., description="Business tool ID to execute for this action. The tool defines the API endpoint and parameters.")

    action_type: CRMActionType = Field(..., description="Type of CRM action: create_interaction (log call), update_contact (update existing record), create_lead (new customer), update_deal (sales pipeline), or custom.")

    execution_condition: ActionExecutionCondition = Field(ActionExecutionCondition.ALWAYS, description="When to execute: always, on_customer_exists (only if enrichment found customer), on_customer_new (only if no customer found), or on_call_success.")

    priority: int = Field(1, ge=1, le=100, description="Execution order priority (1-100). Lower numbers execute first. Use this to ensure actions happen in correct sequence.")

    enabled: bool = Field(True, description="Enable or disable this specific action without removing it from configuration.")

    description: str | None = Field(None, description="Human-readable description of what this action does (for documentation purposes).")

    retry_config: PostCallRetryConfig | None = Field(None, description="Per-action retry configuration. Overrides global default_retry_config if provided.")


class CallLifecycleConfig(BaseSchema):
    """Configuration for call lifecycle management (pre-call enrichment and post-call CRM actions).

    Manages the complete call lifecycle:
    1. Pre-call: Automatically lookup customer data from CRM and enrich conversation context
    2. During call: Customer data available to AI for personalized responses
    3. Post-call: Automatically update CRM with call summary, outcome, and interaction details
    """

    # --- Pre-Call Enrichment ---
    pre_call_enrichment_tool_id: str | None = Field(None, description="Business tool ID for pre-call CRM lookup. Automatically executes on session start to enrich conversation context with customer data (name, status, history, etc.).")

    pre_call_enrichment_enabled: bool = Field(True, description="Enable or disable pre-call CRM enrichment. When disabled, pre_call_enrichment_tool_id is ignored.")

    # --- Post-Call Actions ---
    post_call_actions: list[PostCallAction] = Field(default_factory=list, description="List of actions to execute after call completion. Actions execute in priority order. Common actions: create interaction record, update contact, create lead for new customers.")

    post_call_enabled: bool = Field(True, description="Enable or disable all post-call actions. When disabled, post_call_actions are ignored.")

    # --- Advanced Options ---
    require_enrichment_for_post_actions: bool = Field(False, description="If true, only execute post-call actions if pre-call enrichment was successful. Use this when post-call updates require customer ID from enrichment.")

    parallel_execution: bool = Field(False, description="If true, execute all post-call actions in parallel (faster but no guaranteed order). If false, execute sequentially in priority order (slower but predictable).")

    default_retry_config: PostCallRetryConfig | None = Field(None, description="Global default retry configuration for all post-call actions. Can be overridden per-action using PostCallAction.retry_config.")
