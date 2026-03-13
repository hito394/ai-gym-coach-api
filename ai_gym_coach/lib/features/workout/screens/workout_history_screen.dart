import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../domain/models/workout_history.dart';
import '../providers/workout_history_provider.dart';

class WorkoutHistoryScreen extends ConsumerWidget {
  const WorkoutHistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final historyAsync = ref.watch(workoutHistoryProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Workout History')),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(workoutHistoryProvider);
          await ref.read(workoutHistoryProvider.future);
        },
        child: historyAsync.when(
          data: (sessions) {
            if (sessions.isEmpty) {
              return ListView(
                children: const [
                  SizedBox(height: 140),
                  Center(
                    child: Text('No workout history yet. Log a few sessions.'),
                  ),
                ],
              );
            }

            return ListView.separated(
              padding: const EdgeInsets.all(16),
              itemBuilder: (context, index) => _TimelineCard(
                session: sessions[index],
                isLast: index == sessions.length - 1,
              ),
              separatorBuilder: (_, __) => const SizedBox(height: 12),
              itemCount: sessions.length,
            );
          },
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) => ListView(
            children: [
              const SizedBox(height: 120),
              Center(child: Text('Failed to load history: $error')),
            ],
          ),
        ),
      ),
    );
  }
}

class _TimelineCard extends StatelessWidget {
  const _TimelineCard({required this.session, required this.isLast});

  final WorkoutHistorySession session;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    final local = session.performedAt.toLocal();
    final dateLabel = _formatDate(local);
    final keySetSummary = session.entries.take(2).map((entry) {
      return '${entry.exercise} ${entry.weight.toStringAsFixed(0)} x ${entry.reps}';
    }).join('  •  ');

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 24,
          child: Column(
            children: [
              Container(
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primary,
                  shape: BoxShape.circle,
                ),
              ),
              if (!isLast)
                Container(
                  width: 2,
                  height: 140,
                  color: Colors.white12,
                ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Card(
            child: ExpansionTile(
              tilePadding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              title: Text(
                dateLabel,
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              subtitle: Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      keySetSummary.isEmpty ? 'Session logged' : keySetSummary,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${session.totalSets} sets  •  ${session.totalVolume.toStringAsFixed(1)} kg volume',
                      style: const TextStyle(color: Colors.white70),
                    ),
                  ],
                ),
              ),
              children: [
                for (final entry in session.entries)
                  Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Text(
                            '${entry.exercise}  ${entry.reps} x ${entry.weight.toStringAsFixed(1)}kg',
                          ),
                        ),
                        Text(
                          _detailLabel(entry),
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  String _detailLabel(WorkoutHistorySetEntry entry) {
    final rpe = entry.rpe == null ? '-' : entry.rpe!.toStringAsFixed(1);
    final rest = entry.restSeconds == null ? '-' : '${entry.restSeconds}s';
    return 'RPE $rpe  Rest $rest';
  }

  String _formatDate(DateTime value) {
    const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const months = [
      'Jan',
      'Feb',
      'Mar',
      'Apr',
      'May',
      'Jun',
      'Jul',
      'Aug',
      'Sep',
      'Oct',
      'Nov',
      'Dec',
    ];

    return '${weekdays[value.weekday - 1]}, ${months[value.month - 1]} ${value.day}';
  }
}
