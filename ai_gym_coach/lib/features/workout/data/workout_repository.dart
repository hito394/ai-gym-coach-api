import 'dart:math';
import '../../../core/network/api_exception.dart';
import '../../../data/local/session_cache.dart';
import '../../../data/local/pending_set_log.dart';
import '../../../domain/models/set_log.dart';
import '../../../domain/repositories/gym_coach_repository.dart';

class WorkoutRepository {
  WorkoutRepository({required this.api, required this.cache});

  final GymCoachRepository api;
  final SessionCache cache;

  String generateClientId() {
    final rand = Random();
    String hex(int length) {
      return List.generate(length, (_) => rand.nextInt(16).toRadixString(16))
          .join();
    }

    return '${hex(8)}-${hex(4)}-${hex(4)}-${hex(4)}-${hex(12)}';
  }

  String _pendingKey({required String operation, required String clientId}) {
    return '${operation.toLowerCase()}:$clientId';
  }

  Future<SetLog?> logSetOnline({
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
    return api.logSet(
      userId: userId,
      exerciseName: exerciseName,
      exerciseKey: exerciseKey,
      reps: reps,
      weight: weight,
      rpe: rpe,
      restSeconds: restSeconds,
      sessionId: sessionId,
      clientId: clientId,
    );
  }

  Future<PendingSetLog> queuePending({
    required int userId,
    required String exerciseName,
    required String exerciseKey,
    required int reps,
    required double weight,
    double? rpe,
    int? restSeconds,
    required String sessionId,
    required String clientId,
    String operation = 'create',
  }) async {
    final op = operation.trim().toLowerCase();
    final id = _pendingKey(operation: op, clientId: clientId);
    final log = PendingSetLog(
      uuid: id,
      clientId: clientId,
      userId: userId,
      sessionId: sessionId,
      exerciseName: exerciseName,
      exerciseKeyRaw: exerciseKey,
      reps: reps,
      weight: weight,
      rpe: rpe,
      restSeconds: restSeconds,
      createdAt: DateTime.now(),
      status: 'pending',
      operation: op,
    );
    await cache.addPending(log);
    return log;
  }

  Future<void> deleteSetOnline({
    required int userId,
    required String clientId,
  }) async {
    await api.deleteSet(userId: userId, clientId: clientId);
  }

  Future<bool> logSetOnlineOrQueue({
    required int userId,
    required String exerciseName,
    required String exerciseKey,
    required int reps,
    required double weight,
    double? rpe,
    int? restSeconds,
    required String sessionId,
    required String clientId,
  }) async {
    try {
      await logSetOnline(
        userId: userId,
        exerciseName: exerciseName,
        exerciseKey: exerciseKey,
        reps: reps,
        weight: weight,
        rpe: rpe,
        restSeconds: restSeconds,
        sessionId: sessionId,
        clientId: clientId,
      );
      return false;
    } on ApiException catch (e) {
      if (e.statusCode == null) {
        await queuePending(
          userId: userId,
          exerciseName: exerciseName,
          exerciseKey: exerciseKey,
          reps: reps,
          weight: weight,
          rpe: rpe,
          restSeconds: restSeconds,
          sessionId: sessionId,
          clientId: clientId,
          operation: 'create',
        );
        return true;
      }
      rethrow;
    }
  }

  Future<bool> updateSetOnlineOrQueue({
    required int userId,
    required String exerciseName,
    required String exerciseKey,
    required int reps,
    required double weight,
    double? rpe,
    int? restSeconds,
    required String sessionId,
    required String clientId,
  }) async {
    try {
      await logSetOnline(
        userId: userId,
        exerciseName: exerciseName,
        exerciseKey: exerciseKey,
        reps: reps,
        weight: weight,
        rpe: rpe,
        restSeconds: restSeconds,
        sessionId: sessionId,
        clientId: clientId,
      );
      return false;
    } on ApiException catch (e) {
      if (e.statusCode == null) {
        await queuePending(
          userId: userId,
          exerciseName: exerciseName,
          exerciseKey: exerciseKey,
          reps: reps,
          weight: weight,
          rpe: rpe,
          restSeconds: restSeconds,
          sessionId: sessionId,
          clientId: clientId,
          operation: 'update',
        );
        return true;
      }
      rethrow;
    }
  }

  Future<bool> deleteSetOnlineOrQueue({
    required int userId,
    required String exerciseName,
    required String exerciseKey,
    required String sessionId,
    required String clientId,
    int? restSeconds,
  }) async {
    try {
      await deleteSetOnline(userId: userId, clientId: clientId);
      return false;
    } on ApiException catch (e) {
      if (e.statusCode == null) {
        await queuePending(
          userId: userId,
          exerciseName: exerciseName,
          exerciseKey: exerciseKey,
          reps: 0,
          weight: 0,
          rpe: null,
          restSeconds: restSeconds,
          sessionId: sessionId,
          clientId: clientId,
          operation: 'delete',
        );
        return true;
      }
      rethrow;
    }
  }

  Future<int> pendingCount() => cache.pendingCount();

  Future<List<PendingSetLog>> pendingSets() => cache.pendingSets();

  Future<bool> syncPending() async {
    final pending = await cache.pendingSets();
    pending.sort((a, b) => a.createdAt.compareTo(b.createdAt));
    for (final log in pending) {
      final operation = log.normalizedOperation;
      try {
        if (operation == 'delete') {
          await deleteSetOnline(
            userId: log.userId,
            clientId: log.targetClientId,
          );
        } else {
          await api.logSet(
            userId: log.userId,
            exerciseName: log.exerciseName,
            exerciseKey: log.exerciseKey,
            reps: log.reps,
            weight: log.weight,
            rpe: log.rpe,
            restSeconds: log.restSeconds,
            sessionId: log.sessionId,
            clientId: log.targetClientId,
          );
        }
        await cache.remove(log.uuid);
      } on ApiException catch (e) {
        if (e.statusCode == null) {
          return false;
        }
        final status = e.statusCode!;
        final shouldDrop = status >= 400 && status < 500 && status != 429;
        if (shouldDrop) {
          await cache.remove(log.uuid);
          continue;
        }
        return false;
      } catch (_) {
        return false;
      }
    }
    return true;
  }
}
