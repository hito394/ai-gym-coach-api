import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../domain/models/progress_summary.dart';
import '../../onboarding/providers/onboarding_provider.dart';
import '../../workout/providers/workout_history_provider.dart';
import '../providers/dashboard_provider.dart';

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  int _selectedRangeWeeks = 8;

  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(dashboardProvider.notifier).load());
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(onboardingProvider).profile;
    final dashboardState = ref.watch(dashboardProvider);
    final summary = dashboardState.summary;
    final historyAsync = ref.watch(workoutHistoryProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Today'),
        actions: [
          IconButton(
            onPressed: () => context.push('/chat'),
            icon: const Icon(Icons.chat_bubble_outline),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(dashboardProvider.notifier).load();
          ref.invalidate(workoutHistoryProvider);
          await ref.read(workoutHistoryProvider.future);
        },
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
          children: [
            Text(
              'Hi',
              style: Theme.of(context)
                  .textTheme
                  .headlineMedium
                  ?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 4),
            Text(
              'Goal: ${profile?.goal ?? 'Build strength'}',
              style: Theme.of(context)
                  .textTheme
                  .bodyLarge
                  ?.copyWith(color: Colors.white70),
            ),
            const SizedBox(height: 16),
            _HeroPanel(summary: summary),
            const SizedBox(height: 16),
            historyAsync.when(
              data: (sessions) => Row(
                children: [
                  Expanded(child: _LastWorkoutCard(sessions: sessions)),
                  const SizedBox(width: 12),
                  Expanded(child: _StreakCard(sessions: sessions)),
                ],
              ),
              loading: () => const Row(
                children: [
                  Expanded(child: _LoadingCard()),
                  SizedBox(width: 12),
                  Expanded(child: _LoadingCard()),
                ],
              ),
              error: (_, __) => const Row(
                children: [
                  Expanded(child: _FallbackInfoCard(title: 'Last Workout')),
                  SizedBox(width: 12),
                  Expanded(child: _FallbackInfoCard(title: 'Current Streak')),
                ],
              ),
            ),
            const SizedBox(height: 16),
            _QuickActionsRow(),
            const SizedBox(height: 16),
            _SparklineCard(summary: summary),
            const SizedBox(height: 16),
            _ProgressSection(
              summary: summary,
              selectedRangeWeeks: _selectedRangeWeeks,
              onRangeChanged: (weeks) {
                setState(() => _selectedRangeWeeks = weeks);
              },
            ),
            if (dashboardState.isLoading) ...[
              const SizedBox(height: 16),
              const Center(child: CircularProgressIndicator()),
            ],
            if (dashboardState.error != null) ...[
              const SizedBox(height: 16),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Colors.red.withAlpha(18),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  dashboardState.error!,
                  style: const TextStyle(color: Colors.redAccent),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _HeroPanel extends StatelessWidget {
  const _HeroPanel({required this.summary});

  final ProgressSummary? summary;

  @override
  Widget build(BuildContext context) {
    final score = summary?.progressScore ?? 0.0;
    final insight = (summary?.insights.isNotEmpty ?? false)
        ? summary!.insights.first
        : 'Log today to keep momentum moving.';

    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0D3B2C), Color(0xFF13241E)],
        ),
        borderRadius: BorderRadius.circular(28),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Progress Score',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(color: Colors.white70),
          ),
          const SizedBox(height: 6),
          Text(
            score == 0.0 ? '--' : score.toStringAsFixed(1),
            style: Theme.of(context).textTheme.displaySmall?.copyWith(
                  fontWeight: FontWeight.w800,
                  height: 1,
                ),
          ),
          const SizedBox(height: 10),
          Text(
            insight,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context)
                .textTheme
                .bodyLarge
                ?.copyWith(color: Colors.white70),
          ),
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () => context.go('/workout'),
              icon: const Icon(Icons.play_arrow_rounded),
              label: const Text('Quick Start Workout'),
            ),
          ),
        ],
      ),
    );
  }
}

class _LastWorkoutCard extends StatelessWidget {
  const _LastWorkoutCard({required this.sessions});

  final List<dynamic> sessions;

  @override
  Widget build(BuildContext context) {
    if (sessions.isEmpty) {
      return const _FallbackInfoCard(title: 'Last Workout');
    }

    final session = sessions.first;
    final keySets = session.entries.take(2).map<String>((entry) {
      return '${entry.exercise} ${entry.weight.toStringAsFixed(0)} x ${entry.reps}';
    }).join('  •  ');

    return _MetricCard(
      title: 'Last Workout',
      value: keySets.isEmpty ? '${session.totalSets} sets' : keySets,
      subtitle: '${session.totalVolume.toStringAsFixed(0)} kg total volume',
    );
  }
}

class _StreakCard extends StatelessWidget {
  const _StreakCard({required this.sessions});

  final List<dynamic> sessions;

  @override
  Widget build(BuildContext context) {
    final streak = _calculateStreak(sessions);
    return _MetricCard(
      title: 'Current Streak',
      value: '$streak days',
      subtitle: streak > 0 ? 'Keep it alive today' : 'Start a new streak',
    );
  }

  int _calculateStreak(List<dynamic> sessions) {
    if (sessions.isEmpty) return 0;

    final uniqueDays = <DateTime>[];
    for (final session in sessions) {
      final local = session.performedAt.toLocal();
      final day = DateTime(local.year, local.month, local.day);
      if (uniqueDays.isEmpty || uniqueDays.last != day) {
        uniqueDays.add(day);
      }
    }

    if (uniqueDays.isEmpty) return 0;

    var streak = 1;
    for (var index = 1; index < uniqueDays.length; index++) {
      final difference =
          uniqueDays[index - 1].difference(uniqueDays[index]).inDays;
      if (difference == 1) {
        streak += 1;
      } else {
        break;
      }
    }
    return streak;
  }
}

class _QuickActionsRow extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Quick Actions',
          style: Theme.of(context)
              .textTheme
              .titleMedium
              ?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: _ActionTile(
                label: 'Form Check',
                icon: Icons.videocam_rounded,
                onTap: () => context.push('/form/camera'),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _ActionTile(
                label: 'History',
                icon: Icons.history_rounded,
                onTap: () => context.push('/workout/history'),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _ActionTile(
                label: 'Coach',
                icon: Icons.psychology_alt_outlined,
                onTap: () => context.push('/chat'),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _SparklineCard extends StatelessWidget {
  const _SparklineCard({required this.summary});

  final ProgressSummary? summary;

  @override
  Widget build(BuildContext context) {
    final points = summary?.weeklyVolumePoints ?? const <TrendPoint>[];
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Weekly Volume',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 6),
          Text(
            'Your trend at a glance',
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(color: Colors.white70),
          ),
          const SizedBox(height: 14),
          SizedBox(
            height: 80,
            child: points.isEmpty
                ? const Center(child: Text('No trend data yet'))
                : LineChart(
                    LineChartData(
                      gridData: const FlGridData(show: false),
                      borderData: FlBorderData(show: false),
                      titlesData: const FlTitlesData(show: false),
                      lineTouchData: const LineTouchData(enabled: false),
                      minX: 0,
                      maxX: (points.length - 1).toDouble(),
                      lineBarsData: [
                        LineChartBarData(
                          spots: [
                            for (var i = 0; i < points.length; i++)
                              FlSpot(i.toDouble(), points[i].value),
                          ],
                          isCurved: true,
                          dotData: const FlDotData(show: false),
                          barWidth: 3,
                          color: Theme.of(context).colorScheme.primary,
                          belowBarData: BarAreaData(
                            show: true,
                            color: Theme.of(context)
                                .colorScheme
                                .primary
                                .withAlpha(30),
                          ),
                        ),
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _ProgressSection extends StatelessWidget {
  const _ProgressSection({
    required this.summary,
    required this.selectedRangeWeeks,
    required this.onRangeChanged,
  });

  final ProgressSummary? summary;
  final int selectedRangeWeeks;
  final ValueChanged<int> onRangeChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Progress',
          style: Theme.of(context)
              .textTheme
              .titleMedium
              ?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 10),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final weeks in [4, 8, 12])
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ChoiceChip(
                    label: Text('${weeks}w'),
                    selected: selectedRangeWeeks == weeks,
                    onSelected: (_) => onRangeChanged(weeks),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        _TrendCard(
          title: 'Weight Progression',
          points: _takeRange(summary?.exerciseWeightPoints, selectedRangeWeeks),
        ),
        const SizedBox(height: 12),
        _TrendCard(
          title: 'Estimated 1RM',
          points: _takeRange(summary?.oneRmPoints, selectedRangeWeeks),
        ),
        const SizedBox(height: 12),
        _TrendCard(
          title: 'Weekly Volume',
          points: _takeRange(summary?.weeklyVolumePoints, selectedRangeWeeks),
        ),
        const SizedBox(height: 12),
        _TrendCard(
          title: 'Workout Consistency',
          points:
              _takeRange(summary?.workoutFrequencyPoints, selectedRangeWeeks),
        ),
      ],
    );
  }

  List<TrendPoint> _takeRange(List<TrendPoint>? points, int range) {
    if (points == null || points.isEmpty) return const [];
    if (points.length <= range) return points;
    return points.sublist(points.length - range);
  }
}

class _TrendCard extends StatelessWidget {
  const _TrendCard({required this.title, required this.points});

  final String title;
  final List<TrendPoint> points;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(22),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 10),
          SizedBox(
            height: 110,
            child: points.isEmpty
                ? const Center(child: Text('Not enough data yet'))
                : LineChart(
                    LineChartData(
                      gridData: FlGridData(
                        show: true,
                        horizontalInterval: _interval(points),
                        drawVerticalLine: false,
                        getDrawingHorizontalLine: (_) => const FlLine(
                          color: Colors.white10,
                          strokeWidth: 1,
                        ),
                      ),
                      borderData: FlBorderData(show: false),
                      titlesData: const FlTitlesData(
                        topTitles: AxisTitles(),
                        rightTitles: AxisTitles(),
                        leftTitles: AxisTitles(),
                        bottomTitles: AxisTitles(),
                      ),
                      lineTouchData: LineTouchData(
                        touchTooltipData: LineTouchTooltipData(
                          getTooltipColor: (_) => const Color(0xFF1D1F22),
                        ),
                      ),
                      minX: 0,
                      maxX: (points.length - 1).toDouble(),
                      lineBarsData: [
                        LineChartBarData(
                          spots: [
                            for (var index = 0; index < points.length; index++)
                              FlSpot(index.toDouble(), points[index].value),
                          ],
                          isCurved: true,
                          color: Theme.of(context).colorScheme.primary,
                          barWidth: 3,
                          dotData: const FlDotData(show: false),
                        ),
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  double _interval(List<TrendPoint> values) {
    final maxValue =
        values.map((point) => point.value).reduce((a, b) => a > b ? a : b);
    return maxValue <= 0 ? 1 : (maxValue / 3).clamp(1, maxValue);
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.title,
    required this.value,
    required this.subtitle,
  });

  final String title;
  final String value;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 8),
          Text(
            value,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            subtitle,
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: Colors.white70),
          ),
        ],
      ),
    );
  }
}

class _ActionTile extends StatelessWidget {
  const _ActionTile({
    required this.label,
    required this.icon,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Ink(
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Column(
          children: [
            Icon(icon),
            const SizedBox(height: 8),
            Text(label, textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

class _LoadingCard extends StatelessWidget {
  const _LoadingCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 118,
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(24),
      ),
      child: const Center(child: CircularProgressIndicator()),
    );
  }
}

class _FallbackInfoCard extends StatelessWidget {
  const _FallbackInfoCard({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return _MetricCard(
      title: title,
      value: '--',
      subtitle: 'No data yet',
    );
  }
}
