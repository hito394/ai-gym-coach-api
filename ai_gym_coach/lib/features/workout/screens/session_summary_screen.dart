import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/workout_provider.dart';

class SessionSummaryScreen extends ConsumerWidget {
  const SessionSummaryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(workoutProvider).sessionSummary;

    return Scaffold(
      appBar: AppBar(title: const Text('Session Summary')),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: summary == null
            ? const Center(child: Text('No session summary available.'))
            : ListView(
                children: [
                  _coachHighlightsCard(summary.coachHighlights),
                  const SizedBox(height: 16),
                  _statRow('Total Sets', summary.totalSets.toString()),
                  _statRow(
                      'Total Volume', summary.totalVolume.toStringAsFixed(1)),
                  const SizedBox(height: 16),
                  const Text('Session PRs',
                      style:
                          TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  if (summary.sessionPrs.isEmpty)
                    const Text('No PRs detected')
                  else
                    ...summary.sessionPrs.entries.map((entry) => Text(
                        '${entry.key}: ${entry.value.toStringAsFixed(1)}')),
                  const SizedBox(height: 16),
                  const Text('Next Session Suggestions',
                      style:
                          TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  if (summary.recommendations.isEmpty)
                    const Text('No recommendations available')
                  else
                    ...summary.recommendations.entries
                        .map((entry) => Text('${entry.key}: ${entry.value}')),
                  const SizedBox(height: 20),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () => context.push('/form/camera'),
                          icon: const Icon(Icons.videocam_outlined),
                          label: const Text('Form Check'),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () => context.push('/workout/history'),
                          icon: const Icon(Icons.history),
                          label: const Text('History'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: () => context.push('/chat'),
                      icon: const Icon(Icons.psychology_alt_outlined),
                      label: const Text('Ask AI Coach'),
                    ),
                  ),
                ],
              ),
      ),
    );
  }

  Widget _coachHighlightsCard(List<String> highlights) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF153E2E), Color(0xFF1B2922)],
        ),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'AI Coach Summary',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          if (highlights.isEmpty)
            const Text('No summary generated yet.')
          else
            ...highlights.map(
              (line) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text('• $line'),
              ),
            ),
        ],
      ),
    );
  }

  Widget _statRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: Colors.white70)),
          Text(value, style: const TextStyle(fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }
}
