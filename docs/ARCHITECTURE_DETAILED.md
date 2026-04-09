# Project Architecture

This document provides a comprehensive overview of the project's architecture, which is inspired by the principles of **Domain-Driven Design (DDD)**. Our goal is to create a system that is scalable, maintainable, and easy for new developers to understand and contribute to.

## Core Concepts

The application is organized into distinct layers, each with a clear set of responsibilities. This separation of concerns is key to maintaining a clean and decoupled architecture.

### 1. API Layer (`src/app/api`)

This is the outermost layer of the application and serves as the entry point for all external interactions.

-   **Responsibility**: To handle incoming requests (HTTP, WebSocket), validate them, and pass them on to the application layer. It is also responsible for formatting the responses.
-   **Contents**: This directory contains FastAPI routers that define the API endpoints for different communication channels (WebRTC, Plivo, Twilio, etc.).
-   **Key Principle**: The API layer should be thin and contain no business logic. Its primary job is to manage the transport of data in and out of the application.

### 2. Application Layer (`src/app/agents`)

This layer orchestrates the core business logic of the application.

-   **Responsibility**: To coordinate the various services and domain objects to perform specific application tasks. In our case, the `BaseAgent` acts as an application service that sets up and manages a voice bot session.
-   **Contents**: This directory contains "agents," which are responsible for defining the behavior of the voice bot, including its personality, the tools it has access to, and the services it uses.
-   **Key Principle**: The application layer is where use cases are implemented. It doesn't contain the business rules themselves but rather directs the domain objects to execute them.

### 3. Domain Layer (`src/app/tools`)

The heart of the application, this layer contains the core business logic and rules.

-   **Responsibility**: To represent the business concepts, rules, and logic of the domain. This is where the unique value of the application resides.
-   **Contents**: This directory contains domain-specific tools and functions that can be used by the agents. Key modules include:
    -   `hangup_tool.py`: Domain-specific action for call termination
    -   `custom_api_tool.py`: Advanced custom API integration with OAuth2 and field validation
    -   `engaging_words_config.py`: **Centralized configuration system** for user-facing engaging phrases
-   **Key Principle**: The domain layer is completely independent of other layers. It should not have any knowledge of the database, the API, or any external services.

#### Engaging Words System

A standout feature of our domain layer is the **centralized engaging words configuration system** (`engaging_words_config.py`). This module provides:

-   **Standardized Configuration**: Single source of truth for all engaging phrases used across the application
-   **Context-Aware Generation**: 8 predefined contexts (assistant, database, API, etc.) with appropriate phrases
-   **11 Utility Functions**: Complete toolkit for engaging words management including validation, generation, and examples
-   **Quality Assurance**: Built-in validation for format checking, action word detection, and length validation
-   **Developer Experience**: Easy-to-use functions for consistent, action-oriented user feedback

**Usage Example**:
```python
from app.tools.engaging_words_config import get_contextual_engaging_words

# Generate context-appropriate engaging words
engaging_words = get_contextual_engaging_words("assistant")  
# → "Fetching your assistant information..."
```

### 4. Infrastructure Layer (`src/app/services`)

This layer provides the technical capabilities to support the other layers, such as interacting with external services.

-   **Responsibility**: To implement the interfaces defined by the application and domain layers for interacting with external systems like databases, message queues, and third-party APIs (OpenAI, ElevenLabs, etc.).
-   **Contents**: This directory contains the service implementations for STT, TTS, and LLMs, plus advanced tool management services:
    -   `stt/`, `llm/`, `tts/`: Service factories for AI services (OpenAI, Sarvam, ElevenLabs, etc.)
    -   `tool_registration_service.py`: Dynamic tool registration and LLM integration service
    -   `auth_service.py`: Authentication and authorization service
-   **Key Principle**: The infrastructure layer is where all the "dirty" work of talking to the outside world happens. It is kept separate from the core logic to make the application more portable and easier to test.

## Folder Structure Breakdown

Here is a detailed breakdown of the project's directory structure:


-   `src/`: The main source code for our application.
    -   `app/`: The root package for the application.
        -   `api/`: **API Layer**. Contains the FastAPI routers and endpoint definitions.
        -   `agents/`: **Application Layer**. Contains the agents that orchestrate the voice bot's behavior.
        -   `core/`: **Cross-Cutting Concerns**. Holds application-wide configuration, logging, tracing, and other core components like the `pipeline_builder` and `agent_config_manager`.
            -   `observers/`: Contains pipeline observers, such as the `MetricsLogger`, which hook into the pipeline's lifecycle to monitor and log data.
            -   `transports/`: Contains the transport-specific services (`webrtc_service.py`, `plivo_service.py`, etc.) that are responsible for bridging the API layer with the Pipecat pipeline.
        -   `schemas/`: **Data Transfer Objects (DTOs)**. Pydantic schemas used for validating API request and response data, including the provider-specific service configurations.
        -   `services/`: **Infrastructure Layer**. Contains the implementations for interacting with external AI services (STT, TTS, LLM).
        -   `templates/`: **Presentation**. HTML and XML templates used by the API layer to respond to requests from telephony providers or to serve web clients.
        -   `tools/`: **Domain Layer**. Contains the core, self-contained business logic and tools available to the agents:
            -   `engaging_words_config.py`: Centralized configuration for engaging phrases
            -   `custom_api_tool.py`: Advanced custom API integration with OAuth2 support
            -   `hangup_tool.py`: Call termination functionality
        -   `utils/`: **Shared Utilities**. Common, reusable functions that don't belong to a specific layer (e.g., saving audio files).
        -   `main.py`: The main entry point for the FastAPI application.

## How to Add a New Feature

When adding a new feature, follow these guidelines to maintain the architectural integrity of the project:

-   **New API Endpoint?** Add a new router in `src/app/api` or add a new endpoint to an existing router.
-   **New Business Rule or Action?** If it's a core piece of business logic, create a new module in `src/app/tools`.
-   **New External Service?** If you need to integrate with a new third-party API, add a new service implementation in `src/app/services`.
-   **New Use Case?** If you are creating a new type of voice bot with a different personality or set of tools, create a new agent in `src/app/agents`.
-   **New Data Shape for the API?** Define a new Pydantic schema in `src/app/schemas`.
-   **New Pipeline Observer?** If you need to monitor the pipeline in a new way, create a new observer in `src/app/core/observers`.

By following this structure, we can ensure that the codebase remains organized, decoupled, and easy to evolve over time.
