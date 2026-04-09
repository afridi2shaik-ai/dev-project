# Engaging Words System

## Overview

The **Engaging Words System** is a centralized configuration and utility framework that provides consistent, action-oriented phrases for user feedback during API operations. It ensures all custom API tools and database integrations deliver professional, contextual responses that enhance user experience.

## Core Philosophy

Instead of generic phrases like "assistant details" or "loading data", the system generates action-oriented, engaging phrases such as:
- "Fetching your assistant information..."
- "Retrieving system data..."
- "Searching the database..."

## Architecture

### Location
- **Primary Module**: `src/app/tools/engaging_words_config.py`
- **Architecture Layer**: Domain Layer (pure business logic)
- **Dependencies**: None (fully independent to avoid circular imports)

### Core Components

#### 1. Configuration (`ENGAGING_WORDS_PARAM_CONFIG`)
```python
ENGAGING_WORDS_PARAM_CONFIG = {
    "name": "engaging_words",
    "type": "string",
    "required": True,
    "description": "REQUIRED: Brief phrase describing the ACTION being performed...",
    "examples": [
        "Fetching your assistant information...",
        "Retrieving system data...",
        # ... 8 total examples
    ]
}
```

#### 2. Utility Functions (11 Total)

| Function | Purpose | Example Usage |
|----------|---------|---------------|
| `get_engaging_words_schema()` | JSON schema for API parameters | API documentation generation |
| `get_engaging_words_docstring()` | Function parameter documentation | Tool function docstrings |
| `validate_engaging_words()` | Basic validation | Input validation |
| `get_default_engaging_words()` | Default testing phrase | Unit tests, fallbacks |
| `get_random_engaging_words()` | Random phrase selection | Dynamic variation |
| `get_contextual_engaging_words()` | Context-specific phrases | Smart context awareness |
| `create_custom_engaging_words()` | Dynamic phrase generation | Custom action descriptions |
| `is_valid_engaging_words_format()` | Advanced format validation | Quality assurance |
| `get_all_examples()` | Complete examples list | Documentation, UI dropdowns |
| `get_parameter_info()` | Complete metadata | API introspection |

#### 3. Contextual Support

The system supports 8 predefined contexts with appropriate phrases:

```python
contexts = {
    "assistant": "Fetching your assistant information...",
    "data": "Retrieving system data...",
    "config": "Looking up configurations...",
    "database": "Searching the database...",
    "api": "Getting details from the API...",
    "general": "Processing your request...",
    "update": "Updating the records...",
    "save": "Saving the information..."
}
```

## Usage Patterns

### 1. Basic Context-Based Usage
```python
from app.tools.engaging_words_config import get_contextual_engaging_words

# Get appropriate phrase for assistant operations
engaging_words = get_contextual_engaging_words("assistant")
# → "Fetching your assistant information..."

# Get appropriate phrase for database operations  
engaging_words = get_contextual_engaging_words("database")
# → "Searching the database..."
```

### 2. Custom Dynamic Generation
```python
from app.tools.engaging_words_config import create_custom_engaging_words

# Generate custom phrase
custom_phrase = create_custom_engaging_words("retrieving", "user settings")
# → "Retrieving user settings..."

custom_phrase = create_custom_engaging_words("updating", "profile information")
# → "Updating profile information..."
```

### 3. Validation and Quality Control
```python
from app.tools.engaging_words_config import is_valid_engaging_words_format

# Validate format
is_valid = is_valid_engaging_words_format("Fetching your data...")  # True
is_invalid = is_valid_engaging_words_format("data loading")  # False (no ellipsis)
```

### 4. API Integration
```python
from app.tools.engaging_words_config import get_engaging_words_schema

# Get JSON schema for API documentation
schema = get_engaging_words_schema()
# → {"type": "string", "description": "REQUIRED: Brief phrase..."}
```

## Integration Points

### 1. API Tools Router (`src/app/api/tools_api.py`)
- **TestToolRequest**: Uses contextual engaging words via `default_factory`
- **New Endpoint**: `GET /api/tools/engaging-words` provides configuration info

### 2. Tool Registration Service (`src/app/services/tool_registration_service.py`)
- **Consistent Docstrings**: Uses centralized docstring generation
- **Standardized Descriptions**: All tool functions have consistent parameter docs

### 3. Custom API Tool (`src/app/tools/custom_api_tool.py`)
- **Enhanced Descriptions**: Better parameter documentation
- **Professional Quality**: Improved user-facing descriptions

## Quality Standards

### Format Requirements
1. **Action-Oriented**: Must use present progressive verbs (ending in -ing)
2. **Professional**: Clear, concise, business-appropriate language
3. **Consistent**: Always end with ellipsis ("...")
4. **Contextual**: Appropriate for the specific operation type
5. **Length**: Between 10-100 characters (excluding ellipsis)

### Validation Rules
```python
def is_valid_engaging_words_format(engaging_words: str) -> bool:
    # 1. Not empty
    if not engaging_words or not engaging_words.strip():
        return False
        
    # 2. Ends with ellipsis
    if not words.endswith("..."):
        return False
        
    # 3. Minimum length (excluding ellipsis)
    if len(words.replace("...", "")) < 10:
        return False
        
    # 4. Contains action indicators
    action_indicators = ["fetching", "retrieving", "getting", "looking", 
                        "searching", "processing", "updating", "saving", 
                        "loading", "checking"]
    return any(indicator in words.lower() for indicator in action_indicators)
```

## API Endpoints

### GET /api/tools/engaging-words
Returns comprehensive engaging words configuration and examples.

**Response**:
```json
{
  "parameter_info": {
    "name": "engaging_words",
    "type": "string",
    "required": true,
    "description": "REQUIRED: Brief phrase describing...",
    "examples": ["Fetching your assistant information...", ...]
  },
  "standard_examples": [...],
  "contextual_examples": {
    "assistant": "Fetching your assistant information...",
    "database": "Searching the database...",
    ...
  },
  "usage_tips": [
    "Always use action-oriented phrases",
    "End with ellipsis (...)",
    "Keep it brief and engaging",
    ...
  ]
}
```

## Best Practices

### For Developers

1. **Always Use Contextual Generation**:
   ```python
   # Good
   engaging_words = get_contextual_engaging_words("database")
   
   # Avoid
   engaging_words = "Loading data..."
   ```

2. **Validate Input When Necessary**:
   ```python
   if not is_valid_engaging_words_format(user_input):
       engaging_words = get_default_engaging_words()
   ```

3. **Use Custom Generation for Specific Actions**:
   ```python
   # For specific, known actions
   engaging_words = create_custom_engaging_words("synchronizing", "customer data")
   ```

### For API Tool Creation

1. **Use Context-Appropriate Phrases**:
   - Customer operations: `get_contextual_engaging_words("database")`
   - Configuration: `get_contextual_engaging_words("config")`
   - General API calls: `get_contextual_engaging_words("api")`

2. **Provide Clear Descriptions**:
   ```python
   # In tool parameter description
   engaging_words: str = Field(
       default_factory=lambda: get_contextual_engaging_words("api"),
       description="Action-oriented phrase to speak while processing..."
   )
   ```

## Testing

### Unit Tests
```python
def test_engaging_words_system():
    # Test contextual generation
    assert get_contextual_engaging_words("assistant") == "Fetching your assistant information..."
    
    # Test custom generation
    assert create_custom_engaging_words("fetching", "user data") == "Fetching user data..."
    
    # Test validation
    assert is_valid_engaging_words_format("Processing your request...") == True
    assert is_valid_engaging_words_format("loading") == False
```

### Integration Tests
- Verify API endpoint returns correct structure
- Test tool registration uses centralized configuration
- Validate consistent docstring generation

## Benefits

### User Experience
- **Consistency**: All operations use professional, action-oriented language
- **Clarity**: Users understand what the system is doing
- **Engagement**: Active language keeps users informed and engaged

### Developer Experience
- **Centralized**: Single source of truth for all engaging words logic
- **Reusable**: 11 utility functions for different use cases  
- **Documented**: Comprehensive examples and usage guidance
- **Independent**: No circular dependencies or configuration issues

### Code Quality
- **Standardized**: Eliminates ad-hoc phrase generation
- **Validated**: Built-in quality checks ensure consistent format
- **Maintainable**: Changes to engaging words logic happen in one place
- **Testable**: Well-defined functions with clear inputs/outputs

## Future Enhancements

1. **Internationalization**: Support for multiple languages
2. **A/B Testing**: Framework for testing different phrase effectiveness
3. **Analytics**: Track which phrases users respond to best
4. **AI Generation**: Use LLM to generate contextual phrases dynamically
5. **Voice Optimization**: Phrases optimized for TTS pronunciation

## Migration Guide

### Existing Code
If you have existing hardcoded engaging words:

```python
# Before
engaging_words = "Loading data..."

# After
from app.tools.engaging_words_config import get_contextual_engaging_words
engaging_words = get_contextual_engaging_words("database")
```

### Custom Tool Development
When creating new custom API tools:

```python
from app.tools.engaging_words_config import get_engaging_words_schema

# Include in function parameters
async def my_custom_tool(
    params,
    engaging_words: str = Field(..., **get_engaging_words_schema()),
    # ... other parameters
):
    # Use engaging_words in your tool logic
    await params.llm.push_frame(TTSSpeakFrame(engaging_words))
```

## Support

For questions about the engaging words system:
1. Check this documentation
2. Review examples in `src/app/tools/engaging_words_config.py`
3. Test with the `/api/tools/engaging-words` endpoint
4. Examine existing integrations in the codebase
