"""
Application-wide constants and configuration values.

This module centralizes magic numbers and configuration constants
to improve maintainability and reduce code duplication.
"""

# Database and Performance Constants
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 300.0

IDLE_TIMEOUT_S = 300
RUNNER_SHUTDOWN_TIMEOUT_S = 20.0

# Language Detection Cache Configuration
LANGUAGE_CACHE_EXPIRY_SECONDS = 300  # 5 minutes
LANGUAGE_CACHE_MAX_SIZE = 1000
LANGUAGE_MIN_TEXT_LENGTH = 10  # Minimum text length for reliable language detection

# TTS Service Configuration
TTS_CONTEXT_CLEANUP_INTERVAL = 5.0  # seconds
TTS_CLEANUP_WAIT_TIME = 0.1  # seconds

# Tool Configuration
MAX_ENGAGING_WORDS_LENGTH = 100
DEFAULT_ENGAGING_WORDS = "Processing your request..."

# Field Validation Constants
MAX_EMAIL_LENGTH = 254  # RFC 5321 limit
MIN_PHONE_DIGITS = 7
MAX_PHONE_DIGITS = 15
MAX_URL_LENGTH = 2048

# Session Management
SESSION_CLEANUP_BATCH_SIZE = 500
SESSION_AUDIT_RETENTION_DAYS = 90

# Audio Processing
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_AUDIO_CHANNELS = 1

# API Rate Limiting
DEFAULT_RATE_LIMIT = "100/minute"
AUTH_RATE_LIMIT = "5/minute"

# Validation Constants
MIN_ASSISTANT_NAME_LENGTH = 1
MAX_ASSISTANT_NAME_LENGTH = 100
MIN_TOOL_NAME_LENGTH = 1
MAX_TOOL_NAME_LENGTH = 50

# Error Handling
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0
EXPONENTIAL_BACKOFF_MULTIPLIER = 2.0

# Post-Call Action Retry Configuration
DEFAULT_POST_CALL_RETRY_MAX_ATTEMPTS = 3
DEFAULT_POST_CALL_RETRY_DELAY_SECONDS = 1.0
DEFAULT_POST_CALL_RETRY_LLM_MODEL = "gpt-4o-mini"
DEFAULT_POST_CALL_RETRY_LLM_TEMPERATURE = 0.3

# Warm Transfer Defaults
WARM_TRANSFER_SPEECH_CHARS_PER_SECOND = 12  # Conservative estimate for TTS playback speed
WARM_TRANSFER_SPEECH_BUFFER_SECONDS = 3.0  # Increased buffer to ensure TTS completes before hold music
WARM_TRANSFER_HOLD_MUSIC_STOP_DELAY = 1.0
WARM_TRANSFER_CONFERENCE_JOIN_DELAY = 2.0
WARM_TRANSFER_SUPERVISOR_MESSAGE_DELAY = 1.5
WARM_TRANSFER_CONFERENCE_PREFIX = "transfer_"
WARM_TRANSFER_TIMEOUT_SECONDS = 60  # Timeout for supervisor to answer (default: 60 seconds)
SUPERVISOR_DISCONNECT_MESSAGE_BUSY = "The supervisor couldn't join because their line is busy."
SUPERVISOR_DISCONNECT_MESSAGE_NO_ANSWER = "The supervisor wasn't able to answer right now."
SUPERVISOR_DISCONNECT_MESSAGE_ENDED = "The supervisor has left the call."
SUPERVISOR_DISCONNECT_MESSAGE_TIMEOUT = "We couldn't reach the supervisor at this time. Please try again later."
CUSTOMER_DISCONNECT_MESSAGE = "The customer has disconnected from the call."

# Post-Call Action LLM Parameter Fixing System Prompt Template
DEFAULT_POST_CALL_RETRY_LLM_SYSTEM_PROMPT_TEMPLATE = """You are an intelligent assistant that fixes parameter validation errors for CRM integration tools.

Your task is to analyze a failed API call and generate the correct parameters based on:
1. The tool's purpose and requirements
2. The validation errors that occurred
3. The call summary and session context
4. The parameter definitions and examples

Tool Information:

- Name: {tool_name}
- Description: {tool_description}

Required Parameters:

{parameter_descriptions}

Validation Errors:

{validation_errors}

Current Parameters Provided (cleaned, template placeholders removed):

{cleaned_parameters}

{context_text}

CRITICAL INSTRUCTIONS FOR PARAMETER EXTRACTION:

1. ONLY generate parameters that are defined in the tool's parameter schema above (from Required Parameters section)
   - DO NOT add parameters that are not in the parameter schema
   - DO NOT add extra parameters like "note_content" unless it's explicitly defined in the parameter schema
   - Only work with parameters that exist in the tool's definition

2. Enrich parameters with ALL available information from context:
   - Your primary goal: Extract and provide ANY parameter value that exists in the tool's schema AND can be found in the context
   - For EVERY parameter in the tool's schema (check "Required Parameters" section above):
     * If the value exists in enrichment data, extract it
     * If the value exists in call summary text, extract it  
     * If the value exists in session context, extract it
   - This applies to ALL parameters (required AND optional) - if you can extract it, include it
   - Validation errors are hints about what's missing, but you should proactively provide ALL available parameters
   - Example: If tool has firstname/lastname parameters and call summary mentions a name, extract it regardless of validation errors

3. CRITICAL: Extract user names from call summary text - THIS IS MANDATORY:
   - If the tool's schema includes "firstname" or "lastname" parameters, you MUST check the call summary text for user names
   - User names are often mentioned in call summaries in patterns like:
     * "The user, [Name], ..." (e.g., "The user, Ajay Sai, initiated...")
     * "[Name], the user, ..." (e.g., "Ajay Sai, the user, initiated...")
     * "user [Name]" or "[Name] said" or "[Name] expressed"
   - EXAMPLES of name extraction from call summaries:
     * Call summary: "Ajay Sai, the user, initiated the conversation..."
       → Extract: firstname: "Ajay", lastname: "Sai"
     * Call summary: "The user, John Doe, contacted..."
       → Extract: firstname: "John", lastname: "Doe"
     * Call summary: "Mary Jane Watson expressed interest..."
       → Extract: firstname: "Mary", lastname: "Jane Watson" (keep middle names with lastname)
   - Parse full names intelligently:
     * Two words: "John Doe" → firstname: "John", lastname: "Doe"
     * Three words: "Ajay Sai Goud" → firstname: "Ajay", lastname: "Sai Goud"
     * Four+ words: "Mary Jane Watson Smith" → firstname: "Mary", lastname: "Jane Watson Smith"
   - If the tool requires "contact_name" (full name), use the complete name as found in the summary
   - If the tool requires separate "firstname" and "lastname", split the name appropriately (first word = firstname, rest = lastname)
   - Priority: enrichment data > call summary text > omit parameter
   - If you see a name in the call summary and the tool schema includes firstname/lastname parameters, you MUST extract it - do not skip it!

4. Context extraction priority:
   - Check enrichment data first (enrichment_contact fields)
   - Check call summary text second (look for names, details mentioned in conversation)
   - Check session context third (phone, email, etc.)

5. CRITICAL: NEVER include template placeholders like {{firstname}}, {{lastname}}, {{email}}, {{customer_id}}, etc.
   - If you see template placeholders in the current parameters, DO NOT include them in your response
   - If a parameter value is a template placeholder (e.g., "{{email}}"), either:
     a) Extract the actual value from enrichment data or context and use that, OR
     b) Omit that parameter entirely from your response
   - Template placeholders will be automatically removed by the system - do not return them
   - Your output must contain ONLY actual values, never template syntax like {{anything}}

6. NEVER generate fake or placeholder values:
   - If customer_id is required but not found in enrichment data, DO NOT generate fake values like "CUST-12345"
   - If email is required but not available, DO NOT generate fake email addresses
   - If firstname/lastname are required but not available, DO NOT generate fake names
   - Only include parameters with real, extractable values from the context provided

7. Use the call summary and context to generate meaningful values for parameters that:
   - Are defined in the tool's parameter schema
   - Can be reasonably extracted from the context provided (enrichment data, call summary, session context)
   - This applies to both required and optional parameters - extract them if available

8. Return ONLY a valid JSON object with the corrected parameters (no template placeholders, no fake values, no extra parameters)

9. Include optional parameters:
   - Extract optional parameters if their values can be found in the context (enrichment data, call summary, session context)
   - Do not skip optional parameters just because they're optional - if you can extract them, include them
   - Only omit optional parameters if their values truly cannot be found in any available context

10. Ensure all parameter values match their specified types

11. For nested enrichment data, use dot notation to extract:
   - enrichment_contact.firstname → firstname parameter
   - enrichment_contact.lastname → lastname parameter
   - enrichment_contact.id → customer_id parameter

12. If a required parameter cannot be extracted from context and enrichment data is missing (e.g., "found": false), omit that parameter and let the validation error surface rather than generating a fake value

Return the fixed parameters as a JSON object."""

# Customer Profile Configuration
CUSTOMER_PROFILE_MAX_RECENT_SUMMARIES = 4  # Number of recent call summaries to keep individually
CUSTOMER_PROFILE_AGGREGATION_LLM_MODEL = "gpt-4o-mini"
CUSTOMER_PROFILE_AGGREGATION_LLM_TEMPERATURE = 0.3
CUSTOMER_PROFILE_AGGREGATION_MAX_TOKENS = 600
CUSTOMER_PROFILE_AGGREGATION_MAX_SUMMARY_WORDS = 500

# Customer Profile LLM Extraction Configuration
# Used for extracting customer details (name, language, interests) from call summaries
CUSTOMER_PROFILE_EXTRACTION_LLM_MODEL = "gpt-4o-mini"
CUSTOMER_PROFILE_EXTRACTION_LLM_TEMPERATURE = 0.3
CUSTOMER_PROFILE_EXTRACTION_MAX_TOKENS = 500

# AI Extraction - Required Fields
# These fields will ALWAYS be present in ai_extracted_data (set to None if not found)
# Add or remove fields as needed (e.g., add "phone" later)
CUSTOMER_PROFILE_AI_REQUIRED_FIELDS = ["language_preference", "name", "email"]