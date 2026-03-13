# Usability-First AI Gym App Spec

This spec is intentionally optimized for simplicity, speed, and in-workout usability.

## 1) UX-Focused Product Design

### Design North Star
- Log one set in under 3 seconds.
- One-hand operation by default.
- Zero typing in the primary logging flow.

### Core UX Rules
- `Rule 1: One-tap defaults`
: Pre-fill last used weight/reps/rest for each exercise.
- `Rule 2: Thumb-first controls`
: Primary controls in lower half of screen.
- `Rule 3: No modal maze`
: Avoid nested dialogs during active workout.
- `Rule 4: Feedback under 1 line`
: AI form feedback should be short and actionable.
- `Rule 5: Decision-light UI`
: At each step, show one primary action.

### Primary User Flows
1. `Start Workout`
- Tap `Quick Start` from dashboard.
- Open day template with first exercise selected.

2. `Log Set` (3-second target)
- Tap `+2.5kg` or `-2.5kg`.
- Tap `+1 rep` or `-1 rep`.
- Tap large `Log Set` button.
- Auto-start rest timer.

3. `Review Progress`
- Open `Progress` tab.
- See 4 simple charts with one exercise filter.

4. `AI Form Check`
- Tap `Form Check`.
- Record short clip.
- Receive one-line feedback + one fix cue.

### Interaction Budget
- Weight adjust: 1 tap
- Reps adjust: 1 tap
- Save set: 1 tap
- Total: 3 taps

---

## 2) Wireframe Descriptions (Key Screens)

### A. Dashboard (Instant Read)
Top:
- Greeting + `Today` label
- Progress Score (large number)

Middle cards:
- `Quick Start Workout` (primary CTA, full width)
- `Last Workout` summary (exercise + top set)
- `Current Streak`

Bottom:
- Mini trend sparkline (weekly volume)
- Quick actions: `Form Check`, `History`, `Coach`

UX behavior:
- No dense tables.
- No more than 5 key numbers visible at once.

### B. Active Workout Screen (Primary Screen)
Header:
- Exercise name (large)
- Set index (e.g., Set 3/5)

Main controls (big buttons):
- Weight row: `-2.5` `-1.25` `[weight]` `+1.25` `+2.5`
- Reps row: `-1` `[reps]` `+1`

Bottom CTA:
- Large sticky `Log Set` button

Secondary:
- `Repeat Last Set`
- Rest timer chip after save

UX behavior:
- No text fields in primary flow.
- Haptic feedback on save.

### C. Progress Screen
Top filter:
- Exercise segmented selector
- Time range selector (`4w`, `8w`, `12w`)

Charts (stacked, simple):
- Weight progression
- Estimated 1RM
- Weekly volume
- Workout consistency

UX behavior:
- Minimal axes labels.
- Tooltip on touch.

### D. Form Analysis Screen
Top:
- Camera preview

Bottom panel:
- `Record` / `Stop`
- Current quality indicator

Result card:
- Short line: `Depth slightly shallow.`
- Single cue: `Go 2-3 inches deeper while keeping chest up.`

UX behavior:
- One issue at a time.
- Avoid multi-paragraph coaching.

### E. Workout History Timeline
Date-grouped cards:
- `Mon, Mar 11`
- Key sets summary: `Bench 85 x 5`, `Squat 110 x 5`
- Session volume total

Tap card:
- Expand to all sets

UX behavior:
- Timeline first, details on demand.

---

## 3) Simplified MVP Feature Set

### Must Have (2-4 weeks)
1. Fast set logging with + / - controls
2. Workout session start/end
3. Progress charts (4 metrics)
4. Basic AI form feedback (squat first)
5. Dashboard with quick start + score + last workout
6. Workout history timeline
7. Streak + weekly progress indicator

### Should Have
1. Offline queue for set logs
2. Repeat last set shortcut
3. Rest timer auto-start

### Not in MVP
1. Full social feed
2. Challenge matchmaking
3. Complex coaching plans

---

## 4) Database Schema (PostgreSQL/Supabase)

```sql
create table users (
  id bigserial primary key,
  email text unique,
  created_at timestamptz not null default now()
);

create table exercises (
  id bigserial primary key,
  exercise_key text unique not null,
  display_name text not null,
  muscle_group text,
  created_at timestamptz not null default now()
);

create table workout_sessions (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  session_key text unique,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  note text
);

create table workout_sets (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  workout_session_id bigint references workout_sessions(id) on delete set null,
  exercise_key text not null,
  set_index int not null,
  reps int not null,
  weight_kg numeric(6,2) not null,
  rpe numeric(3,1),
  rest_seconds int,
  performed_at timestamptz not null default now(),
  client_id text,
  unique(user_id, client_id)
);

create table body_weight_logs (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  weight_kg numeric(6,2) not null,
  measured_at timestamptz not null default now()
);

create table form_analysis_sessions (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  exercise_key text not null,
  model_name text,
  model_version text,
  overall_score numeric(5,2),
  depth_score numeric(5,2),
  symmetry_score numeric(5,2),
  torso_score numeric(5,2),
  tempo_score numeric(5,2),
  issues jsonb,
  feedback text,
  diagnostics jsonb,
  created_at timestamptz not null default now()
);

create table weekly_progress_scores (
  id bigserial primary key,
  user_id bigint not null references users(id) on delete cascade,
  week_label text not null,
  score numeric(5,2) not null,
  strength_component numeric(5,2) not null,
  consistency_component numeric(5,2) not null,
  volume_component numeric(5,2) not null,
  unique(user_id, week_label)
);
```

---

## 5) API Endpoint Design

Base: `/v1`

### Workout Logging
- `POST /workouts/start`
- `POST /workouts/log_set`
- `POST /workouts/end`
- `GET /workouts/history/{user_id}?limit=20`

### Analytics
- `GET /analytics/summary/{user_id}`
- `GET /analytics/progress/{user_id}?exercise_key=bench_press`
- `GET /analytics/progress-score/{user_id}`

### Body Weight
- `POST /users/{user_id}/body-weight`
- `GET /users/{user_id}/body-weight?limit=30`

### AI Form
- `POST /form/analyze`

### AI Coach
- `POST /chat/coach`

### Health
- `GET /health`

Response design rules:
- Keep payload compact.
- Return front-end friendly names.
- Include fallback-safe defaults.

---

## 6) Flutter UI Structure (Usability-Optimized)

```text
lib/
  app/
    router.dart
    providers.dart
  core/
    theme/
    network/
    haptics/
  domain/
    models/
  data/
    services/
    repositories/
  features/
    dashboard/
      screens/dashboard_screen.dart
      providers/dashboard_provider.dart
      widgets/summary_cards.dart
    workout/
      screens/workout_screen.dart
      screens/workout_history_screen.dart
      providers/workout_provider.dart
      widgets/quick_log_pad.dart
      widgets/rest_timer_chip.dart
    progress/
      screens/progress_screen.dart
      widgets/trend_chart_card.dart
    form/
      screens/form_camera_screen.dart
      providers/form_provider.dart
    chat/
      screens/chat_screen.dart
```

Implementation notes:
- Put `QuickLogPad` at bottom for one-hand access.
- Keep sticky `Log Set` button always visible.
- Prefer chips, steppers, and presets over keyboard input.

---

## 7) Example Progress Chart (Flutter + fl_chart)

```dart
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

class ProgressLineChart extends StatelessWidget {
  const ProgressLineChart({
    super.key,
    required this.title,
    required this.points,
    required this.color,
  });

  final String title;
  final List<double> points;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final spots = <FlSpot>[];
    for (var i = 0; i < points.length; i++) {
      spots.add(FlSpot(i.toDouble(), points[i]));
    }

    final maxY = points.isEmpty
        ? 1.0
        : points.reduce((a, b) => a > b ? a : b) * 1.15;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            SizedBox(
              height: 180,
              child: LineChart(
                LineChartData(
                  minY: 0,
                  maxY: maxY,
                  gridData: FlGridData(show: true, drawVerticalLine: false),
                  borderData: FlBorderData(show: false),
                  titlesData: FlTitlesData(
                    topTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false),
                    ),
                    rightTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false),
                    ),
                    leftTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: true, reservedSize: 36),
                    ),
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        getTitlesWidget: (value, _) => Text('W${value.toInt() + 1}'),
                      ),
                    ),
                  ),
                  lineTouchData: const LineTouchData(enabled: true),
                  lineBarsData: [
                    LineChartBarData(
                      spots: spots,
                      isCurved: true,
                      color: color,
                      barWidth: 3,
                      dotData: const FlDotData(show: true),
                      belowBarData: BarAreaData(show: true, color: color.withAlpha(32)),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
```

---

## 8) Backend Starter Code (FastAPI)

```python
# app/main.py
from fastapi import FastAPI
from app.api.routes import health, workouts, analytics, users, form, chat

app = FastAPI(title="Usability-First AI Gym API", version="0.1.0")

app.include_router(health.router, prefix="/v1")
app.include_router(users.router, prefix="/v1")
app.include_router(workouts.router, prefix="/v1")
app.include_router(analytics.router, prefix="/v1")
app.include_router(form.router, prefix="/v1")
app.include_router(chat.router, prefix="/v1")
```

```python
# app/api/routes/workouts.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/workouts", tags=["workouts"])

class LogSetIn(BaseModel):
    user_id: int
    exercise_key: str
    reps: int
    weight_kg: float
    rest_seconds: Optional[int] = None
    session_id: Optional[str] = None
    client_id: Optional[str] = None

@router.post("/start")
def start_workout(user_id: int):
    return {"session_key": "sess_123", "started": True}

@router.post("/log_set")
def log_set(payload: LogSetIn):
    # TODO: idempotent write by (user_id, client_id)
    return {
        "ok": True,
        "exercise_key": payload.exercise_key,
        "reps": payload.reps,
        "weight_kg": payload.weight_kg,
    }

@router.post("/end")
def end_workout(session_key: str):
    return {"ok": True, "session_key": session_key}
```

```python
# app/api/routes/analytics.py
from fastapi import APIRouter

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/summary/{user_id}")
def summary(user_id: int):
    return {
        "user_id": user_id,
        "progress_score": 74.2,
        "weekly_volume": 12450,
        "workout_frequency": 4,
        "insights": ["Bench is improving steadily"],
        "weekly_volume_points": [
            {"label": "2026-W08", "value": 9800},
            {"label": "2026-W09", "value": 11200},
            {"label": "2026-W10", "value": 11850},
            {"label": "2026-W11", "value": 12450},
        ],
    }
```

```python
# app/api/routes/form.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter(prefix="/form", tags=["form"])

class AnalyzeIn(BaseModel):
    user_id: int
    exercise_key: str
    diagnostics: Dict[str, Any]

@router.post("/analyze")
def analyze(payload: AnalyzeIn):
    return {
        "overall_score": 81.0,
        "issues": ["shallow_depth"],
        "feedback": "Your squat depth is slightly shallow. Try going 2-3 inches deeper.",
    }
```

---

## Implementation Priority (Strictly Usability-First)
1. Replace typing-heavy set input with quick increment pad.
2. Make `Log Set` sticky and thumb-reachable.
3. Keep dashboard to 4 key items only.
4. Keep AI feedback short: issue + one actionable cue.
5. Preserve chart clarity over chart density.
