# Flock - AI-Powered Organizational Intelligence Platform

> Your organization's knowledge and team dynamics, unified by AI.

Flock combines intelligent document management with personality-driven team insights. It's a dual-purpose platform that adapts to your organization's needs—whether you're managing knowledge and recruiting, or running a therapy practice matching patients with providers.

## 🎯 What Flock Does

Flock creates an AI-powered workspace for organizations that need to:

- **Chat with your organization's knowledge**: Ask questions about documents, policies, and team expertise in natural language
- **Auto-organize documents**: Documents automatically classify themselves by team, project, type, and time period
- **Find team expertise**: Semantic search to discover "who knows about Python?" or "who has experience with acquisitions?"
- **Test ideas before implementation**: AI agents simulate how team members will react to scenarios based on psychological profiles
- **Match people effectively**: Embed widgets to match patients with therapists, candidates with teams, or clients with service providers
- **Optimize team dynamics**: Discover collaboration patterns and compatibility through AI-powered networking analysis

## 🚀 Key Features

### 1. Organizations & Teams
- Create organizations and invite team members via unique invite links
- Members complete a 10-question psychological onboarding (compressed protocol)
- AI enriches profiles with LinkedIn data and personality analysis
- Beautiful Three.js visualization of team members

### 2. Three Simulation Modes

#### 🎭 Simulation Mode
Model how each team member responds to specific scenarios.

**Use Cases:**
- Test how investors will react to a pivot before the board meeting
- Predict team responses to policy changes
- Anticipate objections and prepare messaging

**How it works:**
1. Enter a scenario (e.g., "We're pivoting from B2B to B2C")
2. AI agents representing each team member generate responses based on their psychological profiles
3. View detailed predictions for each person's reaction, concerns, and suggestions

#### 🎉 Party Mode
AI agents interact and collaborate in virtual scenarios to discover team dynamics.

**Use Cases:**
- Team building and composition optimization
- Finding natural collaborations and synergies
- Testing team compatibility before projects

**How it works:**
1. Enter a context/goal for the team
2. AI agents representing team members interact with each other
3. System identifies collaboration patterns, synergies, and potential conflicts

#### 🤝 Networking Mode
Analyze event attendees and optimize networking strategy.

**Use Cases:**
- Conference/event preparation for your team
- Strategic networking with clear ROI
- Maximizing business development opportunities

**How it works:**
1. Upload event attendee list (names + LinkedIn URLs)
2. Input your team's goals
3. System analyzes all attendees and recommends who each team member should prioritize meeting

### 3. Embeddable Widget
Public questionnaire that can be embedded on any website or Notion page.

**Use Cases:**
- **Clinical Teams**: Patients fill out questionnaire and see which therapist matches their needs
- **Recruiting**: Candidates assess their fit with team culture before applying
- **Customer Service**: Match clients with the right service provider

**Features:**
- No sign-up required for users
- Two modes: Party Mode (compatibility) or Simulation Mode (team assessment)
- Customizable person specification (e.g., "new patient seeking therapy")
- Beautiful standalone interface matching your brand

**Setup:**
1. Go to Organization → Embed Settings
2. Choose mode and configure settings
3. Copy iframe code or URL
4. Embed on website or Notion

### 4. AI-Powered Onboarding
Deep psychological profiling through a 10-question compressed protocol.

**Questions Cover:**
1. Defining Moment - Life-changing decisions
2. Resource Allocation - Financial priorities
3. Conflict Response - Disagreement navigation
4. Trade-off Scenario - Values vs. money
5. Social Identity - Community importance
6. Moral Dilemma - Ethical frameworks
7. System Trust - Institutional trust
8. Stress Response - Coping mechanisms
9. Future Values - Goals and aspirations
10. Demographics - Name, age, location, LinkedIn

**AI Analysis:**
- Big Five personality traits
- Value hierarchy and conflicts
- Decision-making patterns
- Moral frameworks
- Stress coping and resilience
- Behavioral predictions
- LinkedIn enrichment (professional background, education, career trajectory)

### 5. Subscription Management
- 20 free simulations per user
- Stripe integration for paid subscriptions
- Subscription required beyond free tier

## 🏗️ Architecture

### Technology Stack
- **Backend**: Python 3, Flask
- **Database**: PostgreSQL (hosted on DigitalOcean)
- **AI**: OpenAI GPT-4 for simulations and analysis
- **Payments**: Stripe
- **Email**: Gmail SMTP
- **Deployment**: DigitalOcean, accessible at https://pont.world

### File Structure

```
flock/
├── app.py                          # Main Flask application (16,298 lines)
├── onboarding.py                   # Onboarding questionnaire flow
├── onboarding_agent.py             # AI personality analysis
├── linkedin_scraper.py             # LinkedIn profile enrichment
├── enhanced_matching_system.py     # Compatibility algorithms
├── payment.py                      # Stripe subscription management
├── email_followup.py               # Email automation
├── data_safety.py                  # Data encryption utilities
├── wsgi.py                         # WSGI entry point
├── requirements.txt                # Python dependencies
├── .env                            # Environment variables
└── README.md                       # This file
```

### Database Schema

#### Core Tables

**users**
- User accounts with encrypted email, phone, name
- Password authentication
- Profile completion status
- Data consent tracking

**user_profiles**
- Stores onboarding questionnaire responses (JSON)
- AI-generated personality insights
- LinkedIn data
- Agent onboarding script for simulations

**organizations**
- Team/organization details
- Unique invite tokens
- Owner and creation metadata

**organization_members**
- Junction table: users ↔ organizations
- Role (owner/member)
- Join date and active status

**simulations**
- Scenario text and metadata
- Organization and creator
- Status and completion timestamp

**simulation_responses**
- AI-generated responses for each simulation
- JSON format with predictions
- Links simulation → user

**embed_configurations**
- Widget settings for organizations
- Mode (party/simulation)
- Person specification
- Unique embed tokens

**embed_sessions**
- Anonymous widget usage tracking
- Onboarding data from widget users
- Simulation results

#### Supporting Tables
- **profile_privacy**: User privacy settings
- **contact_requests**: Connection requests
- **followup_tracking**: Email follow-up automation
- **password_reset_tokens**: Password recovery
- **events**: Event management (legacy)
- **networks**: Network visualization data
- Plus Stripe-related tables for subscriptions

### Key Routes (58 total)

#### Public Routes
- `GET /` - Landing page
- `GET /register` - Sign up
- `POST /register` - Create account
- `GET /login` - Sign in
- `POST /login` - Authenticate
- `GET /embed/<token>` - Public embed widget
- `POST /embed/<token>/process` - Process widget submissions

#### Authenticated Routes
- `GET /dashboard` - Organization list
- `GET /profile-setup` - Start onboarding
- `GET /onboarding/step/<step>` - Onboarding questionnaire (10 steps)
- `POST /onboarding/complete` - Complete onboarding

#### Organization Management
- `GET /create-organization` - Create new organization
- `POST /create-organization` - Save organization
- `GET /organization/<id>` - Organization view with Three.js
- `GET /organization/<id>/edit` - Edit organization
- `GET /organization/<id>/delete` - Delete organization
- `GET /organization/<id>/embed-settings` - Configure embed widget
- `GET /join-organization/<token>` - Join via invite link

#### Simulation API
- `POST /api/run-simulation` - Run Simulation Mode
- `POST /api/run-party-mode` - Run Party Mode
- `POST /api/run-networking-mode` - Run Networking Mode
- `GET /api/load-simulation/<id>` - Load saved simulation
- `DELETE /api/delete-simulation/<id>` - Delete simulation

#### Subscription & Payments
- `GET /subscription/check` - Check subscription status
- `GET /subscription/subscribe` - Subscribe page
- `GET /subscription/plans` - View pricing plans
- `POST /webhook/stripe` - Stripe webhook handler

#### Settings & Profile
- `GET /profile-settings` - Edit profile
- `GET /edit-profile` - Edit onboarding answers
- `GET /settings` - User settings

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.8+
- PostgreSQL database
- OpenAI API key
- Stripe account (for payments)
- Gmail account (for emails)

### Environment Variables

Create a `.env` file with:

```bash
# Flask
FLASK_ENV=production
SECRET_KEY=your-secret-key

# Database
DATABASE_URL=postgresql://user:password@host:port/database

# OpenAI
OPENAI_API_KEY=sk-...

# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
EMAIL_FROM=your-email@gmail.com

# Base URL
BASE_URL=https://pont.world

# Encryption
ENCRYPTION_MASTER_KEY=your-encryption-key
ENCRYPTION_PASSWORD=your-encryption-password
ENCRYPTION_SALT=your-salt
HASH_SALT=your-hash-salt
DATABASE_ENCRYPTION_KEY=your-db-key

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...

# Optional: LinkedIn scraping
PROXYCURL_API_KEY=your-proxycurl-key
```

### Installation

```bash
# Clone repository
git clone <repository-url>
cd flock

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize database (tables created automatically on first run)
python app.py
```

### Running Locally

```bash
# Development
export FLASK_ENV=development
python app.py

# Production (with gunicorn)
gunicorn wsgi:app --bind 0.0.0.0:8080
```

Access at `http://localhost:8080`

## 📖 Usage Guide

### For Team Owners

#### 1. Create Your Team
1. Sign up at https://pont.world/register
2. Complete the 10-question onboarding (takes ~15 minutes)
3. Optionally provide LinkedIn URL for enriched profiling
4. Click "Create Organization"
5. Name your team and add description

#### 2. Invite Team Members
1. Copy the invite link from your organization page
2. Share with team members
3. They'll sign up and complete onboarding
4. Watch them appear in the Three.js visualization

#### 3. Run Simulations

**Simulation Mode:**
1. Click "Simulation Mode" in your organization
2. Enter a scenario (e.g., "We're considering remote work policy")
3. Click "Simulate Responses"
4. View each team member's predicted reaction

**Party Mode:**
1. Click "Party Mode"
2. Enter context/goal
3. AI agents interact
4. View collaboration patterns

**Networking Mode:**
1. Click "Networking Mode"
2. Paste attendee list (Name, LinkedIn URL per line)
3. Enter your team's goal
4. Get personalized recommendations for each team member

#### 4. Set Up Embed Widget
1. Go to organization → "Embed Widget"
2. Choose mode:
   - **Party Mode**: For compatibility assessment
   - **Simulation Mode**: For team engagement analysis
3. Configure settings
4. Copy embed code
5. Add to website or Notion page

### For Embed Widget Users
1. Visit the embedded widget on a website
2. Fill out the questionnaire (no account needed)
3. View results showing:
   - **Party Mode**: Your compatibility with each team member
   - **Simulation Mode**: How each team member would engage with you

## 🧠 How It Works

### Personality Profiling

1. **Onboarding Questions**: User answers 10 high-variance diagnostic questions
2. **LinkedIn Enrichment**: Optional LinkedIn scraping adds professional context
3. **AI Analysis**: GPT-4 extrapolates psychological insights:
   - Core values and conflicts
   - Decision-making patterns
   - Big Five personality traits
   - Moral frameworks
   - Stress coping mechanisms
   - Behavioral predictions
4. **Agent Script**: Generated personality profile used for simulations

### Simulation Engine

1. **Input**: Scenario/context + team member profiles
2. **Processing**: For each team member:
   - Retrieve their personality profile
   - Construct prompt with scenario + profile
   - Call OpenAI API
   - Parse structured response
3. **Storage**: Save simulation and responses to database
4. **Output**: Display predictions in Three.js visualization

### Embed Widget Flow

1. **Configuration**: Organization owner sets mode and settings
2. **Deployment**: Unique URL generated with embed token
3. **User Interaction**: Anonymous user fills questionnaire
4. **Processing**: AI analyzes against team profiles
5. **Results**: Instant compatibility or engagement assessment

## 🔒 Security & Privacy

- **Encryption**: User emails, phone numbers, and names encrypted at rest
- **Password Security**: Bcrypt hashing for passwords
- **Data Consent**: Explicit opt-in for data processing
- **Privacy Controls**: Users control what profile information is shared
- **HTTPS**: All traffic encrypted in transit
- **Session Management**: Secure session cookies with httponly flag

## 💰 Pricing

- **Free Tier**: 20 simulations per user
- **Paid Subscription**: Unlimited simulations
  - Managed via Stripe
  - Monthly or annual billing
  - Self-service subscription management

## 🚀 Deployment

Application is deployed on DigitalOcean and accessible at:
**https://pont.world**

### Production Setup
- PostgreSQL database on DigitalOcean
- Gunicorn WSGI server
- Environment variables configured in DigitalOcean App Platform
- Automatic SSL via DigitalOcean

## 📊 Analytics & Monitoring

- Simulation usage tracking per user
- Embed widget session tracking
- Subscription status monitoring
- Email delivery tracking
- Error logging to console

## 🤝 Contributing

This is a private project. For questions or issues, contact the development team.

## 📝 License

Proprietary - All rights reserved

## 🆘 Support

For technical support or questions:
- Email: alessa@pont-diagnostics.com
- Issues: Contact development team

## 🗺️ Roadmap

### Current Features ✅
- Organizations and team management
- Three simulation modes (Simulation, Party, Networking)
- Embeddable widget
- AI-powered personality profiling
- Stripe subscription management
- LinkedIn enrichment

### Future Enhancements 🚧
- Real-time collaboration on simulations
- Export simulation results
- API access for integrations
- Advanced analytics dashboard
- Custom branding for embed widgets
- Multi-language support

---

**Built with ❤️ by the Pont team**

*Last updated: October 2025*
