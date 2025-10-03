# flock
# Platform Pivot Plan: From Matching Service to Business/Team Simulation Platform

## Overview
Transform the current friendship matching platform into a team dynamics simulation tool where organizations can model and predict how team members will respond to different scenarios.

## Database Schema Changes

### New Tables to Create:
1. **organizations** - Store org details (name, created_by, invite_link, created_at)
2. **organization_members** - Junction table linking users to orgs with their join date and role
3. **simulations** - Store each simulation (org_id, scenario_text, created_by, created_at, status)
4. **simulation_responses** - Store AI-generated responses (simulation_id, user_id, response_json)

### Tables to Modify:
- **users** table: Keep existing but ensure it supports org membership
- **user_profiles**: Reuse for storing onboarding answers that feed into simulations

## Core User Flow Changes

### 1. Sign Up & Initial Onboarding (Mostly Keep)
- Keep existing auth system ([app.py:5654-6118](app.py))
- Keep onboarding questions ([onboarding.py](onboarding.py)) - these become the "persona" data for simulations
- Onboarding answers saved to user_profiles table

### 2. Create Organization (New)
- After onboarding, redirect to "Create Organization" page instead of events
- User becomes org owner
- Generate unique invite link: `/join-org/<org_token>`
- Store org in new `organizations` table

### 3. Invite Team Members (New)
- Org page shows invite link to share
- Display Three.js visualization with current members as spheres
- Real-time updates as people join

### 4. Join Organization Flow (New)
- Click invite link → lands on join page
- If not logged in: sign up → onboarding → auto-join org
- If logged in but no profile: onboarding → auto-join org  
- If logged in with profile: confirm join → add to org
- Upon joining: add member sphere to Three.js (visible to all)

### 5. Dashboard (Major Redesign)
- Replace current dashboard ([app.py:7313-7408](app.py)) with org list
- Show cards for each org user belongs to
- Click org → enter org simulation view

### 6. Organization Simulation View (New - Core Feature)
**Left Sidebar:**
- Saved "Chats" (past simulations) with + button for new simulation
- Toggle to show/hide

**Center:**
- Three.js visualization with sphere per team member + their name label
- Text input: "Enter a scenario..."
- "Simulate" button underneath

**Right Sidebar:**
- Hidden until simulation complete
- Click sphere → shows that person's predicted response
- JSON formatted nicely

**Top Navigation:**
- Dashboard link (back to org list)
- Settings link (profile, etc.)

### 7. Simulation Engine (New)
When "Simulate" clicked:
- For each org member:
  - Fetch their onboarding answers from user_profiles
  - Construct prompt: `[onboarding data] + [scenario] + "Predict their response in this format: {...}"`
  - Call OpenAI API
  - Store response in simulation_responses table
- Save simulation to simulations table
- Add to left sidebar "Chats"
- Show results in UI

## Files to Modify

### Primary Changes:
1. **app.py** (lines 7313+):
   - Replace `/dashboard` route with org list view
   - Remove event matching logic
   - Add org CRUD routes
   - Add simulation API routes
   - Add Three.js template rendering

2. **onboarding.py**:
   - Keep existing onboarding flow
   - Remove event selection redirect
   - Redirect to "create org" after completion

3. **Database schema** (app.py ~160-300):
   - Add new tables for orgs, members, simulations, responses
   - Keep users and user_profiles tables

### New Files to Create:
1. **static/js/threejs-org-view.js** - Three.js visualization
2. **Organization routes** in app.py or separate module

### Files/Features to Remove:
- Event system routes ([app.py:12929-14307](app.py))
- Matching algorithm calls
- Contact request system ([app.py:9893-10524](app.py))


## Implementation Steps

1. **Database migrations** - Add new tables
2. **Create org flow** - Build org creation, invite, join logic
3. **Dashboard redesign** - Org list view
4. **Three.js visualization** - Sphere rendering with real-time updates
5. **Simulation engine** - OpenAI integration for response prediction
6. **Org simulation view** - Full UI with sidebars, input, results
7. **Clean up** - Remove unused event/matching code
8. **Testing** - Multi-user org scenarios

## Key Considerations

- **Real-time updates**: Use WebSockets or polling for Three.js sphere additions
- **Simulation performance**: Async processing for multiple team members
- **Data privacy**: Onboarding answers are sensitive - maintain encryption
- **Scalability**: Index org_id and simulation_id fields

This pivot reuses ~60% of existing code (auth, onboarding, profile storage) while replacing the matching/events core with org/simulation logic.