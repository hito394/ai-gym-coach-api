import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../app/providers.dart';
import '../../../domain/models/workout_plan.dart';
import '../../onboarding/providers/onboarding_provider.dart';
import '../data/workout_repository.dart';
import '../models/session_summary.dart';

class SessionSet {
  final String id;
  final String clientId;
  final String exerciseName;
  final String exerciseKey;
  final int reps;
  final double weight;
  final double? rpe;
  final int? restSeconds;
  final bool synced;
  final String sessionId;

  const SessionSet({
    required this.id,
    required this.clientId,
    required this.exerciseName,
    required this.exerciseKey,
    required this.reps,
    required this.weight,
    this.rpe,
    this.restSeconds,
    this.synced = false,
    required this.sessionId,
  });

  SessionSet copyWith({
    int? reps,
    double? weight,
    double? rpe,
    bool clearRpe = false,
    int? restSeconds,
    bool? synced,
  }) {
    return SessionSet(
      id: id,
      clientId: clientId,
      exerciseName: exerciseName,
      exerciseKey: exerciseKey,
      reps: reps ?? this.reps,
      weight: weight ?? this.weight,
      rpe: clearRpe ? null : (rpe ?? this.rpe),
      restSeconds: restSeconds ?? this.restSeconds,
      synced: synced ?? this.synced,
      sessionId: sessionId,
    );
  }
}

class WorkoutState {
  final WorkoutPlan? plan;
  final bool isLoading;
  final String? error;
  final List<String> recentLogs;
  final bool sessionActive;
  final int activeDayIndex;
  final String sessionId;
  final List<SessionSet> sessionSets;
  final Map<String, SessionSet> lastSetByExercise;
  final SessionSummary? sessionSummary;

  const WorkoutState({
    this.plan,
    this.isLoading = false,
    this.error,
    this.recentLogs = const [],
    this.sessionActive = false,
    this.activeDayIndex = 0,
    this.sessionId = '',
    this.sessionSets = const [],
    this.lastSetByExercise = const {},
    this.sessionSummary,
  });

  WorkoutState copyWith({
    WorkoutPlan? plan,
    bool? isLoading,
    String? error,
    List<String>? recentLogs,
    bool? sessionActive,
    int? activeDayIndex,
    String? sessionId,
    List<SessionSet>? sessionSets,
    Map<String, SessionSet>? lastSetByExercise,
    SessionSummary? sessionSummary,
  }) {
    return WorkoutState(
      plan: plan ?? this.plan,
      isLoading: isLoading ?? this.isLoading,
      error: error,
      recentLogs: recentLogs ?? this.recentLogs,
      sessionActive: sessionActive ?? this.sessionActive,
      activeDayIndex: activeDayIndex ?? this.activeDayIndex,
      sessionId: sessionId ?? this.sessionId,
      sessionSets: sessionSets ?? this.sessionSets,
      lastSetByExercise: lastSetByExercise ?? this.lastSetByExercise,
      sessionSummary: sessionSummary,
    );
  }
}

class WorkoutController extends StateNotifier<WorkoutState> {
  WorkoutController(this._ref) : super(const WorkoutState()) {
    _initialize();
  }

  final Ref _ref;
  Timer? _syncTimer;
  bool _syncInProgress = false;
  int _backoffSeconds = 2;

  WorkoutRepository get _repo => _ref.read(workoutRepositoryProvider);

  Future<void> _initialize() async {
    await _syncPending();
  }

  void startSession({required int dayIndex}) {
    final sessionId = DateTime.now().millisecondsSinceEpoch.toString();
    state = state.copyWith(
      sessionActive: true,
      activeDayIndex: dayIndex,
      sessionId: sessionId,
      sessionSets: [],
      sessionSummary: null,
    );
  }

  Future<void> endSession() async {
    final summary = await _buildSessionSummary();
    state = state.copyWith(sessionActive: false, sessionSummary: summary);
  }

  Future<void> generate({required String split}) async {
    final profile = _ref.read(onboardingProvider).profile;
    if (profile == null) {
      state = state.copyWith(error: 'Complete onboarding first.');
      return;
    }

    state = state.copyWith(isLoading: true, error: null);
    try {
      final repo = _ref.read(gymCoachRepositoryProvider);
      final plan = await repo.generateWorkout(
        profileId: profile.id,
        split: split,
        weekIndex: 1,
        blockIndex: 1,
        readinessScore: 0.7,
      );
      final firstDayIndex = plan.days.isNotEmpty ? plan.days.first.dayIndex : 0;
      state = state.copyWith(
        plan: plan,
        isLoading: false,
        activeDayIndex: firstDayIndex,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> logSet({
    required String exerciseName,
    required String exerciseKey,
    required int reps,
    required double weight,
    double? rpe,
    int? restSeconds,
  }) async {
    final profile = _ref.read(onboardingProvider).profile;
    if (profile == null) {
      state = state.copyWith(error: 'Complete onboarding first.');
      return;
    }

    try {
      final sessionId = state.sessionId.isEmpty
          ? DateTime.now().millisecondsSinceEpoch.toString()
          : state.sessionId;
      final clientId = _repo.generateClientId();
      final pending = await _repo.logSetOnlineOrQueue(
        userId: profile.id,
        exerciseName: exerciseName,
        exerciseKey: exerciseKey,
        reps: reps,
        weight: weight,
        rpe: rpe,
        restSeconds: restSeconds,
        sessionId: sessionId,
        clientId: clientId,
      );
      final localId = clientId;
      final sessionSet = SessionSet(
        id: localId,
        clientId: clientId,
        exerciseName: exerciseName,
        exerciseKey: exerciseKey,
        reps: reps,
        weight: weight,
        rpe: rpe,
        restSeconds: restSeconds,
        sessionId: sessionId,
        synced: !pending,
      );

      final updatedLast = Map<String, SessionSet>.from(state.lastSetByExercise)
        ..[exerciseKey] = sessionSet;

      final log = '$exerciseName • $reps reps • ${weight.toStringAsFixed(1)}kg';
      state = state.copyWith(
        recentLogs: [log, ...state.recentLogs],
        sessionSets: [sessionSet, ...state.sessionSets],
        lastSetByExercise: updatedLast,
      );
      await _syncPending();
    } catch (e) {
      state = state.copyWith(error: e.toString());
    }
  }

  Future<void> repeatLastSet(String exerciseKey, {double? addWeight}) async {
    final last = state.lastSetByExercise[exerciseKey];
    if (last == null) return;
    final weight = addWeight != null ? last.weight + addWeight : last.weight;
    await logSet(
      exerciseName: last.exerciseName,
      exerciseKey: last.exerciseKey,
      reps: last.reps,
      weight: weight,
      rpe: last.rpe,
      restSeconds: last.restSeconds,
    );
  }

  Future<void> removeSessionSet(String id) async {
    final target = state.sessionSets.where((set) => set.id == id);
    if (target.isEmpty) return;

    final removed = target.first;
    final previousSets = state.sessionSets;
    final updatedSets = state.sessionSets.where((set) => set.id != id).toList();
    final updatedLast = _buildLastSetByExercise(updatedSets);

    state = state.copyWith(
      sessionSets: updatedSets,
      lastSetByExercise: updatedLast,
    );

    final profile = _ref.read(onboardingProvider).profile;
    if (profile == null) {
      state = state.copyWith(error: 'Complete onboarding first.');
      return;
    }

    try {
      final pending = await _repo.deleteSetOnlineOrQueue(
        userId: profile.id,
        exerciseName: removed.exerciseName,
        exerciseKey: removed.exerciseKey,
        sessionId: removed.sessionId,
        clientId: removed.clientId,
        restSeconds: removed.restSeconds,
      );
      final syncState = pending ? 'Pending sync' : 'Synced';
      state = state.copyWith(
        recentLogs: [
          'Removed ${removed.exerciseName} • ${removed.reps} reps • ${removed.weight.toStringAsFixed(1)}kg • $syncState',
          ...state.recentLogs,
        ],
      );
      await _syncPending();
    } catch (e) {
      state = state.copyWith(
        sessionSets: previousSets,
        lastSetByExercise: _buildLastSetByExercise(previousSets),
        error: e.toString(),
      );
    }
  }

  Future<void> updateSessionSet({
    required String id,
    required int reps,
    required double weight,
    double? rpe,
  }) async {
    final index = state.sessionSets.indexWhere((set) => set.id == id);
    if (index < 0) return;

    final current = state.sessionSets[index];
    final previousSets = state.sessionSets;
    final updatedSet = current.copyWith(
      reps: reps,
      weight: weight,
      rpe: rpe,
      clearRpe: rpe == null,
      synced: false,
    );

    final updatedSets = [...state.sessionSets]..[index] = updatedSet;
    final updatedLast = _buildLastSetByExercise(updatedSets);

    state = state.copyWith(
      sessionSets: updatedSets,
      lastSetByExercise: updatedLast,
    );

    final profile = _ref.read(onboardingProvider).profile;
    if (profile == null) {
      state = state.copyWith(error: 'Complete onboarding first.');
      return;
    }

    try {
      final pending = await _repo.updateSetOnlineOrQueue(
        userId: profile.id,
        exerciseName: updatedSet.exerciseName,
        exerciseKey: updatedSet.exerciseKey,
        reps: updatedSet.reps,
        weight: updatedSet.weight,
        rpe: updatedSet.rpe,
        restSeconds: updatedSet.restSeconds,
        sessionId: updatedSet.sessionId,
        clientId: updatedSet.clientId,
      );

      final stateIndex = state.sessionSets.indexWhere((set) => set.id == id);
      if (stateIndex >= 0) {
        final normalized = state.sessionSets[stateIndex].copyWith(
          synced: !pending,
        );
        final nextSets = [...state.sessionSets]..[stateIndex] = normalized;
        state = state.copyWith(
          sessionSets: nextSets,
          lastSetByExercise: _buildLastSetByExercise(nextSets),
          recentLogs: [
            'Edited ${normalized.exerciseName} • ${normalized.reps} reps • ${normalized.weight.toStringAsFixed(1)}kg • ${pending ? 'Pending sync' : 'Synced'}',
            ...state.recentLogs,
          ],
        );
      }
      await _syncPending();
    } catch (e) {
      state = state.copyWith(
        sessionSets: previousSets,
        lastSetByExercise: _buildLastSetByExercise(previousSets),
        error: e.toString(),
      );
    }
  }

  Map<String, SessionSet> _buildLastSetByExercise(List<SessionSet> sets) {
    final map = <String, SessionSet>{};
    for (final set in sets) {
      map.putIfAbsent(set.exerciseKey, () => set);
    }
    return map;
  }

  Future<void> _syncPending() async {
    if (_syncInProgress) return;
    _syncInProgress = true;
    try {
      final success = await _repo.syncPending();
      if (success) {
        _backoffSeconds = 2;
        if (state.sessionSets.isNotEmpty) {
          final synced = state.sessionSets
              .map((set) => set.copyWith(synced: true))
              .toList();
          state = state.copyWith(
            sessionSets: synced,
            lastSetByExercise: _buildLastSetByExercise(synced),
          );
        }
      } else {
        _backoffSeconds = (_backoffSeconds * 2).clamp(2, 30);
        _scheduleSync();
      }
    } finally {
      _syncInProgress = false;
    }
  }

  void _scheduleSync() {
    _syncTimer?.cancel();
    _syncTimer = Timer(Duration(seconds: _backoffSeconds), () async {
      await _syncPending();
    });
  }

  @override
  void dispose() {
    _syncTimer?.cancel();
    super.dispose();
  }

  Future<SessionSummary> _buildSessionSummary() async {
    final sets = state.sessionSets;
    final totalSets = sets.length;
    final totalVolume =
        sets.fold<double>(0.0, (sum, item) => sum + (item.reps * item.weight));
    final sessionPrsByKey = <String, double>{};
    final exerciseNameByKey = <String, String>{};
    final recommendations = <String, String>{};

    for (final set in sets) {
      exerciseNameByKey[set.exerciseKey] = set.exerciseName;
      final current = sessionPrsByKey[set.exerciseKey] ?? 0.0;
      if (set.weight > current) {
        sessionPrsByKey[set.exerciseKey] = set.weight;
      }
    }

    final sessionPrs = <String, double>{};
    for (final entry in sessionPrsByKey.entries) {
      final name = exerciseNameByKey[entry.key] ?? entry.key;
      sessionPrs[name] = entry.value;
    }

    final profile = _ref.read(onboardingProvider).profile;
    double? previousVolume;
    if (profile != null) {
      final uniqueKeys = sessionPrsByKey.keys.toList();
      for (final exerciseKey in uniqueKeys) {
        final exerciseName = exerciseNameByKey[exerciseKey] ?? exerciseKey;
        try {
          final decision =
              await _ref.read(gymCoachRepositoryProvider).adjustProgression(
                    userId: profile.id,
                    exerciseName: exerciseName,
                    exerciseKey: exerciseKey,
                    lastWeekAvgRpe: 7.5,
                    lastWeekVolume: totalSets,
                    plateauWeeks: 0,
                    fatigueScore: 0.3,
                    readinessScore: 0.7,
                  );
          final weightDelta = decision.weightDelta;
          final sign = weightDelta >= 0 ? '+' : '';
          recommendations[exerciseName] =
              '${decision.message} ($sign${weightDelta.toStringAsFixed(1)}kg, ${decision.volumeDeltaSets} sets)';
        } catch (_) {
          recommendations[exerciseName] = 'Sync to get suggestions';
        }
      }

      try {
        final history =
            await _ref.read(gymCoachRepositoryProvider).getWorkoutHistory(
                  userId: profile.id,
                  limit: 3,
                );
        if (history.isNotEmpty) {
          if (history.first.sessionId == state.sessionId &&
              history.length > 1) {
            previousVolume = history[1].totalVolume;
          } else {
            previousVolume = history.first.totalVolume;
          }
        }
      } catch (_) {
        previousVolume = null;
      }
    } else {
      recommendations['session'] = 'Sync to get suggestions';
    }

    final coachHighlights = await _buildCoachHighlights(
      totalSets: totalSets,
      totalVolume: totalVolume,
      previousVolume: previousVolume,
      sessionPrs: sessionPrs,
      recommendations: recommendations,
    );

    return SessionSummary(
      sessionId: state.sessionId,
      totalSets: totalSets,
      totalVolume: totalVolume,
      sessionPrs: sessionPrs,
      recommendations: recommendations,
      coachHighlights: coachHighlights,
    );
  }

  Future<List<String>> _buildCoachHighlights({
    required int totalSets,
    required double totalVolume,
    required double? previousVolume,
    required Map<String, double> sessionPrs,
    required Map<String, String> recommendations,
  }) async {
    final fallback = _fallbackCoachHighlights(
      totalSets: totalSets,
      totalVolume: totalVolume,
      previousVolume: previousVolume,
      sessionPrs: sessionPrs,
      recommendations: recommendations,
    );

    final profile = _ref.read(onboardingProvider).profile;
    if (profile == null) {
      return fallback;
    }

    try {
      final recommendationText = recommendations.entries
          .take(3)
          .map((entry) => '- ${entry.key}: ${entry.value}')
          .join('\n');
      final prompt = [
        'Session stats:',
        '- Total sets: $totalSets',
        '- Total volume: ${totalVolume.toStringAsFixed(1)} kg',
        if (previousVolume != null)
          '- Previous volume: ${previousVolume.toStringAsFixed(1)} kg',
        if (sessionPrs.isNotEmpty)
          '- Session PRs: ${sessionPrs.entries.map((entry) => '${entry.key} ${entry.value.toStringAsFixed(1)}kg').join(', ')}',
        if (recommendationText.isNotEmpty)
          'Progression suggestions:\n$recommendationText',
        '',
        'Give exactly 3 short, actionable bullet points for next workout. Each bullet under 80 characters.',
      ].join('\n');

      final reply = await _ref.read(gymCoachRepositoryProvider).chatCoach(
        userId: profile.id,
        messages: [
          {
            'role': 'system',
            'content':
                'You are a concise strength coach. Respond with short actionable bullets only.',
          },
          {'role': 'user', 'content': prompt},
        ],
      );

      final parsed = _parseCoachHighlights(reply);
      if (parsed.isEmpty) {
        return fallback;
      }

      final merged = <String>[];
      final seen = <String>{};
      for (final item in [...parsed, ...fallback]) {
        final normalized = item.trim();
        if (normalized.isEmpty) continue;
        final key = normalized.toLowerCase();
        if (seen.add(key)) {
          merged.add(normalized);
        }
        if (merged.length >= 3) break;
      }
      return merged;
    } catch (_) {
      return fallback;
    }
  }

  List<String> _fallbackCoachHighlights({
    required int totalSets,
    required double totalVolume,
    required double? previousVolume,
    required Map<String, double> sessionPrs,
    required Map<String, String> recommendations,
  }) {
    final result = <String>[];

    if (previousVolume != null && previousVolume > 0) {
      final deltaPct = ((totalVolume - previousVolume) / previousVolume) * 100;
      final direction = deltaPct >= 0 ? 'up' : 'down';
      result.add(
        'Volume $direction ${deltaPct.abs().toStringAsFixed(1)}% vs previous workout.',
      );
    } else {
      result.add(
          'Logged $totalSets sets and ${totalVolume.toStringAsFixed(0)} kg total volume.');
    }

    if (sessionPrs.isNotEmpty) {
      final best = sessionPrs.entries.first;
      result.add(
          'Top PR: ${best.key} reached ${best.value.toStringAsFixed(1)} kg.');
    } else {
      result.add('Keep technique sharp and add 1 rep before adding more load.');
    }

    final suggestion = recommendations.entries
        .map((entry) => '${entry.key}: ${entry.value}')
        .firstWhere(
          (text) => text.trim().isNotEmpty,
          orElse: () =>
              'Start next session with your main compound movement first.',
        );
    result.add(suggestion);

    return result.take(3).toList();
  }

  List<String> _parseCoachHighlights(String raw) {
    final lines = raw
        .split(RegExp(r'[\r\n]+'))
        .map((line) =>
            line.replaceFirst(RegExp(r'^\s*[-*0-9.)]+\s*'), '').trim())
        .where((line) => line.isNotEmpty)
        .toList();
    if (lines.isEmpty) {
      return const [];
    }
    return lines.take(3).toList();
  }
}

final workoutProvider =
    StateNotifierProvider<WorkoutController, WorkoutState>((ref) {
  return WorkoutController(ref);
});

final workoutRepositoryProvider = Provider<WorkoutRepository>((ref) {
  return WorkoutRepository(
    api: ref.watch(gymCoachRepositoryProvider),
    cache: ref.watch(sessionCacheProvider),
  );
});
