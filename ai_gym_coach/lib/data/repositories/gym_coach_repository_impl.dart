import '../../domain/models/user_profile.dart';
import '../../domain/models/workout_plan.dart';
import '../../domain/models/set_log.dart';
import '../../domain/models/progress_summary.dart';
import '../../domain/models/progression_decision.dart';
import '../../domain/models/workout_history.dart';
import '../../domain/repositories/gym_coach_repository.dart';
import '../models/user_profile_dto.dart';
import '../models/workout_plan_dto.dart';
import '../models/set_log_dto.dart';
import '../models/progress_summary_dto.dart';
import '../models/progression_decision_dto.dart';
import '../models/workout_history_dto.dart';
import '../services/gym_coach_api.dart';

class GymCoachRepositoryImpl implements GymCoachRepository {
  GymCoachRepositoryImpl(this._api);

  final GymCoachApi _api;

  @override
  Future<UserProfile> createProfile({
    required int age,
    required double weightKg,
    required double heightCm,
    required String experienceLevel,
    required String goal,
    required int trainingDays,
    required List<String> equipment,
  }) async {
    final payload = UserProfileDto.toJson(
      age: age,
      weightKg: weightKg,
      heightCm: heightCm,
      experienceLevel: experienceLevel,
      goal: goal,
      trainingDays: trainingDays,
      equipment: equipment,
    );

    final data = await _api.createProfile(payload);
    return UserProfileDto.fromJson(data);
  }

  @override
  Future<WorkoutPlan> generateWorkout({
    required int profileId,
    required String split,
    required int weekIndex,
    required int blockIndex,
    required double readinessScore,
  }) async {
    final payload = {
      'profile_id': profileId,
      'split': split,
      'week_index': weekIndex,
      'block_index': blockIndex,
      'readiness_score': readinessScore,
    };

    final data = await _api.generateWorkout(payload);
    return WorkoutPlanDto.fromJson(data);
  }

  @override
  Future<String> chatCoach({
    required int userId,
    required List<Map<String, String>> messages,
  }) async {
    final payload = {
      'user_id': userId,
      'messages': messages,
    };

    final data = await _api.chatCoach(payload);
    return data['reply'] as String? ?? '';
  }

  @override
  Future<SetLog> logSet({
    required int userId,
    required String exerciseName,
    required String exerciseKey,
    required int reps,
    required double weight,
    double? rpe,
    int? restSeconds,
    String? sessionId,
    String? clientId,
  }) async {
    final payload = SetLogDto.toJson(
      userId: userId,
      exercise: exerciseName,
      exerciseKey: exerciseKey,
      reps: reps,
      weight: weight,
      rpe: rpe,
      restSeconds: restSeconds,
      sessionId: sessionId,
      clientId: clientId,
    );

    final data = await _api.logSet(payload);
    return SetLogDto.fromJson(data);
  }

  @override
  Future<void> deleteSet({
    required int userId,
    required String clientId,
  }) async {
    await _api.deleteSet({
      'user_id': userId,
      'client_id': clientId,
    });
  }

  @override
  Future<List<WorkoutHistorySession>> getWorkoutHistory({
    required int userId,
    int limit = 20,
  }) async {
    final data = await _api.workoutHistory(userId, limit: limit);
    return WorkoutHistoryDto.fromJson(data);
  }

  @override
  Future<ProgressSummary> getProgressSummary({required int userId}) async {
    final data = await _api.progressSummary(userId);
    return ProgressSummaryDto.fromJson(data);
  }

  @override
  Future<ProgressionDecision> adjustProgression({
    required int userId,
    required String exerciseName,
    required String exerciseKey,
    required double lastWeekAvgRpe,
    required int lastWeekVolume,
    required int plateauWeeks,
    required double fatigueScore,
    required double readinessScore,
  }) async {
    final payload = {
      'user_id': userId,
      'exercise': exerciseName,
      'exercise_name': exerciseName,
      'exercise_key': exerciseKey,
      'last_week_avg_rpe': lastWeekAvgRpe,
      'last_week_volume': lastWeekVolume,
      'plateau_weeks': plateauWeeks,
      'fatigue_score': fatigueScore,
      'readiness_score': readinessScore,
    };

    final data = await _api.adjustProgression(payload);
    return ProgressionDecisionDto.fromJson(data);
  }
}
