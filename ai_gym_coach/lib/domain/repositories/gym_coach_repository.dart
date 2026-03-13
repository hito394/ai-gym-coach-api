import '../models/user_profile.dart';
import '../models/workout_plan.dart';
import '../models/set_log.dart';
import '../models/progress_summary.dart';
import '../models/progression_decision.dart';
import '../models/workout_history.dart';

abstract class GymCoachRepository {
  Future<UserProfile> createProfile({
    required int age,
    required double weightKg,
    required double heightCm,
    required String experienceLevel,
    required String goal,
    required int trainingDays,
    required List<String> equipment,
  });

  Future<WorkoutPlan> generateWorkout({
    required int profileId,
    required String split,
    required int weekIndex,
    required int blockIndex,
    required double readinessScore,
  });

  Future<String> chatCoach({
    required int userId,
    required List<Map<String, String>> messages,
  });

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
  });

  Future<void> deleteSet({
    required int userId,
    required String clientId,
  });

  Future<List<WorkoutHistorySession>> getWorkoutHistory({
    required int userId,
    int limit,
  });

  Future<ProgressSummary> getProgressSummary({required int userId});

  Future<ProgressionDecision> adjustProgression({
    required int userId,
    required String exerciseName,
    required String exerciseKey,
    required double lastWeekAvgRpe,
    required int lastWeekVolume,
    required int plateauWeeks,
    required double fatigueScore,
    required double readinessScore,
  });
}
