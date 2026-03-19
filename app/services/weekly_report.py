"""
Weekly AI coaching report generator.

Aggregates the user's last 7 days of training data and body metrics,
then uses Claude to generate a personalised Japanese coaching report.
Falls back to a rule-based summary if no API key is set.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.db import models


def generate_weekly_report(
    user_id: int,
    db: Session,
    api_key: Optional[str] = None,
) -> dict:
    """
    Returns a coaching report dict with keys:
      - period_start / period_end  (ISO dates)
      - sessions_count
      - total_volume_kg
      - form_avg_score
      - top_exercise
      - achievements_earned
      - body_weight_change_kg  (None if not enough data)
      - ai_report  (markdown text, AI or rule-based)
      - source      ("ai" | "rule_based")
    """
    now = datetime.utcnow()
    week_start = now - timedelta(days=7)

    # ----------------------------------------------------------------
    # Gather stats
    # ----------------------------------------------------------------
    workout_sessions = (
        db.query(models.WorkoutSession)
        .filter(
            models.WorkoutSession.user_id == user_id,
            models.WorkoutSession.started_at >= week_start,
        )
        .all()
    )

    form_sessions = (
        db.query(models.FormAnalysisSession)
        .filter(
            models.FormAnalysisSession.user_id == user_id,
            models.FormAnalysisSession.created_at >= week_start,
        )
        .all()
    )

    achievements = (
        db.query(models.FormAchievement)
        .filter(
            models.FormAchievement.user_id == user_id,
            models.FormAchievement.created_at >= week_start,
        )
        .all()
    )

    # Body weight
    bw_logs = (
        db.query(models.BodyWeightLog)
        .filter(
            models.BodyWeightLog.user_id == user_id,
            models.BodyWeightLog.measured_at >= week_start - timedelta(days=7),
        )
        .order_by(models.BodyWeightLog.measured_at.asc())
        .all()
    )

    # User profile
    user = db.query(models.User).filter(models.User.id == user_id).first()

    # ---- Compute summary values ----
    sessions_count = len(workout_sessions)
    total_volume = sum(s.total_volume or 0.0 for s in workout_sessions)
    form_avg = (
        round(sum(s.overall_score for s in form_sessions) / len(form_sessions), 1)
        if form_sessions else None
    )

    # Top exercise (most sets in the week)
    from collections import Counter
    set_logs = (
        db.query(models.SetLog)
        .filter(
            models.SetLog.user_id == user_id,
            models.SetLog.performed_at >= week_start,
        )
        .all()
    )
    exercise_counts = Counter(s.exercise_key or s.exercise for s in set_logs)
    top_exercise = exercise_counts.most_common(1)[0][0] if exercise_counts else None

    # Body weight change
    bw_change = None
    if len(bw_logs) >= 2:
        bw_change = round(bw_logs[-1].weight_kg - bw_logs[0].weight_kg, 1)

    stats = {
        "period_start": week_start.date().isoformat(),
        "period_end": now.date().isoformat(),
        "sessions_count": sessions_count,
        "total_volume_kg": round(total_volume, 1),
        "form_avg_score": form_avg,
        "top_exercise": top_exercise,
        "achievements_earned": len(achievements),
        "body_weight_change_kg": bw_change,
        "exercise": user.goal if user else None,
        "experience": user.experience_level if user else None,
    }

    # ----------------------------------------------------------------
    # Try AI report first
    # ----------------------------------------------------------------
    if api_key:
        ai_text = _generate_ai_report(stats, api_key)
        if ai_text:
            stats["ai_report"] = ai_text
            stats["source"] = "ai"
            return stats

    # ----------------------------------------------------------------
    # Fallback: rule-based report
    # ----------------------------------------------------------------
    stats["ai_report"] = _rule_based_report(stats)
    stats["source"] = "rule_based"
    return stats


def _generate_ai_report(stats: dict, api_key: str) -> Optional[str]:
    """Call Claude to write a coaching report. Returns text or None."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""あなたは優秀なパーソナルトレーナーです。
以下はユーザーの今週のトレーニングデータです。
この1週間を振り返るコーチングレポートを日本語で書いてください。

【今週のデータ】
- トレーニング回数: {stats['sessions_count']}回
- 合計ボリューム: {stats['total_volume_kg']} kg
- フォームスコア平均: {stats['form_avg_score'] or '未計測'}
- 最も多く行った種目: {stats['top_exercise'] or '未記録'}
- 獲得アチーブメント数: {stats['achievements_earned']}個
- 体重変化: {f"{stats['body_weight_change_kg']:+.1f} kg" if stats['body_weight_change_kg'] is not None else '未記録'}
- ゴール: {stats['exercise'] or '未設定'}
- 経験レベル: {stats['experience'] or '未設定'}

以下の形式でレポートを書いてください（markdown形式、400文字以内）：
1. 今週の振り返り（良かった点）
2. 改善ポイント
3. 来週に向けたアドバイス

簡潔で励みになる内容にしてください。"""

        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception:
        return None


def _rule_based_report(stats: dict) -> str:
    """Generate a simple markdown report without AI."""
    lines = []
    n = stats["sessions_count"]

    # --- 振り返り ---
    lines.append("## 今週の振り返り")
    if n == 0:
        lines.append("今週はトレーニングの記録がありませんでした。来週こそ始めましょう！")
    elif n >= 4:
        lines.append(f"素晴らしい！今週は **{n}回** トレーニングできました。コンスタントに取り組んでいますね。")
    elif n >= 2:
        lines.append(f"今週は **{n}回** トレーニングを記録しました。着実に積み上げています。")
    else:
        lines.append(f"今週は **{n}回** 記録しました。忙しい中でも続けられていますね。")

    if stats["total_volume_kg"] > 0:
        lines.append(f"合計ボリューム: **{stats['total_volume_kg']} kg**")

    if stats["form_avg_score"] is not None:
        score = stats["form_avg_score"]
        if score >= 85:
            lines.append(f"フォームスコア平均 **{score}点** — 非常に良いフォームを維持できています！")
        elif score >= 70:
            lines.append(f"フォームスコア平均 **{score}点** — 良いフォームです。あと少しで上級者レベル。")
        else:
            lines.append(f"フォームスコア平均 **{score}点** — フォームの改善に集中しましょう。")

    if stats["achievements_earned"] > 0:
        lines.append(f"🏆 今週 **{stats['achievements_earned']}個** のアチーブメントを獲得しました！")

    # --- 体重変化 ---
    if stats["body_weight_change_kg"] is not None:
        delta = stats["body_weight_change_kg"]
        if delta < -0.5:
            lines.append(f"\n## 体重変化\n体重が **{delta:+.1f} kg** 変化しました。目標に向けて良いペースです。")
        elif delta > 0.5:
            lines.append(f"\n## 体重変化\n体重が **{delta:+.1f} kg** 増加しました。筋肉増加の可能性があります。")

    # --- 来週へのアドバイス ---
    lines.append("\n## 来週に向けて")
    if n == 0:
        lines.append("まず週2回から始めてみましょう。小さな一歩が大きな変化につながります。")
    elif stats["form_avg_score"] is not None and stats["form_avg_score"] < 70:
        lines.append("重量より **フォームの質** を優先してください。軽い重量で10点満点を目指しましょう。")
    else:
        lines.append("今週の調子を維持して、少しずつ負荷を上げていきましょう！")

    return "\n".join(lines)
