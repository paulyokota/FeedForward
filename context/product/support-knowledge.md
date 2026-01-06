# Tailwind Support Knowledge Base

Common issues, troubleshooting guides, and product behavior extracted from support.tailwindapp.com.

## Pinterest Publishing Issues

### Why Pins Fail to Publish

| Failure Reason              | Cause                                           | Solution                                                          |
| --------------------------- | ----------------------------------------------- | ----------------------------------------------------------------- |
| **Connection Lost**         | Password change on Pinterest, token expired     | Reconnect Pinterest via Dashboard or Reconnect Page               |
| **Board Access Lost**       | Removed from group board, board deleted         | Contact board owner for reinvite or reschedule to different board |
| **Account in Safe Mode**    | Pinterest detected suspicious activity          | Reset Pinterest password to exit safe mode                        |
| **Invalid Source URL**      | No URL, redirect URL, or spammy URL             | Provide direct, non-redirect URL to valid domain                  |
| **URL Points to Pinterest** | Pinterest rejects pins linking to pinterest.com | Use external destination URL                                      |
| **Pin Limit Exceeded**      | Account has 200,000+ pins                       | Delete some pins before scheduling new ones                       |
| **Technical Issue**         | Pinterest API outage (rare)                     | Resend to drafts and reschedule                                   |
| **Video Requirements**      | Personal account trying to post video           | Convert to Pinterest Business account                             |

### Where Are My Pins?

Users often can't find published pins because:

1. **Created vs Saved Tab** - Pins may appear in "Saved" instead of "Created"
2. **Requirements for "Created" tab**:
   - Must be Business account
   - Must have claimed domain
   - Source URL must point to claimed domain
   - Note: "Verified" badge is NOT the same as claimed domain

**Finding Published Pins:**

- Dashboard Calendar → Click pin → "View on Pinterest" link
- Insights → Pin Inspector → Sort by Date Pinned → Look for blue TW icon

## Instagram/Facebook Connection

### Why Meta Connection is Required

"This requirement is not only specific to Tailwind but is mandated by Meta for integrations with third-party platforms."

### Connection Requirements

1. **Instagram Business Account** (not Personal or Media Creator)
   - Settings > Account > Switch to Professional Account > Business
2. **Facebook Page** connected to Instagram
   - Through Instagram: Edit Profile > Public Business Information > Connect Page
   - Through Facebook: facebook.com/pages/create
3. **Tailwind Permissions** - All permissions must be granted

### Instagram Troubleshooting Checklist

- [ ] Instagram is connected to correct Facebook Page
- [ ] Account is Professional (Business) status
- [ ] Logged into correct personal Facebook profile (admin/owner of Page)
- [ ] All permissions selected during Tailwind authorization
- [ ] Full admin access in Meta Business Suite

### If Connection Issues Persist

1. Disconnect Instagram-Facebook relationship
2. Remove Tailwind from Facebook Business Integration settings
3. Reconnect everything fresh
4. Verify full control access in Meta Business Suite

## Instagram Publishing Issues

### Image/Video Requirements

| Requirement    | Specification                    |
| -------------- | -------------------------------- |
| Max file size  | 8MB                              |
| Formats        | JPEG, PNG, BMP, non-animated GIF |
| Aspect ratio   | 4:5 to 1.91:1                    |
| Min resolution | 150×150 pixels                   |
| Max resolution | 1920×1080 pixels                 |

### Caption/Hashtag Limits

- Max 2,200 characters
- Max 30 hashtags
- Exceeding either causes post failure

### Auto Post vs Push Notification

- **Auto Post** - Tailwind publishes automatically, requires Business account
- **Push Notification** - Tailwind sends reminder, you publish manually

## Multi-Network Scheduling

### Cross-posting Requirements

- Instagram must be connected to Facebook Page for cross-posting
- Each network may have different image/video requirements
- Captions may need adjustment for platform differences

## Failed/Missed Posts Dashboard

**Location:** Dashboard → Failed/Missed Posts tab

- **Failed tab** - Pins or auto-publish posts that failed with reasons
- **Missed tab** - Instagram Stories/Posts where notification was sent but not acted on

**Options:**

- Send back to Drafts to reschedule
- Delete entirely

## Browser Extension Issues

### Common Problems

- Extension not loading on certain websites
- Can't find save button
- Extension conflicts with other browser extensions

### Troubleshooting

1. Check browser compatibility (Chrome/Firefox supported)
2. Disable conflicting extensions
3. Clear browser cache
4. Reinstall extension

## Account & Collaboration Issues

### Email Already Exists Error

When adding a collaborator whose email is already in Tailwind:

- Use email aliasing: `name+tailwind@domain.com`
- Tailwind treats this as unique, but emails still arrive at main inbox

## Feature-Specific Terminology Mapping

| User Says               | They Mean                          |
| ----------------------- | ---------------------------------- |
| "pins not posting"      | Pinterest publishing failure       |
| "can't connect"         | OAuth/API connection issue         |
| "wrong board"           | Board selection/routing problem    |
| "smart schedule"        | SmartSchedule auto-optimization    |
| "create"                | Tailwind Create design tool        |
| "extension"             | Browser Extension (Chrome/Firefox) |
| "community/communities" | Tailwind Communities feature       |
| "ghost writer"          | Ghostwriter AI copywriting         |
| "schedule times"        | SmartSchedule time slots           |

## Contact Support

- Email: help@tailwindapp.com
- In-app: Help widget
- Knowledge base: support.tailwindapp.com

---

_Sources: support.tailwindapp.com articles scraped January 2026_
