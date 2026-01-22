# PR #117 Functional Test Evidence

**Date**: 2026-01-22
**Test Type**: Facet Extraction Service
**PR**: #117 - Pipeline step: facet extraction for conversations

## Test Results

### Single Extraction Tests

| Conv ID | Text Summary | action_type | direction | success |
|---------|--------------|-------------|-----------|---------|
| test_001 | Duplicate notifications | bug_report | **excess** | ✅ |
| test_002 | Pins not showing | bug_report | **deficit** | ✅ |
| test_003 | Dark mode request | feature_request | creation | ✅ |
| test_004 | Delete account | delete_request | deletion | ✅ |

### Batch Processing Test

- Total processed: 4
- Total success: 4
- Total failed: 0

### Direction Differentiation (T-006 Critical Requirement)

The facet extraction correctly distinguishes semantically similar but directionally opposite issues:

- **Duplicate pins** (test_001): `direction=excess`
- **Missing pins** (test_002): `direction=deficit`

✅ **SUCCESS**: Direction facet correctly differentiates opposite issues!

### Sample Output

```
Conversation: test_001
Text: I keep getting duplicate notifications for the same pin...
Result:
  action_type: bug_report
  direction: excess
  symptom: duplicate notifications for the same pin
  user_goal: stop receiving duplicate notifications
  success: True

Conversation: test_002
Text: My pins are not showing up in the app...
Result:
  action_type: bug_report
  direction: deficit
  symptom: pins not showing up in the app
  user_goal: view added pins on the map
  success: True
```

## Security Validations

- ✅ PII protection: Conversation IDs hashed in logs
- ✅ Prompt injection defense: Defensive framing in prompt
- ✅ Character limits: Fields truncated to 200 chars

## Conclusion

Functional test **PASSED**. The facet extraction service is working correctly and ready for merge.
