---
name: json-config-driven-form
description: "JSON config file pattern for form fields with validation rules, aria attributes, and options — always generate this for any page with form inputs"
tags: ["form", "config", "json", "validation", "input", "field", "ng-model", "ng-form"]
trigger: form_fields
---

# JSON Config-Driven Form — Golden Pattern

## When to Apply
**ALWAYS** when the legacy code contains `ng-model`, `ng-form`, `<input`, or form field bindings.
Every page with inputs MUST have a matching `config/<pageName>.json`.

## Why This Pattern Exists
- Separates field metadata (labels, placeholders, aria, validation rules) from component logic
- Makes field changes configuration, not code changes
- Keeps the page component clean — it only orchestrates, never defines field metadata

## Exact Golden Pattern (config file)

```json
// filepath: src/config/login.json
{
  "email": {
    "id": "email",
    "type": "email",
    "name": "email",
    "placeholder": "Enter your email",
    "label": "Email Address",
    "value": "",
    "isRequired": true,
    "hasError": false,
    "errorMessage": "",
    "validationRules": {
      "required": {
        "value": true,
        "errorMessage": "Email Address is required."
      },
      "pattern": {
        "value": "EMAIL",
        "errorMessage": "Please enter a valid email address."
      }
    },
    "aria-label": "Email Address",
    "aria-describedby": "emailHelp",
    "tooltip": "We'll never share your email with anyone else."
  },
  "password": {
    "id": "password",
    "type": "password",
    "name": "password",
    "placeholder": "Enter your password",
    "label": "Password",
    "value": "",
    "isRequired": true,
    "hasError": false,
    "errorMessage": "",
    "validationRules": {
      "required": {
        "value": true,
        "errorMessage": "Password is required."
      },
      "minLength": {
        "value": 6,
        "errorMessage": "Password must be at least 6 characters long."
      }
    },
    "aria-label": "Password",
    "aria-describedby": "passwordHelp",
    "tooltip": "Choose a strong password to keep your account secure."
  },
  "city": {
    "id": "city",
    "type": "select",
    "name": "city",
    "placeholder": "Select your city",
    "label": "City",
    "value": "",
    "isRequired": true,
    "hasError": false,
    "errorMessage": "",
    "validationRules": {
      "required": {
        "value": true,
        "errorMessage": "City selection is required."
      }
    },
    "aria-label": "City",
    "aria-describedby": "cityHelp",
    "tooltip": "Optional: Select your city for a more personalized experience.",
    "options": [
      { "value": "", "label": "Select your city" },
      { "value": "new_york", "label": "New York" }
    ]
  }
}
```

## Validation Rule Keys Supported
| Key | Usage |
|-----|-------|
| `required` | `{ "value": true, "errorMessage": "..." }` |
| `pattern` | `{ "value": "EMAIL" \| "PHONE" \| "ZIP", "errorMessage": "..." }` |
| `minLength` | `{ "value": 6, "errorMessage": "..." }` |
| `maxLength` | `{ "value": 100, "errorMessage": "..." }` |
| `min` | `{ "value": 0, "errorMessage": "..." }` (numeric) |
| `max` | `{ "value": 999, "errorMessage": "..." }` (numeric) |

## Mandatory Field Properties
Every field object MUST have:
`id`, `type`, `name`, `placeholder`, `label`, `value`, `isRequired`, `hasError`, `errorMessage`, `validationRules`, `aria-label`

## For Select Fields — MUST include `options` array
Each option: `{ "value": "key", "label": "Display Label" }`
First option always: `{ "value": "", "label": "Select <fieldLabel>" }`
