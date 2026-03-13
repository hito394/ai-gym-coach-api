# AI Gym Coach Product Strategy (18Birdies-Inspired)

This document translates 18Birdies product patterns into an AI-powered gym coaching app.

Current strengths to preserve:
- Quick Log Pad
- Bottom-fixed LOG SET button
- Haptics
- Automatic rest timer
- Manual workout logging and custom menu
- Log manager with edit and delete
- Online sync + offline retry queue
- FastAPI integration
- AI coach endpoint

## 1) Best Features To Borrow From 18Birdies

### Activity Tracking
- 18Birdies: Tracks the full golf round timeline.
- Gym equivalent: Track each workout session as a structured timeline (warmup, working sets, rest, finish).
- Priority: MVP.

### Event-Level Tracking
- 18Birdies: Shot-by-shot tracking.
- Gym equivalent: Set-by-set and rep-level tracking with one-tap logging.
- Priority: MVP (already mostly implemented).

### Real-Time Assistance
- 18Birdies: Contextual help while playing.
- Gym equivalent: Live form feedback and next-set guidance in-session.
- Priority: MVP.

### Performance Statistics
- 18Birdies: Score and trend statistics.
- Gym equivalent: e1RM, volume trend, frequency, PR events.
- Priority: MVP.

### AI Caddie/Coach
- 18Birdies: Decision support.
- Gym equivalent: Coach summaries, progression suggestions, recovery tips.
- Priority: MVP.

### Historical Performance
- 18Birdies: Historical rounds and comparisons.
- Gym equivalent: Weekly and monthly progress comparisons.
- Priority: MVP.

### Social Challenge and Leaderboard
- 18Birdies: Competition and motivation loops.
- Gym equivalent: Weekly challenge board and streak competition.
- Priority: Post-MVP.

### Wearables
- 18Birdies: Device and sensor integrations.
- Gym equivalent: Apple Health / wearable data for fatigue and readiness.
- Priority: Post-MVP.

## 2) Feature Translation Mapping

- Golf Round Tracking -> Workout Session Tracking
- Golf Shot Tracking -> Rep and Set Tracking
- Golf Stats -> Strength Progress Analytics
- Swing Analyzer -> Exercise Form Analysis
- Golf School -> Exercise Coaching Tips
- Leaderboard -> Fitness Challenges
- Caddy Strategy -> Workout Optimization
- Historical Performance -> Strength Progress Graphs

## 3) MVP vs Later Prioritization

### MVP (next)
- Real-time form feedback HUD (green/yellow/red indicators)
- Session-end AI summary with actionable bullets
- Core analytics: weight progression, e1RM trend, weekly volume trend
- Plateau detection and recommendation prompts

### Post-MVP
- Challenges and small-group leaderboards
- Wearable and recovery score integration
- Smart workout optimization by readiness score

### Future
- Predictive PR model and cycle planning
- Advanced multi-angle form analysis
- Social squads and coach marketplace

## 4) Real-Time Form Analysis System

### Real-time UI
- Camera preview + skeletal overlay
- Depth guide bar
- Knee tracking bar
- Spine angle indicator
- Color states:
  - Green: in-range
  - Yellow: warning
  - Red: incorrect

### Detection Pipeline
1. Pose estimation (MoveNet or BlazePose)
2. Joint extraction with confidence scores
3. Kinematic feature computation (angles, velocity, symmetry)
4. Rep phase detection (eccentric, bottom, concentric, lockout)
5. Rule-based checks + lightweight classifier for final issue labels

### Exercise-specific checks
- Squat: hip depth ratio, knee valgus drift, trunk angle deviation
- Bench press: wrist/bar path consistency, elbow flare control
- Deadlift: spinal neutrality and bar proximity to shin line

### Stability and accuracy strategy
- Confidence threshold filtering
- Temporal smoothing (EMA / One Euro)
- Outlier rejection for impossible frame jumps
- Frame window consensus for color transitions
- Short calibration before each set

## 5) Progress Visualization Design

Use line charts as default.

### Dashboard
- Weekly training volume trend
- Workout frequency trend
- Body weight trend
- Mini e1RM trend for key lifts

### Exercise Page
- Weight progression by exercise
- e1RM over time
- Form score trend

### Analytics Page
- Weekly volume trend by training block
- Muscle group volume trend
- Session frequency trend
- Readiness vs performance trend

## 6) UX Structure (Gym Context)

Principles:
- One-hand operation
- Large touch targets
- Minimal typing
- Under-3-second set logging
- Low cognitive load

### Screen flow
1. Dashboard -> Start Workout
2. Workout Screen -> Quick/Manual Log + Rest Timer
3. Optional Form Analysis during working sets
4. End Session -> AI Summary
5. History / Analytics review

## 7) Technical Architecture

## Stack
- Frontend: Flutter
- Backend: FastAPI
- Database: PostgreSQL or Supabase
- AI: OpenAI API + on-device pose model
- Charts: fl_chart

### Data flow
1. User logs set in Flutter
2. Local state updates immediately
3. Online sync attempt to FastAPI
4. Offline queue handles retry
5. Analytics aggregates are fetched for charts
6. Coach endpoint returns short actionable guidance

### Recommended API endpoints
- POST /v1/workouts/session/start
- POST /v1/workouts/log_set
- POST /v1/workouts/delete_set
- POST /v1/workouts/session/end
- GET /v1/workouts/history/{user_id}
- GET /v1/analytics/summary/{user_id}
- GET /v1/analytics/exercise/{user_id}/{exercise_key}
- POST /v1/coach/after-workout
- POST /v1/form/analyze

### Core tables
- users
- workouts
- exercises
- sets
- progress_metrics
- body_metrics
- form_events

## 8) Suggested Next Features

### Phase 1 (retention-first)
- Real-time form HUD
- Session-end AI summary
- Core progress charts in dashboard and exercise page
- Plateau alert card

### Phase 2 (engagement)
- Weekly challenge module
- Readiness-aware load suggestion
- Wearable integration

### Phase 3 (advanced differentiation)
- Predictive progression engine
- Social competition with teams
- High-fidelity form diagnostics

## 9) Long-Term Product Roadmap

- 0-2 months: Perfect in-gym logging speed and coach summary loop
- 2-4 months: Ship analytics depth and plateau intervention
- 4-8 months: Add engagement loops (challenge + social)
- 8-12 months: Launch advanced AI coaching and predictive planning

## Implementation Notes

- Keep current quick logging architecture as the center of the product.
- Add complexity only when it clearly improves outcomes or retention.
- Every new screen should preserve one-hand, low-friction operation.
