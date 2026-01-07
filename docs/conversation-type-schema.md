# Conversation Type Schema

Based on LLM-as-judge analysis of 75 closed conversations (90 days, all sources).

**Generated:** 2026-01-07
**Data source:** `data/conversation_types/conversation_types_20260107_134344.csv`

---

## Conversation Type Categories

### 1. **Product Issue**

_Customer reports something broken or not working as expected_

**Subcategories:**

- `bug_report` - Feature broken, error message, unexpected behavior
- `feature_not_working` - Feature exists but not functioning for customer
- `data_issue` - Content not showing, posts missing, incorrect data

**Distinguishing signals:**

- "not working", "broken", "error", "can't", "won't", "doesn't"
- Error messages or screenshots
- Reproducible steps

**Examples from data:** (Not found in sample - need more product-focused conversations)

---

### 2. **How-To Question**

_Customer needs guidance on using existing features_

**Distribution:** 25% of sample (19/75 conversations)
**Confidence:** 95% high confidence

**Subcategories:**

- `feature_usage` - How do I do X?
- `workflow_help` - How do I accomplish Y task?
- `feature_discovery` - Where is feature Z?

**Distinguishing signals:**

- "how do I", "how to", "can I", "is it possible"
- "don't see option", "where is", "can't find"
- "not sure how it works", "haven't had time to read tutorials"

**Examples from data:**

- "I'm not sure how it works, haven't had time to read tutorials" (18329574377)
- "don't see option to share to Instagram" (18356016454)
- "I'm not seeing an option to schedule & share to my Instagram" (18379846791)

**Vocabulary needs:**

- Themes for common how-to questions per product area
- Onboarding/setup themes

---

### 3. **Feature Request**

_Customer wants new capability or enhancement_

**Distribution:** 1% of sample (1/75 conversations)
**Confidence:** 100% high confidence

**Subcategories:**

- `new_feature` - Request for entirely new capability
- `enhancement` - Improvement to existing feature
- `integration_request` - Connect to new platform/service

**Distinguishing signals:**

- "I want to", "I wish", "it would be great if"
- "add support for", "integrate with"
- "important feature I want"

**Examples from data:**

- "I'm not seeing option to schedule to Instagram... that's the most important one" (18379846791)

**Vocabulary needs:**

- Feature request themes by product area
- Integration request themes (new platforms)

---

### 4. **Account Issue**

_Customer cannot access account or having auth/permission problems_

**Distribution:** 20% of sample (15/75 conversations)
**Confidence:** 100% high confidence
**Source type:** 93% from email (14/15)

**Subcategories:**

- `login_issue` - Can't sign in, forgot password
- `access_denied` - Permission errors, locked out
- `connection_issue` - Social account disconnected, OAuth problems
- `username_change` - Update email, change username

**Distinguishing signals:**

- "can't login", "can't access", "locked out"
- "forgot password", "reset password"
- "disconnected", "re-authorize", "reconnect"

**Examples from data:**

- 14 consecutive account_issues (215472566640974-215472566825006) - likely batch issue
- "username_change_request" (215472550428980)

**Vocabulary needs:**

- Account themes (login, OAuth, permissions)
- Connection/authorization themes

---

### 5. **Billing Question**

_Customer has question about payment, plan, invoice, or subscription_

**Distribution:** 7% of sample (5/75 conversations)
**Confidence:** 100% high confidence

**Subcategories:**

- `payment_issue` - Card declined, update payment method
- `plan_question` - Which plan should I choose, plan features
- `invoice_request` - Need receipt, invoice not received
- `subscription_change` - Upgrade, downgrade, cancel
- `refund_request` - Request refund or credit

**Distinguishing signals:**

- "payment", "billing", "invoice", "receipt"
- "plan", "subscription", "cancel", "upgrade"
- "refund", "credit", "charge"

**Examples from data:**

- "money" + billing URL (760509807645)
- "update payment information" subject (215472569243952)
- "Plan Selection/Refund" subject (215472549698140)
- "Subscription cancellation" (215472529416559)

**Vocabulary needs:**

- ✅ **CRITICAL**: No billing themes in current vocabulary
- Payment method themes
- Plan/subscription themes
- Invoice/receipt themes

---

### 6. **Configuration Help**

_Customer needs help with settings, setup, or integration configuration_

**Distribution:** 1% of sample (1/75 conversations)
**Confidence:** 100% high confidence

**Subcategories:**

- `initial_setup` - Onboarding, first-time configuration
- `integration_setup` - Connect social account, API setup
- `settings_question` - How to change settings

**Distinguishing signals:**

- "setup", "configure", "integrate", "connect"
- "add account", "link", "authorize"
- First message in conversation (new user)

**Examples from data:**

- "I noticed since I added Pinterest, I don't see Instagram option" (18356016454)

**Vocabulary needs:**

- Onboarding themes
- Integration setup themes per platform

---

### 7. **General Inquiry**

_Broad question or unclear intent - may need clarification_

**Distribution:** 37% of sample (28/75 conversations)
**⚠️ WARNING:** High rate of auto-responses and spam in this category

**Subcategories:**

- `unclear_intent` - Customer message is vague
- `multiple_topics` - Covers several unrelated questions
- `exploratory` - Browsing, not specific ask

**Distinguishing signals:**

- Very short messages with no specifics
- Auto-responses: "Thanks, I'll see if I have answer for that"
- No clear ask or problem statement

**Examples from data:**

- Most are "Thanks, I'll see if I have answer..." auto-response
- "thank you :)" (18355364780)

**Note:** This category needs refinement. Many may be:

- Bot auto-responses (not real customer inquiries)
- Spam/marketing emails masquerading as support
- Follow-up acknowledgments (not new conversations)

---

### 8. **Spam / Not Support** 🗑️

_Should be filtered out - not legitimate support conversation_

**Distribution:** ~4% of sample (3/75 conversations)

**Subcategories:**

- `marketing_email` - Promotional content, newsletters
- `guest_post_spam` - SEO link building requests
- `event_invitation` - Webinar invites, events
- `sales_outreach` - Vendor solicitations

**Distinguishing signals:**

- Generic recipient ("Hi", no personalization)
- External URLs, promotional language
- "guest post", "link building", "SEO services"
- Subject lines about events, promotions

**Examples from data:**

- "Guest Post Opportunities on High-Authority Websites" (215472582742545)
- "Snuggle Up: Valentine's Day Collection!" (215472582069907)
- "event_invitation" (215472579309392)

**Action:** Should be filtered at source, not classified

---

## Distribution Summary

| Type               | Count | %     | High Confidence |
| ------------------ | ----- | ----- | --------------- |
| General Inquiry    | 28    | 37.3% | 64%             |
| How-To Question    | 19    | 25.3% | 95%             |
| Account Issue      | 15    | 20.0% | 100%            |
| Billing Question   | 5     | 6.7%  | 100%            |
| Spam/Marketing     | 3     | 4.0%  | 100%            |
| Configuration Help | 1     | 1.3%  | 100%            |
| Feature Request    | 1     | 1.3%  | 100%            |
| Product Issue      | 0     | 0%    | -               |

**Notes:**

- No bug reports or product issues in sample (may indicate filtering bias)
- High "general inquiry" rate suggests need for better conversation quality filtering
- Account issues clustered (14 consecutive) - may be incident-related

---

## Source Type Patterns

### In-App Conversation (`conversation`)

- 56% of sample (42/75)
- Has `source.url` with product context
- **Primary types:** How-to (45%), General (50%)
- Users are actively in product, asking questions

### Email

- 44% of sample (33/75)
- No `source.url` context
- **Primary types:** Account issues (42%), Billing (12%), Spam (9%)
- More structural issues (can't get into product)

---

## Recommendations

### 1. Consolidate Schema

Reduce from 13 LLM-generated types to **7 core types**:

1. Product Issue (bug_report, feature_not_working, data_issue)
2. How-To Question
3. Feature Request
4. Account Issue (login, access, connections)
5. Billing Question (payment, plan, invoice, subscription)
6. Configuration Help (setup, integration, settings)
7. General Inquiry (unclear, exploratory)

Plus filter category: 8. Spam / Not Support (exclude from analysis)

### 2. Improve Quality Filtering

- Auto-response detection: Flag "Thanks, I'll see if I have answer" pattern
- Spam detection: Filter guest posts, marketing emails
- Acknowledgment detection: "thank you :)" isn't a new inquiry

### 3. Vocabulary Expansion Priorities

**HIGH PRIORITY:**

1. **Billing themes** - Currently missing, 7% of conversations
   - Payment methods (card declined, update payment)
   - Plan questions (which plan, plan features)
   - Subscription changes (cancel, upgrade, downgrade)
   - Invoice/receipt requests
   - Refund requests

2. **Account/Auth themes** - 20% of conversations
   - Login issues
   - Password reset
   - OAuth/connection problems
   - Account permissions

**MEDIUM PRIORITY:** 3. **Onboarding/Setup themes**

- Initial configuration
- Integration setup per platform
- First-time user questions

4. **How-to themes per product area**
   - Expand existing product themes with common how-to variants

**LOW PRIORITY:** 5. **Feature request tracking** - Only 1% but valuable signal

- Integration requests (new platforms)
- Enhancement requests by product area

### 4. URL Pattern Expansion

Current: 27 patterns for product pages
**Needed:** Settings, billing, account pages

- `/settings/billing` → Billing & Settings
- `/settings/account` → Account
- `/settings/upgrade` → Billing & Settings
- `/dashboard/v2/home` → Home/Dashboard (generic)

---

## Next Steps

1. ✅ Define conversation type schema (this doc)
2. ⬜ Add billing themes to vocabulary
3. ⬜ Add account/auth themes to vocabulary
4. ⬜ Expand URL patterns for settings pages
5. ⬜ Update theme_extractor.py prompt with conversation type classification
6. ⬜ Test on larger dataset (100+ conversations)
7. ⬜ Document in architecture.md
