# Complete Database-Based Tools System

This example demonstrates how to use the full CRUD tools system that matches the `lib_c/ref_src` implementation.

## 1. Create Tools via API

### Create a CRM API Tool

```bash
curl -X POST "https://your-api.com/api/tools" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CRM Customer Lookup",
    "description": "Look up customer information from our CRM system",
    "type": "custom_api",
    "config": {
      "type": "custom_api",
      "config": {
        "enabled": true,
        "config": {
          "base_url": "https://api.crm.example.com/customers",
          "method": "GET",
          "headers": {
            "Accept": "application/json"
          },
          "timeout_seconds": 30,
          "authentication": {
            "type": "bearer",
            "token": "your-crm-api-token"
          },
          "query": {
            "fields": [
              {
                "key": "customer_id",
                "description": "The customer ID to look up",
                "field_type": "integer",
                "required": true,
                "examples": ["12345", "67890"]
              },
              {
                "key": "include_history",
                "description": "Whether to include purchase history",
                "field_type": "boolean",
                "required": false,
                "examples": ["true", "false"]
              }
            ]
          }
        }
      }
    }
  }'
```

Response:
```json
"tool-uuid-12345"
```

### Create a Webhook Tool

```bash
curl -X POST "https://your-api.com/api/tools" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Order Processing Webhook",
    "description": "Process new orders through our webhook system",
    "type": "custom_api",
    "config": {
      "type": "custom_api",
      "config": {
        "enabled": true,
        "config": {
          "base_url": "https://api.orders.example.com/webhook",
          "method": "POST",
          "headers": {
            "Content-Type": "application/json"
          },
          "timeout_seconds": 45,
          "authentication": {
            "type": "api_key",
            "api_key": "your-webhook-key",
            "header_name": "X-API-Key"
          },
          "body": {
            "fields": [
              {
                "key": "order_id",
                "description": "The order ID to process",
                "field_type": "string",
                "required": true,
                "examples": ["ORD-123", "ORD-456"]
              },
              {
                "key": "priority",
                "description": "Processing priority (1-5)",
                "field_type": "integer",
                "required": false,
                "examples": ["1", "3", "5"]
              },
              {
                "key": "customer_notes",
                "description": "Additional notes about the customer",
                "field_type": "string",
                "required": false,
                "examples": ["VIP customer", "Rush delivery"]
              }
            ]
          }
        }
      }
    }
  }'
```

Response:
```json
"tool-uuid-67890"
```

## 2. List Available Tools

```bash
curl -X GET "https://your-api.com/api/tools?page=1&limit=10" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Response:
```json
{
  "total_items": 2,
  "total_pages": 1,
  "current_page": 1,
  "data": [
    {
      "_id": "tool-uuid-12345",
      "name": "CRM Customer Lookup",
      "description": "Look up customer information from our CRM system",
      "type": "custom_api",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    },
    {
      "_id": "tool-uuid-67890",
      "name": "Order Processing Webhook",
      "description": "Process new orders through our webhook system",
      "type": "custom_api",
      "created_at": "2024-01-15T10:35:00Z",
      "updated_at": "2024-01-15T10:35:00Z"
    }
  ]
}
```

## 3. Test a Tool

```bash
curl -X POST "https://your-api.com/api/tools/tool-uuid-12345/test" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query_params": {
      "customer_id": 12345,
      "include_history": true
    },
    "engaging_words": "Let me check your customer information..."
  }'
```

Response:
```json
{
  "success": true,
  "status_code": 200,
  "response_data": {
    "customer_id": 12345,
    "name": "John Doe",
    "email": "john@example.com",
    "status": "premium",
    "purchase_history": [
      {"order_id": "ORD-123", "amount": 250.00, "date": "2024-01-10"}
    ]
  },
  "execution_time_ms": 342.5
}
```

## 4. Use Tools in Agent Configuration

### Database-Based Tool References (Recommended)

```json
{
  "name": "Customer Service Assistant",
  "llm": {
    "provider": "openai",
    "model": "gpt-4o",
    "system_prompt_template": "You are a helpful customer service assistant with access to our CRM and order processing systems. Use the available tools to help customers with their inquiries."
  },
  "tools": {
    "custom_tools": [
      {
        "tool_id": "tool-uuid-12345",
        "enabled": true
      },
      {
        "tool_id": "tool-uuid-67890",
        "enabled": true
      }
    ]
  }
}
```

### Legacy Inline Configuration (Still Supported)

```json
{
  "name": "Customer Service Assistant",
  "llm": {
    "provider": "gemini",
    "model": "gemini-2.0-flash-live-001",
    "system_prompt_template": "You are a helpful customer service assistant."
  },
  "tools": {
    "custom_api": {
      "crm_lookup": {
        "enabled": true,
        "config": {
          "base_url": "https://api.crm.example.com/customers",
          "method": "GET",
          "authentication": {
            "type": "bearer",
            "token": "your-token"
          },
          "query": {
            "fields": [
              {
                "key": "customer_id",
                "description": "Customer ID to lookup",
                "field_type": "integer",
                "required": true
              }
            ]
          }
        }
      }
    }
  }
}
```

## 5. How LLMs Use the Tools

When an LLM wants to use a database tool, it will call functions like:

```javascript
// For the CRM tool
call_crm_customer_lookup({
  "engaging_words": "Let me look up your account information...",
  "query_params": {
    "customer_id": 12345,
    "include_history": true
  }
})

// For the webhook tool  
call_order_processing_webhook({
  "engaging_words": "I'm processing your order now...",
  "body_data": {
    "order_id": "ORD-123",
    "priority": 1,
    "customer_notes": "VIP customer - rush processing"
  }
})
```

## 6. Tool Management Operations

### Update a Tool

```bash
curl -X PUT "https://your-api.com/api/tools/tool-uuid-12345" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Updated: Look up customer information with enhanced features"
  }'
```

### Delete a Tool

```bash
curl -X DELETE "https://your-api.com/api/tools/tool-uuid-12345" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Validate Tool IDs

```bash
curl -X POST "https://your-api.com/api/tools/validate-ids" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '["tool-uuid-12345", "invalid-tool-id", "tool-uuid-67890"]'
```

Response:
```json
{
  "valid_ids": ["tool-uuid-12345", "tool-uuid-67890"],
  "invalid_ids": ["invalid-tool-id"],
  "total_requested": 3,
  "valid_count": 2,
  "invalid_count": 1
}
```

## 7. Benefits of Database-Based Tools

### ✅ **Advantages:**
- **Reusable**: Tools can be shared across multiple agents
- **Centrally Managed**: Update once, affects all agents using the tool
- **Secure**: Credentials stored securely in database
- **Testable**: Built-in testing endpoint for each tool
- **Auditable**: Full CRUD history with user tracking
- **Dynamic**: Add/remove tools without code changes
- **Scalable**: Handle hundreds of different API integrations

### 🔧 **Perfect For:**
- **Multi-tenant SaaS**: Each tenant can have their own tools
- **Enterprise Integration**: Connect to various internal APIs
- **Customer-specific APIs**: Different customers, different integrations
- **Rapid Prototyping**: Quickly add new API capabilities
- **External Partner APIs**: Easily integrate third-party services

This implementation provides the complete enterprise-grade tools management system from the reference implementation!
