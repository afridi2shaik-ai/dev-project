# Pipecat-Service Documentation

Welcome to the **Pipecat-Service** comprehensive documentation hub! This guide provides complete coverage of the voice AI platform built on the Pipecat SDK, spanning architecture, implementation, deployment, and advanced use cases.

---

## 📚 Documentation Overview

The documentation is organized into **logical sections** to help you find exactly what you need:

### 🚀 **Getting Started**
- **[QUICK_START.md](QUICK_START.md)** - Begin here! Get the platform running in minutes
- **[ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)** - High-level system design and component interactions
- **[ARCHITECTURE_DETAILED.md](ARCHITECTURE_DETAILED.md)** - Deep technical architecture details

### 🏗️ **Core Architecture & Design**
- **[ADVANCED_PIPELINE_ARCHITECTURE.md](ADVANCED_PIPELINE_ARCHITECTURE.md)** - Pipecat pipeline internals, frame flow, and processor chain
- **[FILE_STRUCTURE.md](FILE_STRUCTURE.md)** - Project directory layout and file organization
- **[DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md)** - MongoDB schemas and data models

### 🔧 **Configuration & Setup**
- **[DEPLOYMENT_CONFIGURATION.md](DEPLOYMENT_CONFIGURATION.md)** - Environment variables, Docker setup, and performance tuning
- **[AUTHENTICATION_AUTHORIZATION.md](AUTHENTICATION_AUTHORIZATION.md)** - Auth0 integration, JWT tokens, role-based access control
- **[OUTBOUND_CALL_TOKEN_FLOW.md](OUTBOUND_CALL_TOKEN_FLOW.md)** - Token management during outbound call initiation and assistant config retrieval

### 🤖 **Agent & LLM Configuration**
- **[CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md)** - AI-powered call summaries and automatic profile extraction
- **[LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md)** - OpenAI, Gemini integration, prompt engineering, tool registration
- **[STT_TTS_SERVICES_GUIDE.md](STT_TTS_SERVICES_GUIDE.md)** - Speech-to-Text and Text-to-Speech provider implementations

### 👥 **Customer & Context Management**
- **[CUSTOMER_PROFILES.md](CUSTOMER_PROFILES.md)** - Customer identity management and profile structure
- **[CUSTOMER_PROFILE_MANAGER_GUIDE.md](CUSTOMER_PROFILE_MANAGER_GUIDE.md)** - Profile manager utilities and operations
- **[CONTEXT_ENRICHMENT.md](CONTEXT_ENRICHMENT.md)** - CRM enrichment, language detection, dynamic context building

### 🛠️ **Advanced Topics**
- **[BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md)** - Building custom business tools and integrations
- **[CUSTOM_PROCESSORS_GUIDE.md](CUSTOM_PROCESSORS_GUIDE.md)** - Custom pipeline processors (AudioBuffer, Transcription, Classification, etc.)
- **[SESSION_MANAGEMENT.md](SESSION_MANAGEMENT.md)** - Call session lifecycle, state management, and tracking
- **[TELEPHONY_FLOWS.md](TELEPHONY_FLOWS.md)** - Plivo & Twilio WebSocket integration, call routing, and telephony patterns

### 📊 **Operations & Support**
- **[API_GUIDE.md](API_GUIDE.md)** - Complete REST API reference with all endpoints
- **[DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md)** - Logging, tracing, monitoring, performance metrics
- **[MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md)** - Migration guides and breaking changes
- **[CLEANUP_SUMMARY.md](CLEANUP_SUMMARY.md)** - Cleanup procedures and maintenance tasks

### 📖 **Guides & Examples**
- **[guides/multi-step-workflows.md](guides/multi-step-workflows.md)** - Multi-step API workflow examples
- **[guides/engaging-words-system.md](guides/engaging-words-system.md)** - Engaging words and conversational patterns
- **[guides/tool-usage-examples.md](guides/tool-usage-examples.md)** - Practical business tool usage examples

---

## 🎯 Quick Navigation by Role

### 👨‍💻 **Backend Developers** - Build & Integrate Features
**Recommended Reading Order:**

1. [QUICK_START.md](QUICK_START.md) - Set up your environment
2. [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) - Understand the system
3. [FILE_STRUCTURE.md](FILE_STRUCTURE.md) - Navigate the codebase
4. [ADVANCED_PIPELINE_ARCHITECTURE.md](ADVANCED_PIPELINE_ARCHITECTURE.md) - Learn how pipelines work
5. [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md) - Understand LLM integration
6. [BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md) - Create custom tools
7. [CUSTOM_PROCESSORS_GUIDE.md](CUSTOM_PROCESSORS_GUIDE.md) - Build custom processors
8. [SESSION_MANAGEMENT.md](SESSION_MANAGEMENT.md) - Manage call sessions
9. [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md) - Understand data models
10. [API_GUIDE.md](API_GUIDE.md) - Reference all endpoints
11. [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md) - Debug and trace issues

### 🔧 **DevOps/Infrastructure Engineers** - Deploy & Monitor
**Recommended Reading Order:**

1. [QUICK_START.md](QUICK_START.md) - Initial setup
2. [DEPLOYMENT_CONFIGURATION.md](DEPLOYMENT_CONFIGURATION.md) - Configure production environment
3. [AUTHENTICATION_AUTHORIZATION.md](AUTHENTICATION_AUTHORIZATION.md) - Set up Auth0 and security
4. [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md) - Database setup
5. [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md) - Monitoring and alerts
6. [STT_TTS_SERVICES_GUIDE.md](STT_TTS_SERVICES_GUIDE.md) - Configure speech services
7. [DEPLOYMENT_CONFIGURATION.md](DEPLOYMENT_CONFIGURATION.md) - Performance tuning

### 📊 **Integration Partners** - Integrate & Extend
**Recommended Reading Order:**

1. [QUICK_START.md](QUICK_START.md) - Overview
2. [API_GUIDE.md](API_GUIDE.md) - Learn all APIs
3. [BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md) - Understand tool integration
4. [CUSTOMER_PROFILES.md](CUSTOMER_PROFILES.md) - Manage customer data
5. [guides/multi-step-workflows.md](guides/multi-step-workflows.md) - Real-world workflow examples
6. [CONTEXT_ENRICHMENT.md](CONTEXT_ENRICHMENT.md) - Enrich customer context
7. [TELEPHONY_FLOWS.md](TELEPHONY_FLOWS.md) - Understand telephony integration

### 🤖 **AI/ML Specialists** - Optimize AI Behavior
**Recommended Reading Order:**

1. [CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md) - AI summaries & extraction
2. [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md) - LLM configuration & prompting
3. [CONTEXT_ENRICHMENT.md](CONTEXT_ENRICHMENT.md) - Language detection & context
4. [ADVANCED_PIPELINE_ARCHITECTURE.md](ADVANCED_PIPELINE_ARCHITECTURE.md) - Pipeline optimization
5. [STT_TTS_SERVICES_GUIDE.md](STT_TTS_SERVICES_GUIDE.md) - Speech service tuning
6. [CUSTOMER_PROFILES.md](CUSTOMER_PROFILES.md) - Profile-based personalization

---

## 🗂️ Complete Document Hierarchy

```
docs/
├── README.md (this file - start here!)
│
├── GETTING STARTED
├── QUICK_START.md
├── ARCHITECTURE_OVERVIEW.md
├── ARCHITECTURE_DETAILED.md
│
├── CORE DESIGN
├── ADVANCED_PIPELINE_ARCHITECTURE.md
├── FILE_STRUCTURE.md
├── DATABASE_COLLECTIONS_STRUCTURE.md
│
├── CONFIGURATION
├── DEPLOYMENT_CONFIGURATION.md
├── AUTHENTICATION_AUTHORIZATION.md
├── OUTBOUND_CALL_TOKEN_FLOW.md
│
├── AI & LLM
├── CONFIGURABLE_SUMMARIES.md
├── LLM_SERVICES_GUIDE.md
├── STT_TTS_SERVICES_GUIDE.md
│
├── CUSTOMER & CONTEXT
├── CUSTOMER_PROFILES.md
├── CUSTOMER_PROFILE_MANAGER_GUIDE.md
├── CONTEXT_ENRICHMENT.md
│
├── ADVANCED FEATURES
├── BUSINESS_TOOLS_GUIDE.md
├── CUSTOM_PROCESSORS_GUIDE.md
├── SESSION_MANAGEMENT.md
├── TELEPHONY_FLOWS.md
│
├── OPERATIONS
├── API_GUIDE.md
├── DEBUGGING_OBSERVABILITY.md
├── MIGRATION_SUMMARY.md
├── CLEANUP_SUMMARY.md
│
├── guides/
│   ├── multi-step-workflows.md
│   ├── engaging-words-system.md
│   └── tool-usage-examples.md
│
└── NEW_DOCUMENTATION_SUMMARY.md (summary of new docs added)
```

---

## 🔗 Documentation Connection Map

### **Startup & Setup Path**
```
QUICK_START.md
    ↓
DEPLOYMENT_CONFIGURATION.md
    ↓
AUTHENTICATION_AUTHORIZATION.md
    ↓
DATABASE_COLLECTIONS_STRUCTURE.md
    ↓
API_GUIDE.md (Test all endpoints)
```

### **Architecture Understanding Path**
```
ARCHITECTURE_OVERVIEW.md
    ↓
ADVANCED_PIPELINE_ARCHITECTURE.md
    ↓
CUSTOM_PROCESSORS_GUIDE.md
    ↓
FILE_STRUCTURE.md
```

### **LLM & AI Configuration Path**
```
LLM_SERVICES_GUIDE.md
    ↓
CONFIGURABLE_SUMMARIES.md
    ↓
CONTEXT_ENRICHMENT.md
    ↓
CUSTOMER_PROFILES.md
    ↓
CUSTOM_PROCESSORS_GUIDE.md (Custom processors)
```

### **Business Integration Path**
```
BUSINESS_TOOLS_GUIDE.md
    ↓
API_GUIDE.md (Business tools endpoints)
    ↓
guides/tool-usage-examples.md
    ↓
guides/multi-step-workflows.md
```

### **Voice & Speech Path**
```
STT_TTS_SERVICES_GUIDE.md
    ↓
DEPLOYMENT_CONFIGURATION.md (Provider setup)
    ↓
CONTEXT_ENRICHMENT.md (Language detection)
    ↓
CUSTOM_PROCESSORS_GUIDE.md (Audio processors)
```

### **Session & Call Management Path**
```
SESSION_MANAGEMENT.md
    ↓
TELEPHONY_FLOWS.md
    ↓
DATABASE_COLLECTIONS_STRUCTURE.md (Session schema)
    ↓
API_GUIDE.md (Session endpoints)
```

### **Monitoring & Troubleshooting Path**
```
DEBUGGING_OBSERVABILITY.md
    ↓
API_GUIDE.md (Debug endpoints)
    ↓
MIGRATION_SUMMARY.md (Known issues)
    ↓
CLEANUP_SUMMARY.md (Maintenance)
```

---

## 🚀 Common Use Cases & Recommended Docs

### **I want to...**

| Task | Documentation Path |
|------|-------------------|
| **Get the service running** | QUICK_START.md → DEPLOYMENT_CONFIGURATION.md |
| **Understand the architecture** | ARCHITECTURE_OVERVIEW.md → ADVANCED_PIPELINE_ARCHITECTURE.md → FILE_STRUCTURE.md |
| **Create a voice agent** | QUICK_START.md → LLM_SERVICES_GUIDE.md → guides/multi-step-workflows.md |
| **Build a business tool** | BUSINESS_TOOLS_GUIDE.md → API_GUIDE.md → guides/tool-usage-examples.md |
| **Integrate with Plivo/Twilio** | TELEPHONY_FLOWS.md → API_GUIDE.md → DEPLOYMENT_CONFIGURATION.md |
| **Enable AI summaries** | CONFIGURABLE_SUMMARIES.md → LLM_SERVICES_GUIDE.md → SESSION_MANAGEMENT.md |
| **Manage customer profiles** | CUSTOMER_PROFILES.md → API_GUIDE.md → CUSTOMER_PROFILE_MANAGER_GUIDE.md |
| **Build custom processors** | CUSTOM_PROCESSORS_GUIDE.md → ADVANCED_PIPELINE_ARCHITECTURE.md → API_GUIDE.md |
| **Configure speech services** | STT_TTS_SERVICES_GUIDE.md → DEPLOYMENT_CONFIGURATION.md |
| **Add context enrichment** | CONTEXT_ENRICHMENT.md → CUSTOMER_PROFILES.md → guides/multi-step-workflows.md |
| **Set up security** | AUTHENTICATION_AUTHORIZATION.md → DEPLOYMENT_CONFIGURATION.md |
| **Understand outbound call tokens** | OUTBOUND_CALL_TOKEN_FLOW.md → AUTHENTICATION_AUTHORIZATION.md |
| **Monitor & debug** | DEBUGGING_OBSERVABILITY.md → API_GUIDE.md |
| **Deploy to production** | DEPLOYMENT_CONFIGURATION.md → AUTHENTICATION_AUTHORIZATION.md → DEBUGGING_OBSERVABILITY.md |
| **Handle sessions** | SESSION_MANAGEMENT.md → API_GUIDE.md → DATABASE_COLLECTIONS_STRUCTURE.md |
| **Troubleshoot issues** | MIGRATION_SUMMARY.md → CLEANUP_SUMMARY.md → DEBUGGING_OBSERVABILITY.md |

---

## 📝 Core Concepts

### **Domain-Driven Design (DDD)**
The platform is built on DDD principles with 4 distinct layers:
- **API Layer** (`src/app/api`): Request/response handling, endpoint definitions
- **Application Layer** (`src/app/agents`): Orchestration, use case coordination
- **Domain Layer** (`src/app/tools`): Core business logic, independent rules
- **Infrastructure Layer** (`src/app/services`): External system integration

→ **Learn more**: [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)

### **Frame-Based Pipelines**
The Pipecat SDK uses a frame-based architecture for real-time processing:
- **Frames**: Atomic data units (Audio, Text, Control frames)
- **Pipeline**: Chain of processors that handle frames
- **Processors**: Transform or react to frames (STT, TTS, LLM, Custom)
- **Observers**: Monitor pipeline events and collect metrics

→ **Learn more**: [ADVANCED_PIPELINE_ARCHITECTURE.md](ADVANCED_PIPELINE_ARCHITECTURE.md)

### **Configuration-Driven Architecture**
Voice agents are configured via `AgentConfig` without code changes:
- Supports multiple LLMs (OpenAI, Gemini)
- Configurable STT/TTS providers
- Dynamic context building
- Flexible business tool integration

→ **Learn more**: [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md)

### **Multi-Tenant Isolation**
All data is scoped by `tenant_id`:
- Complete data isolation per tenant
- Role-based access control (RBAC)
- Built-in from the ground up

→ **Learn more**: [AUTHENTICATION_AUTHORIZATION.md](AUTHENTICATION_AUTHORIZATION.md)

### **Real-Time Voice Communication**
Telephony integration via WebSocket streams:
- Plivo & Twilio support
- Real-time audio streaming
- Session management and state tracking
- Call recording and logging

→ **Learn more**: [TELEPHONY_FLOWS.md](TELEPHONY_FLOWS.md)

### **AI-Powered Call Processing**
Advanced AI capabilities built-in:
- Automatic call summaries
- Profile extraction and enrichment
- Language detection and context
- Intent classification

→ **Learn more**: [CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md)

---

## 🔍 Search & Reference Guide

### **By Technical Concept**
- 🎙️ Audio Processing → [STT_TTS_SERVICES_GUIDE.md](STT_TTS_SERVICES_GUIDE.md), [CUSTOM_PROCESSORS_GUIDE.md](CUSTOM_PROCESSORS_GUIDE.md)
- 🤖 LLM Integration → [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md), [CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md)
- 📊 Database Schema → [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md)
- 🔐 Security & Auth → [AUTHENTICATION_AUTHORIZATION.md](AUTHENTICATION_AUTHORIZATION.md), [DEPLOYMENT_CONFIGURATION.md](DEPLOYMENT_CONFIGURATION.md)
- 📞 Telephony → [TELEPHONY_FLOWS.md](TELEPHONY_FLOWS.md), [API_GUIDE.md](API_GUIDE.md)
- 🛠️ Custom Code → [BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md), [CUSTOM_PROCESSORS_GUIDE.md](CUSTOM_PROCESSORS_GUIDE.md)
- 👤 Customer Data → [CUSTOMER_PROFILES.md](CUSTOMER_PROFILES.md), [CONTEXT_ENRICHMENT.md](CONTEXT_ENRICHMENT.md)
- ⚙️ Configuration → [DEPLOYMENT_CONFIGURATION.md](DEPLOYMENT_CONFIGURATION.md), [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md)
- 📈 Monitoring → [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md), [API_GUIDE.md](API_GUIDE.md)
- 🔄 Session Management → [SESSION_MANAGEMENT.md](SESSION_MANAGEMENT.md), [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md)

### **By Use Case**
- **Outbound Calling** → [TELEPHONY_FLOWS.md](TELEPHONY_FLOWS.md), [OUTBOUND_CALL_TOKEN_FLOW.md](OUTBOUND_CALL_TOKEN_FLOW.md), [API_GUIDE.md](API_GUIDE.md), [SESSION_MANAGEMENT.md](SESSION_MANAGEMENT.md)
- **Inbound IVR** → [CUSTOM_PROCESSORS_GUIDE.md](CUSTOM_PROCESSORS_GUIDE.md), [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md)
- **Call Recording** → [SESSION_MANAGEMENT.md](SESSION_MANAGEMENT.md), [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md)
- **Customer Enrichment** → [CUSTOMER_PROFILES.md](CUSTOMER_PROFILES.md), [CONTEXT_ENRICHMENT.md](CONTEXT_ENRICHMENT.md)
- **AI Summaries** → [CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md), [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md)
- **Business Integration** → [BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md), [API_GUIDE.md](API_GUIDE.md)
- **Multi-Language Support** → [CONTEXT_ENRICHMENT.md](CONTEXT_ENRICHMENT.md), [STT_TTS_SERVICES_GUIDE.md](STT_TTS_SERVICES_GUIDE.md)
- **Error Handling** → [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md), [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md)

---

## 📋 Feature Documentation Matrix

| Feature | Core Docs | Reference | Configuration | Examples |
|---------|-----------|-----------|-----------------|----------|
| **Voice Agents** | QUICK_START.md | LLM_SERVICES_GUIDE.md | DEPLOYMENT_CONFIGURATION.md | guides/ |
| **LLM Integration** | LLM_SERVICES_GUIDE.md | API_GUIDE.md | LLM_SERVICES_GUIDE.md | guides/ |
| **Speech Services** | STT_TTS_SERVICES_GUIDE.md | API_GUIDE.md | DEPLOYMENT_CONFIGURATION.md | - |
| **Business Tools** | BUSINESS_TOOLS_GUIDE.md | API_GUIDE.md | LLM_SERVICES_GUIDE.md | guides/tool-usage-examples.md |
| **Custom Processors** | CUSTOM_PROCESSORS_GUIDE.md | ADVANCED_PIPELINE_ARCHITECTURE.md | - | CUSTOM_PROCESSORS_GUIDE.md |
| **Customer Profiles** | CUSTOMER_PROFILES.md | API_GUIDE.md | - | CUSTOMER_PROFILE_MANAGER_GUIDE.md |
| **AI Summaries** | CONFIGURABLE_SUMMARIES.md | API_GUIDE.md | LLM_SERVICES_GUIDE.md | - |
| **Context Enrichment** | CONTEXT_ENRICHMENT.md | - | DEPLOYMENT_CONFIGURATION.md | - |
| **Telephony** | TELEPHONY_FLOWS.md | API_GUIDE.md | DEPLOYMENT_CONFIGURATION.md | guides/multi-step-workflows.md |
| **Token Flow (Outbound)** | OUTBOUND_CALL_TOKEN_FLOW.md | AUTHENTICATION_AUTHORIZATION.md | DEPLOYMENT_CONFIGURATION.md | - |
| **Session Management** | SESSION_MANAGEMENT.md | API_GUIDE.md | DATABASE_COLLECTIONS_STRUCTURE.md | - |
| **Authentication** | AUTHENTICATION_AUTHORIZATION.md | API_GUIDE.md | DEPLOYMENT_CONFIGURATION.md | - |
| **Monitoring** | DEBUGGING_OBSERVABILITY.md | API_GUIDE.md | DEPLOYMENT_CONFIGURATION.md | - |

---

## 🔗 Document Dependencies

### **Foundation Documents** (read first)
These documents provide essential context:
- QUICK_START.md
- ARCHITECTURE_OVERVIEW.md
- FILE_STRUCTURE.md

### **Configuration Documents** (setup required)
Configure the system before using features:
- DEPLOYMENT_CONFIGURATION.md
- AUTHENTICATION_AUTHORIZATION.md
- STT_TTS_SERVICES_GUIDE.md

### **Feature Documents** (build on foundation)
Implement specific features:
- LLM_SERVICES_GUIDE.md
- BUSINESS_TOOLS_GUIDE.md
- CUSTOM_PROCESSORS_GUIDE.md
- CUSTOMER_PROFILES.md

### **Integration Documents** (connect everything)
Tie features together:
- API_GUIDE.md
- SESSION_MANAGEMENT.md
- CONTEXT_ENRICHMENT.md
- guides/multi-step-workflows.md

### **Operations Documents** (maintain & debug)
Keep the system running:
- DEBUGGING_OBSERVABILITY.md
- DATABASE_COLLECTIONS_STRUCTURE.md
- MIGRATION_SUMMARY.md
- CLEANUP_SUMMARY.md

---

## 📞 Getting Help

### **Documentation Resources**
- **Architecture Questions** → [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) + [ADVANCED_PIPELINE_ARCHITECTURE.md](ADVANCED_PIPELINE_ARCHITECTURE.md)
- **Implementation Help** → [guides/](guides/) folder + relevant feature docs
- **API Reference** → [API_GUIDE.md](API_GUIDE.md)
- **Troubleshooting** → [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md) + [CLEANUP_SUMMARY.md](CLEANUP_SUMMARY.md) + [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md)
- **Source Code** → [../src](../src) directory

### **Related Resources**
- **Pipecat SDK Documentation**: https://github.com/pipecat-ai/pipecat
- **Project Architecture**: See [ARCHITECTURE_DETAILED.md](ARCHITECTURE_DETAILED.md) for workspace-level DDD principles
- **Main README**: See [../README.md](../README.md) for project overview

---

## 📊 Document Statistics

| Category | Count |
|----------|-------|
| **Core Architecture Docs** | 3 |
| **Configuration & Setup** | 3 |
| **AI & LLM Docs** | 3 |
| **Customer & Context Docs** | 3 |
| **Advanced Features** | 4 |
| **Operations & Support** | 4 |
| **Example Guides** | 3 |
| **Summary/Reference Docs** | 2 |
| **Total Documents** | 25 |

---

## 🔄 Documentation Version & Updates

**Last Updated**: January 2026
**Documentation Version**: 2.0
**Platform Version**: Current (based on Pipecat v0.0.94+)

### **What's New in v2.0**
- Comprehensive document hierarchy with clear categorization
- Role-based navigation paths
- Connection maps showing inter-document relationships
- Feature documentation matrix
- Enhanced search and reference guide
- Complete use-case documentation

---

## 📖 How to Use This Documentation

### **For First-Time Users**
1. Read [QUICK_START.md](QUICK_START.md) to set up locally
2. Read [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) to understand the system
3. Choose your role above and follow the recommended reading order

### **For Specific Features**
1. Use the "Common Use Cases" table above to find your task
2. Follow the documentation path provided
3. Use cross-references in each document to learn more

### **For Troubleshooting**
1. Check [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md) first
2. Review [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md) for known issues
3. Check [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md) for data schema issues

### **For System Design Questions**
1. Start with [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
2. Deep dive with [ADVANCED_PIPELINE_ARCHITECTURE.md](ADVANCED_PIPELINE_ARCHITECTURE.md)
3. Review [FILE_STRUCTURE.md](FILE_STRUCTURE.md) for code organization
4. Check [CUSTOM_PROCESSORS_GUIDE.md](CUSTOM_PROCESSORS_GUIDE.md) for extension points

---

## 🎯 Next Steps

**Choose your starting point:**
- 🚀 **New to the platform?** → Start with [QUICK_START.md](QUICK_START.md)
- 🏗️ **Want to understand architecture?** → Read [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
- 👨‍💻 **Ready to build?** → Choose your role path above
- 🔍 **Looking for something specific?** → Use the search tables above
- 📚 **Want comprehensive knowledge?** → Follow the recommended reading order for your role

**Happy coding! 🎉**

---

**Documentation Hub**: This README serves as the central navigation hub for all Pipecat-Service documentation. Each document is self-contained but referenced here for easy discovery and understanding of relationships.

# Documentation

This directory contains documentation for the Pipecat Service.

## DND v2

[Telephony DND v2](dnd_v2.md) - Structured Do Not Disturb implementation for telephony-only call blocking with assistant-configurable enforcement.

# Pipecat-Service Documentation

Welcome to the **Pipecat-Service** comprehensive documentation hub! This guide provides complete coverage of the voice AI platform built on the Pipecat SDK, spanning architecture, implementation, deployment, and advanced use cases.

---

## 📚 Documentation Overview

The documentation is organized into **logical sections** to help you find exactly what you need:

### 🚀 **Getting Started**
- **[QUICK_START.md](QUICK_START.md)** - Begin here! Get the platform running in minutes
- **[ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)** - High-level system design and component interactions
- **[ARCHITECTURE_DETAILED.md](ARCHITECTURE_DETAILED.md)** - Deep technical architecture details

### 🏗️ **Core Architecture & Design**
- **[ADVANCED_PIPELINE_ARCHITECTURE.md](ADVANCED_PIPELINE_ARCHITECTURE.md)** - Pipecat pipeline internals, frame flow, and processor chain
- **[FILE_STRUCTURE.md](FILE_STRUCTURE.md)** - Project directory layout and file organization
- **[DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md)** - MongoDB schemas and data models

### 🔧 **Configuration & Setup**
- **[DEPLOYMENT_CONFIGURATION.md](DEPLOYMENT_CONFIGURATION.md)** - Environment variables, Docker setup, and performance tuning
- **[AUTHENTICATION_AUTHORIZATION.md](AUTHENTICATION_AUTHORIZATION.md)** - Auth0 integration, JWT tokens, role-based access control
- **[OUTBOUND_CALL_TOKEN_FLOW.md](OUTBOUND_CALL_TOKEN_FLOW.md)** - Token management during outbound call initiation and assistant config retrieval

### 🤖 **Agent & LLM Configuration**
- **[CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md)** - AI-powered call summaries and automatic profile extraction
- **[LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md)** - OpenAI, Gemini integration, prompt engineering, tool registration
- **[STT_TTS_SERVICES_GUIDE.md](STT_TTS_SERVICES_GUIDE.md)** - Speech-to-Text and Text-to-Speech provider implementations

### 👥 **Customer & Context Management**
- **[CUSTOMER_PROFILES.md](CUSTOMER_PROFILES.md)** - Customer identity management and profile structure
- **[CUSTOMER_PROFILE_MANAGER_GUIDE.md](CUSTOMER_PROFILE_MANAGER_GUIDE.md)** - Profile manager utilities and operations
- **[CONTEXT_ENRICHMENT.md](CONTEXT_ENRICHMENT.md)** - CRM enrichment, language detection, dynamic context building

### 🛠️ **Advanced Topics**
- **[BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md)** - Building custom business tools and integrations
- **[CUSTOM_PROCESSORS_GUIDE.md](CUSTOM_PROCESSORS_GUIDE.md)** - Custom pipeline processors (AudioBuffer, Transcription, Classification, etc.)
- **[SESSION_MANAGEMENT.md](SESSION_MANAGEMENT.md)** - Call session lifecycle, state management, and tracking
- **[TELEPHONY_FLOWS.md](TELEPHONY_FLOWS.md)** - Plivo & Twilio WebSocket integration, call routing, and telephony patterns

### 📊 **Operations & Support**
- **[API_GUIDE.md](API_GUIDE.md)** - Complete REST API reference with all endpoints
- **[DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md)** - Logging, tracing, monitoring, performance metrics
- **[MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md)** - Migration guides and breaking changes
- **[CLEANUP_SUMMARY.md](CLEANUP_SUMMARY.md)** - Cleanup procedures and maintenance tasks

### 📖 **Guides & Examples**
- **[guides/multi-step-workflows.md](guides/multi-step-workflows.md)** - Multi-step API workflow examples
- **[guides/engaging-words-system.md](guides/engaging-words-system.md)** - Engaging words and conversational patterns
- **[guides/tool-usage-examples.md](guides/tool-usage-examples.md)** - Practical business tool usage examples

---

## 🎯 Quick Navigation by Role

### 👨‍💻 **Backend Developers** - Build & Integrate Features
**Recommended Reading Order:**

1. [QUICK_START.md](QUICK_START.md) - Set up your environment
2. [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) - Understand the system
3. [FILE_STRUCTURE.md](FILE_STRUCTURE.md) - Navigate the codebase
4. [ADVANCED_PIPELINE_ARCHITECTURE.md](ADVANCED_PIPELINE_ARCHITECTURE.md) - Learn how pipelines work
5. [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md) - Understand LLM integration
6. [BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md) - Create custom tools
7. [CUSTOM_PROCESSORS_GUIDE.md](CUSTOM_PROCESSORS_GUIDE.md) - Build custom processors
8. [SESSION_MANAGEMENT.md](SESSION_MANAGEMENT.md) - Manage call sessions
9. [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md) - Understand data models
10. [API_GUIDE.md](API_GUIDE.md) - Reference all endpoints
11. [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md) - Debug and trace issues

### 🔧 **DevOps/Infrastructure Engineers** - Deploy & Monitor
**Recommended Reading Order:**

1. [QUICK_START.md](QUICK_START.md) - Initial setup
2. [DEPLOYMENT_CONFIGURATION.md](DEPLOYMENT_CONFIGURATION.md) - Configure production environment
3. [AUTHENTICATION_AUTHORIZATION.md](AUTHENTICATION_AUTHORIZATION.md) - Set up Auth0 and security
4. [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md) - Database setup
5. [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md) - Monitoring and alerts
6. [STT_TTS_SERVICES_GUIDE.md](STT_TTS_SERVICES_GUIDE.md) - Configure speech services
7. [DEPLOYMENT_CONFIGURATION.md](DEPLOYMENT_CONFIGURATION.md) - Performance tuning

### 📊 **Integration Partners** - Integrate & Extend
**Recommended Reading Order:**

1. [QUICK_START.md](QUICK_START.md) - Overview
2. [API_GUIDE.md](API_GUIDE.md) - Learn all APIs
3. [BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md) - Understand tool integration
4. [CUSTOMER_PROFILES.md](CUSTOMER_PROFILES.md) - Manage customer data
5. [guides/multi-step-workflows.md](guides/multi-step-workflows.md) - Real-world workflow examples
6. [CONTEXT_ENRICHMENT.md](CONTEXT_ENRICHMENT.md) - Enrich customer context
7. [TELEPHONY_FLOWS.md](TELEPHONY_FLOWS.md) - Understand telephony integration

### 🤖 **AI/ML Specialists** - Optimize AI Behavior
**Recommended Reading Order:**

1. [CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md) - AI summaries & extraction
2. [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md) - LLM configuration & prompting
3. [CONTEXT_ENRICHMENT.md](CONTEXT_ENRICHMENT.md) - Language detection & context
4. [ADVANCED_PIPELINE_ARCHITECTURE.md](ADVANCED_PIPELINE_ARCHITECTURE.md) - Pipeline optimization
5. [STT_TTS_SERVICES_GUIDE.md](STT_TTS_SERVICES_GUIDE.md) - Speech service tuning
6. [CUSTOMER_PROFILES.md](CUSTOMER_PROFILES.md) - Profile-based personalization

---

## 🗂️ Complete Document Hierarchy

```
docs/
├── README.md (this file - start here!)
│
├── GETTING STARTED
├── QUICK_START.md
├── ARCHITECTURE_OVERVIEW.md
├── ARCHITECTURE_DETAILED.md
│
├── CORE DESIGN
├── ADVANCED_PIPELINE_ARCHITECTURE.md
├── FILE_STRUCTURE.md
├── DATABASE_COLLECTIONS_STRUCTURE.md
│
├── CONFIGURATION
├── DEPLOYMENT_CONFIGURATION.md
├── AUTHENTICATION_AUTHORIZATION.md
├── OUTBOUND_CALL_TOKEN_FLOW.md
│
├── AI & LLM
├── CONFIGURABLE_SUMMARIES.md
├── LLM_SERVICES_GUIDE.md
├── STT_TTS_SERVICES_GUIDE.md
│
├── CUSTOMER & CONTEXT
├── CUSTOMER_PROFILES.md
├── CUSTOMER_PROFILE_MANAGER_GUIDE.md
├── CONTEXT_ENRICHMENT.md
│
├── ADVANCED FEATURES
├── BUSINESS_TOOLS_GUIDE.md
├── CUSTOM_PROCESSORS_GUIDE.md
├── SESSION_MANAGEMENT.md
├── TELEPHONY_FLOWS.md
│
├── OPERATIONS
├── API_GUIDE.md
├── DEBUGGING_OBSERVABILITY.md
├── MIGRATION_SUMMARY.md
├── CLEANUP_SUMMARY.md
│
├── guides/
│   ├── multi-step-workflows.md
│   ├── engaging-words-system.md
│   └── tool-usage-examples.md
│
└── NEW_DOCUMENTATION_SUMMARY.md (summary of new docs added)
```

---

## 🔗 Documentation Connection Map

### **Startup & Setup Path**
```
QUICK_START.md
    ↓
DEPLOYMENT_CONFIGURATION.md
    ↓
AUTHENTICATION_AUTHORIZATION.md
    ↓
DATABASE_COLLECTIONS_STRUCTURE.md
    ↓
API_GUIDE.md (Test all endpoints)
```

### **Architecture Understanding Path**
```
ARCHITECTURE_OVERVIEW.md
    ↓
ADVANCED_PIPELINE_ARCHITECTURE.md
    ↓
CUSTOM_PROCESSORS_GUIDE.md
    ↓
FILE_STRUCTURE.md
```

### **LLM & AI Configuration Path**
```
LLM_SERVICES_GUIDE.md
    ↓
CONFIGURABLE_SUMMARIES.md
    ↓
CONTEXT_ENRICHMENT.md
    ↓
CUSTOMER_PROFILES.md
    ↓
CUSTOM_PROCESSORS_GUIDE.md (Custom processors)
```

### **Business Integration Path**
```
BUSINESS_TOOLS_GUIDE.md
    ↓
API_GUIDE.md (Business tools endpoints)
    ↓
guides/tool-usage-examples.md
    ↓
guides/multi-step-workflows.md
```

### **Voice & Speech Path**
```
STT_TTS_SERVICES_GUIDE.md
    ↓
DEPLOYMENT_CONFIGURATION.md (Provider setup)
    ↓
CONTEXT_ENRICHMENT.md (Language detection)
    ↓
CUSTOM_PROCESSORS_GUIDE.md (Audio processors)
```

### **Session & Call Management Path**
```
SESSION_MANAGEMENT.md
    ↓
TELEPHONY_FLOWS.md
    ↓
DATABASE_COLLECTIONS_STRUCTURE.md (Session schema)
    ↓
API_GUIDE.md (Session endpoints)
```

### **Monitoring & Troubleshooting Path**
```
DEBUGGING_OBSERVABILITY.md
    ↓
API_GUIDE.md (Debug endpoints)
    ↓
MIGRATION_SUMMARY.md (Known issues)
    ↓
CLEANUP_SUMMARY.md (Maintenance)
```

---

## 🚀 Common Use Cases & Recommended Docs

### **I want to...**

| Task | Documentation Path |
|------|-------------------|
| **Get the service running** | QUICK_START.md → DEPLOYMENT_CONFIGURATION.md |
| **Understand the architecture** | ARCHITECTURE_OVERVIEW.md → ADVANCED_PIPELINE_ARCHITECTURE.md → FILE_STRUCTURE.md |
| **Create a voice agent** | QUICK_START.md → LLM_SERVICES_GUIDE.md → guides/multi-step-workflows.md |
| **Build a business tool** | BUSINESS_TOOLS_GUIDE.md → API_GUIDE.md → guides/tool-usage-examples.md |
| **Integrate with Plivo/Twilio** | TELEPHONY_FLOWS.md → API_GUIDE.md → DEPLOYMENT_CONFIGURATION.md |
| **Enable AI summaries** | CONFIGURABLE_SUMMARIES.md → LLM_SERVICES_GUIDE.md → SESSION_MANAGEMENT.md |
| **Manage customer profiles** | CUSTOMER_PROFILES.md → API_GUIDE.md → CUSTOMER_PROFILE_MANAGER_GUIDE.md |
| **Build custom processors** | CUSTOM_PROCESSORS_GUIDE.md → ADVANCED_PIPELINE_ARCHITECTURE.md → API_GUIDE.md |
| **Configure speech services** | STT_TTS_SERVICES_GUIDE.md → DEPLOYMENT_CONFIGURATION.md |
| **Add context enrichment** | CONTEXT_ENRICHMENT.md → CUSTOMER_PROFILES.md → guides/multi-step-workflows.md |
| **Set up security** | AUTHENTICATION_AUTHORIZATION.md → DEPLOYMENT_CONFIGURATION.md |
| **Understand outbound call tokens** | OUTBOUND_CALL_TOKEN_FLOW.md → AUTHENTICATION_AUTHORIZATION.md |
| **Monitor & debug** | DEBUGGING_OBSERVABILITY.md → API_GUIDE.md |
| **Deploy to production** | DEPLOYMENT_CONFIGURATION.md → AUTHENTICATION_AUTHORIZATION.md → DEBUGGING_OBSERVABILITY.md |
| **Handle sessions** | SESSION_MANAGEMENT.md → API_GUIDE.md → DATABASE_COLLECTIONS_STRUCTURE.md |
| **Troubleshoot issues** | MIGRATION_SUMMARY.md → CLEANUP_SUMMARY.md → DEBUGGING_OBSERVABILITY.md |

---

## 📝 Core Concepts

### **Domain-Driven Design (DDD)**
The platform is built on DDD principles with 4 distinct layers:
- **API Layer** (`src/app/api`): Request/response handling, endpoint definitions
- **Application Layer** (`src/app/agents`): Orchestration, use case coordination
- **Domain Layer** (`src/app/tools`): Core business logic, independent rules
- **Infrastructure Layer** (`src/app/services`): External system integration

→ **Learn more**: [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)

### **Frame-Based Pipelines**
The Pipecat SDK uses a frame-based architecture for real-time processing:
- **Frames**: Atomic data units (Audio, Text, Control frames)
- **Pipeline**: Chain of processors that handle frames
- **Processors**: Transform or react to frames (STT, TTS, LLM, Custom)
- **Observers**: Monitor pipeline events and collect metrics

→ **Learn more**: [ADVANCED_PIPELINE_ARCHITECTURE.md](ADVANCED_PIPELINE_ARCHITECTURE.md)

### **Configuration-Driven Architecture**
Voice agents are configured via `AgentConfig` without code changes:
- Supports multiple LLMs (OpenAI, Gemini)
- Configurable STT/TTS providers
- Dynamic context building
- Flexible business tool integration

→ **Learn more**: [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md)

### **Multi-Tenant Isolation**
All data is scoped by `tenant_id`:
- Complete data isolation per tenant
- Role-based access control (RBAC)
- Built-in from the ground up

→ **Learn more**: [AUTHENTICATION_AUTHORIZATION.md](AUTHENTICATION_AUTHORIZATION.md)

### **Real-Time Voice Communication**
Telephony integration via WebSocket streams:
- Plivo & Twilio support
- Real-time audio streaming
- Session management and state tracking
- Call recording and logging

→ **Learn more**: [TELEPHONY_FLOWS.md](TELEPHONY_FLOWS.md)

### **AI-Powered Call Processing**
Advanced AI capabilities built-in:
- Automatic call summaries
- Profile extraction and enrichment
- Language detection and context
- Intent classification

→ **Learn more**: [CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md)

---

## 🔍 Search & Reference Guide

### **By Technical Concept**
- 🎙️ Audio Processing → [STT_TTS_SERVICES_GUIDE.md](STT_TTS_SERVICES_GUIDE.md), [CUSTOM_PROCESSORS_GUIDE.md](CUSTOM_PROCESSORS_GUIDE.md)
- 🤖 LLM Integration → [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md), [CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md)
- 📊 Database Schema → [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md)
- 🔐 Security & Auth → [AUTHENTICATION_AUTHORIZATION.md](AUTHENTICATION_AUTHORIZATION.md), [DEPLOYMENT_CONFIGURATION.md](DEPLOYMENT_CONFIGURATION.md)
- 📞 Telephony → [TELEPHONY_FLOWS.md](TELEPHONY_FLOWS.md), [API_GUIDE.md](API_GUIDE.md)
- 🛠️ Custom Code → [BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md), [CUSTOM_PROCESSORS_GUIDE.md](CUSTOM_PROCESSORS_GUIDE.md)
- 👤 Customer Data → [CUSTOMER_PROFILES.md](CUSTOMER_PROFILES.md), [CONTEXT_ENRICHMENT.md](CONTEXT_ENRICHMENT.md)
- ⚙️ Configuration → [DEPLOYMENT_CONFIGURATION.md](DEPLOYMENT_CONFIGURATION.md), [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md)
- 📈 Monitoring → [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md), [API_GUIDE.md](API_GUIDE.md)
- 🔄 Session Management → [SESSION_MANAGEMENT.md](SESSION_MANAGEMENT.md), [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md)

### **By Use Case**
- **Outbound Calling** → [TELEPHONY_FLOWS.md](TELEPHONY_FLOWS.md), [OUTBOUND_CALL_TOKEN_FLOW.md](OUTBOUND_CALL_TOKEN_FLOW.md), [API_GUIDE.md](API_GUIDE.md), [SESSION_MANAGEMENT.md](SESSION_MANAGEMENT.md)
- **Inbound IVR** → [CUSTOM_PROCESSORS_GUIDE.md](CUSTOM_PROCESSORS_GUIDE.md), [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md)
- **Call Recording** → [SESSION_MANAGEMENT.md](SESSION_MANAGEMENT.md), [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md)
- **Customer Enrichment** → [CUSTOMER_PROFILES.md](CUSTOMER_PROFILES.md), [CONTEXT_ENRICHMENT.md](CONTEXT_ENRICHMENT.md)
- **AI Summaries** → [CONFIGURABLE_SUMMARIES.md](CONFIGURABLE_SUMMARIES.md), [LLM_SERVICES_GUIDE.md](LLM_SERVICES_GUIDE.md)
- **Business Integration** → [BUSINESS_TOOLS_GUIDE.md](BUSINESS_TOOLS_GUIDE.md), [API_GUIDE.md](API_GUIDE.md)
- **Multi-Language Support** → [CONTEXT_ENRICHMENT.md](CONTEXT_ENRICHMENT.md), [STT_TTS_SERVICES_GUIDE.md](STT_TTS_SERVICES_GUIDE.md)
- **Error Handling** → [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md), [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md)

---

## 📋 Feature Documentation Matrix

| Feature | Core Docs | Reference | Configuration | Examples |
|---------|-----------|-----------|-----------------|----------|
| **Voice Agents** | QUICK_START.md | LLM_SERVICES_GUIDE.md | DEPLOYMENT_CONFIGURATION.md | guides/ |
| **LLM Integration** | LLM_SERVICES_GUIDE.md | API_GUIDE.md | LLM_SERVICES_GUIDE.md | guides/ |
| **Speech Services** | STT_TTS_SERVICES_GUIDE.md | API_GUIDE.md | DEPLOYMENT_CONFIGURATION.md | - |
| **Business Tools** | BUSINESS_TOOLS_GUIDE.md | API_GUIDE.md | LLM_SERVICES_GUIDE.md | guides/tool-usage-examples.md |
| **Custom Processors** | CUSTOM_PROCESSORS_GUIDE.md | ADVANCED_PIPELINE_ARCHITECTURE.md | - | CUSTOM_PROCESSORS_GUIDE.md |
| **Customer Profiles** | CUSTOMER_PROFILES.md | API_GUIDE.md | - | CUSTOMER_PROFILE_MANAGER_GUIDE.md |
| **AI Summaries** | CONFIGURABLE_SUMMARIES.md | API_GUIDE.md | LLM_SERVICES_GUIDE.md | - |
| **Context Enrichment** | CONTEXT_ENRICHMENT.md | - | DEPLOYMENT_CONFIGURATION.md | - |
| **Telephony** | TELEPHONY_FLOWS.md | API_GUIDE.md | DEPLOYMENT_CONFIGURATION.md | guides/multi-step-workflows.md |
| **Token Flow (Outbound)** | OUTBOUND_CALL_TOKEN_FLOW.md | AUTHENTICATION_AUTHORIZATION.md | DEPLOYMENT_CONFIGURATION.md | - |
| **Session Management** | SESSION_MANAGEMENT.md | API_GUIDE.md | DATABASE_COLLECTIONS_STRUCTURE.md | - |
| **Authentication** | AUTHENTICATION_AUTHORIZATION.md | API_GUIDE.md | DEPLOYMENT_CONFIGURATION.md | - |
| **Monitoring** | DEBUGGING_OBSERVABILITY.md | API_GUIDE.md | DEPLOYMENT_CONFIGURATION.md | - |

---

## 🔗 Document Dependencies

### **Foundation Documents** (read first)
These documents provide essential context:
- QUICK_START.md
- ARCHITECTURE_OVERVIEW.md
- FILE_STRUCTURE.md

### **Configuration Documents** (setup required)
Configure the system before using features:
- DEPLOYMENT_CONFIGURATION.md
- AUTHENTICATION_AUTHORIZATION.md
- STT_TTS_SERVICES_GUIDE.md

### **Feature Documents** (build on foundation)
Implement specific features:
- LLM_SERVICES_GUIDE.md
- BUSINESS_TOOLS_GUIDE.md
- CUSTOM_PROCESSORS_GUIDE.md
- CUSTOMER_PROFILES.md

### **Integration Documents** (connect everything)
Tie features together:
- API_GUIDE.md
- SESSION_MANAGEMENT.md
- CONTEXT_ENRICHMENT.md
- guides/multi-step-workflows.md

### **Operations Documents** (maintain & debug)
Keep the system running:
- DEBUGGING_OBSERVABILITY.md
- DATABASE_COLLECTIONS_STRUCTURE.md
- MIGRATION_SUMMARY.md
- CLEANUP_SUMMARY.md

---

## 📞 Getting Help

### **Documentation Resources**
- **Architecture Questions** → [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) + [ADVANCED_PIPELINE_ARCHITECTURE.md](ADVANCED_PIPELINE_ARCHITECTURE.md)
- **Implementation Help** → [guides/](guides/) folder + relevant feature docs
- **API Reference** → [API_GUIDE.md](API_GUIDE.md)
- **Troubleshooting** → [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md) + [CLEANUP_SUMMARY.md](CLEANUP_SUMMARY.md) + [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md)
- **Source Code** → [../src](../src) directory

### **Related Resources**
- **Pipecat SDK Documentation**: https://github.com/pipecat-ai/pipecat
- **Project Architecture**: See [ARCHITECTURE_DETAILED.md](ARCHITECTURE_DETAILED.md) for workspace-level DDD principles
- **Main README**: See [../README.md](../README.md) for project overview

---

## 📊 Document Statistics

| Category | Count |
|----------|-------|
| **Core Architecture Docs** | 3 |
| **Configuration & Setup** | 3 |
| **AI & LLM Docs** | 3 |
| **Customer & Context Docs** | 3 |
| **Advanced Features** | 4 |
| **Operations & Support** | 4 |
| **Example Guides** | 3 |
| **Summary/Reference Docs** | 2 |
| **Total Documents** | 25 |

---

## 🔄 Documentation Version & Updates

**Last Updated**: January 2026
**Documentation Version**: 2.0
**Platform Version**: Current (based on Pipecat v0.0.94+)

### **What's New in v2.0**
- Comprehensive document hierarchy with clear categorization
- Role-based navigation paths
- Connection maps showing inter-document relationships
- Feature documentation matrix
- Enhanced search and reference guide
- Complete use-case documentation

---

## 📖 How to Use This Documentation

### **For First-Time Users**
1. Read [QUICK_START.md](QUICK_START.md) to set up locally
2. Read [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) to understand the system
3. Choose your role above and follow the recommended reading order

### **For Specific Features**
1. Use the "Common Use Cases" table above to find your task
2. Follow the documentation path provided
3. Use cross-references in each document to learn more

### **For Troubleshooting**
1. Check [DEBUGGING_OBSERVABILITY.md](DEBUGGING_OBSERVABILITY.md) first
2. Review [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md) for known issues
3. Check [DATABASE_COLLECTIONS_STRUCTURE.md](DATABASE_COLLECTIONS_STRUCTURE.md) for data schema issues

### **For System Design Questions**
1. Start with [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
2. Deep dive with [ADVANCED_PIPELINE_ARCHITECTURE.md](ADVANCED_PIPELINE_ARCHITECTURE.md)
3. Review [FILE_STRUCTURE.md](FILE_STRUCTURE.md) for code organization
4. Check [CUSTOM_PROCESSORS_GUIDE.md](CUSTOM_PROCESSORS_GUIDE.md) for extension points

---

## 🎯 Next Steps

**Choose your starting point:**
- 🚀 **New to the platform?** → Start with [QUICK_START.md](QUICK_START.md)
- 🏗️ **Want to understand architecture?** → Read [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
- 👨‍💻 **Ready to build?** → Choose your role path above
- 🔍 **Looking for something specific?** → Use the search tables above
- 📚 **Want comprehensive knowledge?** → Follow the recommended reading order for your role

**Happy coding! 🎉**

---

**Documentation Hub**: This README serves as the central navigation hub for all Pipecat-Service documentation. Each document is self-contained but referenced here for easy discovery and understanding of relationships.
