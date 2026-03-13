import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:hive_flutter/hive_flutter.dart';
import '../../../domain/models/workout_plan.dart';
import '../../../app/providers.dart';
import '../providers/workout_provider.dart';

class WorkoutScreen extends ConsumerStatefulWidget {
  const WorkoutScreen({super.key});

  @override
  ConsumerState<WorkoutScreen> createState() => _WorkoutScreenState();
}

class _WorkoutScreenState extends ConsumerState<WorkoutScreen> {
  static const _uiBoxName = 'workout_ui';
  static const _customMenusKey = 'custom_menu_names';
  static const _defaultManualMenus = <String>[
    'Bench Press',
    'Squat',
    'Deadlift',
    'Overhead Press',
    'Barbell Row',
    'Lat Pulldown',
    'Leg Press',
  ];

  String _split = 'ppl';
  int _activeExercisePosition = 0;
  Timer? _restTimer;
  int _restSeconds = 0;
  int _customRestSeconds = 90;
  bool _useCustomRestForLog = true;
  final Map<String, int> _repsByExercise = {};
  final Map<String, double> _weightByExercise = {};
  final Map<String, double?> _rpeByExercise = {};
  final TextEditingController _customMenuController = TextEditingController();
  List<String> _customMenus = const [];
  String? _selectedManualMenu;
  int _manualReps = 8;
  double _manualWeight = 0.0;
  double? _manualRpe = 8.0;
  String _logSort = 'newest';
  String _logFilter = 'all';

  @override
  void initState() {
    super.initState();
    unawaited(_loadCustomMenus());
  }

  @override
  void dispose() {
    _restTimer?.cancel();
    _customMenuController.dispose();
    super.dispose();
  }

  void _startRestTimer(int seconds) {
    final safeSeconds = seconds.clamp(5, 900);
    _restTimer?.cancel();
    setState(() => _restSeconds = safeSeconds);
    _restTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (_restSeconds <= 1) {
        timer.cancel();
        setState(() => _restSeconds = 0);
        return;
      }
      setState(() => _restSeconds -= 1);
    });
  }

  int _suggestedReps(String repRange) {
    final parts = repRange.split('-');
    if (parts.length != 2) return 8;
    final low = int.tryParse(parts[0].trim()) ?? 8;
    final high = int.tryParse(parts[1].trim()) ?? low;
    return ((low + high) / 2).round();
  }

  int _restForExercise(ExercisePrescription exercise) {
    return _useCustomRestForLog ? _customRestSeconds : exercise.restSeconds;
  }

  void _adjustWeight(String key, double current, double delta) {
    setState(() {
      final next = (current + delta).clamp(0.0, 999.0);
      _weightByExercise[key] = double.parse(next.toStringAsFixed(2));
    });
  }

  void _adjustReps(String key, int current, int delta) {
    setState(() {
      final next = (current + delta).clamp(1, 99);
      _repsByExercise[key] = next;
    });
  }

  void _logQuickSet({
    required WorkoutState state,
    required ExercisePrescription exercise,
    required int reps,
    required double weight,
    required double? rpe,
  }) {
    if (weight <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Set weight once, then log in 1 tap.')),
      );
      return;
    }

    HapticFeedback.mediumImpact();

    ref.read(workoutProvider.notifier).logSet(
          exerciseName: exercise.name,
          exerciseKey: exercise.exerciseKey,
          reps: reps,
          weight: weight,
          rpe: rpe,
          restSeconds: _restForExercise(exercise),
        );
    _startRestTimer(_restForExercise(exercise));

    final day =
        state.plan!.days.firstWhere((d) => d.dayIndex == state.activeDayIndex);
    if (_activeExercisePosition < day.exercises.length - 1) {
      setState(() => _activeExercisePosition += 1);
    }
  }

  List<String> get _allManualMenus {
    final seen = <String>{};
    final merged = <String>[];
    for (final item in [..._defaultManualMenus, ..._customMenus]) {
      final menu = item.trim();
      if (menu.isEmpty) continue;
      final key = menu.toLowerCase();
      if (seen.add(key)) {
        merged.add(menu);
      }
    }
    return merged;
  }

  Future<void> _loadCustomMenus() async {
    final box = await Hive.openBox(_uiBoxName);
    final raw = box.get(_customMenusKey, defaultValue: const <dynamic>[]);
    final custom = raw is List ? raw.whereType<String>().toList() : <String>[];
    if (!mounted) return;
    setState(() {
      _customMenus = custom;
      _selectedManualMenu ??=
          _allManualMenus.isNotEmpty ? _allManualMenus.first : null;
    });
  }

  Future<void> _saveCustomMenus() async {
    final box = await Hive.openBox(_uiBoxName);
    await box.put(_customMenusKey, _customMenus);
  }

  bool _addCustomMenu(String rawName) {
    final name = rawName.trim();
    if (name.isEmpty) return false;
    final existing = _allManualMenus
        .where((menu) => menu.toLowerCase() == name.toLowerCase());
    if (existing.isNotEmpty) {
      setState(() => _selectedManualMenu = existing.first);
      return true;
    }

    setState(() {
      _customMenus = [name, ..._customMenus];
      _selectedManualMenu = name;
    });
    unawaited(_saveCustomMenus());
    return true;
  }

  void _removeCustomMenu(String name) {
    setState(() {
      _customMenus = _customMenus
          .where((menu) => menu.toLowerCase() != name.toLowerCase())
          .toList();
      if (_selectedManualMenu?.toLowerCase() == name.toLowerCase()) {
        _selectedManualMenu =
            _allManualMenus.isNotEmpty ? _allManualMenus.first : null;
      }
    });
    unawaited(_saveCustomMenus());
  }

  String _manualExerciseKey(String menuName) {
    final slug = menuName
        .trim()
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
        .replaceAll(RegExp(r'^_+|_+$'), '');
    if (slug.isEmpty) {
      return 'manual_${menuName.hashCode.abs()}';
    }
    return 'manual_$slug';
  }

  void _onManualMenuSelected(WorkoutState state, String menuName) {
    final key = _manualExerciseKey(menuName);
    final last = state.lastSetByExercise[key];
    setState(() {
      _selectedManualMenu = menuName;
      if (last != null) {
        _manualReps = last.reps;
        _manualWeight = last.weight;
        _manualRpe = last.rpe;
      }
    });
  }

  void _logManualSet(WorkoutState state, String menuName) {
    if (!state.sessionActive) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Start session first, then log sets.')),
      );
      return;
    }
    if (_manualWeight <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter weight before logging.')),
      );
      return;
    }

    final key = _manualExerciseKey(menuName);
    HapticFeedback.mediumImpact();
    ref.read(workoutProvider.notifier).logSet(
          exerciseName: menuName,
          exerciseKey: key,
          reps: _manualReps,
          weight: _manualWeight,
          rpe: _manualRpe,
          restSeconds: _customRestSeconds,
        );
    _startRestTimer(_customRestSeconds);
  }

  Future<void> _showAddMenuDialog() async {
    _customMenuController.clear();
    final added = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Add Custom Menu'),
        content: TextField(
          controller: _customMenuController,
          textInputAction: TextInputAction.done,
          decoration: const InputDecoration(
            labelText: 'Exercise name',
            hintText: 'e.g. Incline Dumbbell Press',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final ok = _addCustomMenu(_customMenuController.text);
              Navigator.pop(context, ok);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );

    if (added == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Custom menu saved.')),
      );
    }
  }

  Future<void> _showEditSetDialog(SessionSet set) async {
    final repsController = TextEditingController(text: set.reps.toString());
    final weightController =
        TextEditingController(text: set.weight.toStringAsFixed(1));
    final rpeController = TextEditingController(
      text: set.rpe == null ? '' : set.rpe!.toStringAsFixed(1),
    );

    final saved = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Edit ${set.exerciseName}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: repsController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Reps'),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: weightController,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Weight (kg)'),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: rpeController,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(
                labelText: 'RPE (optional)',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () async {
              final reps = int.tryParse(repsController.text.trim());
              final weight = double.tryParse(weightController.text.trim());
              final rpeText = rpeController.text.trim();
              final rpe = rpeText.isEmpty ? null : double.tryParse(rpeText);
              if (reps == null || reps < 1 || weight == null || weight <= 0) {
                return;
              }
              await ref.read(workoutProvider.notifier).updateSessionSet(
                    id: set.id,
                    reps: reps,
                    weight: weight,
                    rpe: rpe,
                  );
              if (!context.mounted) return;
              Navigator.pop(context, true);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );

    repsController.dispose();
    weightController.dispose();
    rpeController.dispose();

    if (saved == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Log updated.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(workoutProvider);
    final pendingCountAsync = ref.watch(pendingUploadsCountProvider);
    final quickLog = _resolveQuickLogContext(state);
    final manualMenus = _allManualMenus;
    final selectedManualMenu =
        manualMenus.contains(_selectedManualMenu) ? _selectedManualMenu : null;

    return Scaffold(
      appBar: AppBar(title: const Text('Workout')),
      bottomNavigationBar: quickLog == null
          ? null
          : _buildStickyLogBar(state: state, quickLog: quickLog),
      body: ListView(
        padding: EdgeInsets.fromLTRB(20, 20, 20, quickLog == null ? 20 : 120),
        children: [
          DropdownButtonFormField<String>(
            initialValue: _split,
            decoration: const InputDecoration(labelText: 'Split'),
            items: const [
              DropdownMenuItem(value: 'ppl', child: Text('Push / Pull / Legs')),
              DropdownMenuItem(
                  value: 'upper_lower', child: Text('Upper / Lower')),
              DropdownMenuItem(value: 'full_body', child: Text('Full Body')),
            ],
            onChanged: (value) => setState(() => _split = value ?? 'ppl'),
          ),
          const SizedBox(height: 12),
          ElevatedButton(
            onPressed: state.isLoading
                ? null
                : () =>
                    ref.read(workoutProvider.notifier).generate(split: _split),
            child: state.isLoading
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Generate Plan'),
          ),
          const SizedBox(height: 20),
          _sectionTitle('Live Session'),
          const SizedBox(height: 8),
          _buildSessionControls(state),
          pendingCountAsync.when(
            data: (count) => count > 0
                ? Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Row(
                      children: [
                        const Icon(Icons.cloud_upload_outlined, size: 18),
                        const SizedBox(width: 6),
                        Text('Pending uploads: $count'),
                      ],
                    ),
                  )
                : const SizedBox.shrink(),
            loading: () => const SizedBox.shrink(),
            error: (_, __) => const SizedBox.shrink(),
          ),
          const SizedBox(height: 12),
          _buildManualLogCard(
            state: state,
            manualMenus: manualMenus,
            selectedManualMenu: selectedManualMenu,
          ),
          const SizedBox(height: 12),
          _buildSessionLogManager(state),
          const SizedBox(height: 12),
          if (quickLog != null)
            ..._buildScorecard(state: state, quickLog: quickLog),
          const SizedBox(height: 16),
          _buildRestTimer(),
          if (state.error != null) ...[
            const SizedBox(height: 12),
            Text(state.error!, style: const TextStyle(color: Colors.red)),
          ],
          if (state.recentLogs.isNotEmpty) ...[
            const SizedBox(height: 12),
            _sectionTitle('Recent Logs'),
            const SizedBox(height: 8),
            ...state.recentLogs.take(5).map((log) => Text(log)),
          ],
          if (state.plan != null) ...[
            const SizedBox(height: 20),
            _PlanHeader(planName: state.plan!.planName),
            const SizedBox(height: 12),
            ...state.plan!.days.map((day) => _DayCard(day: day)),
          ],
        ],
      ),
    );
  }

  Widget _buildManualLogCard({
    required WorkoutState state,
    required List<String> manualMenus,
    required String? selectedManualMenu,
  }) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Manual Log', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            Text(
              'Pick or add your own exercise, then log in one tap.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    key: ValueKey(selectedManualMenu ?? 'none'),
                    initialValue: selectedManualMenu,
                    decoration:
                        const InputDecoration(labelText: 'Exercise Menu'),
                    items: manualMenus
                        .map(
                          (menu) => DropdownMenuItem(
                            value: menu,
                            child: Text(menu),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value == null) return;
                      _onManualMenuSelected(state, value);
                    },
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filledTonal(
                  onPressed: _showAddMenuDialog,
                  icon: const Icon(Icons.add),
                  tooltip: 'Add custom menu',
                ),
              ],
            ),
            if (_customMenus.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: _customMenus
                    .map(
                      (menu) => InputChip(
                        label: Text(menu),
                        selected: selectedManualMenu?.toLowerCase() ==
                            menu.toLowerCase(),
                        onSelected: (_) => _onManualMenuSelected(state, menu),
                        onDeleted: () => _removeCustomMenu(menu),
                      ),
                    )
                    .toList(),
              ),
            ],
            const SizedBox(height: 12),
            _QuickValueDisplay(
              label: 'Weight',
              value: '${_manualWeight.toStringAsFixed(1)} kg',
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                _QuickAdjustButton(
                  label: '-2.5',
                  onTap: () => setState(() {
                    _manualWeight = double.parse((_manualWeight - 2.5)
                        .clamp(0.0, 999.0)
                        .toStringAsFixed(1));
                  }),
                ),
                const SizedBox(width: 8),
                _QuickAdjustButton(
                  label: '-1.25',
                  onTap: () => setState(() {
                    _manualWeight = double.parse((_manualWeight - 1.25)
                        .clamp(0.0, 999.0)
                        .toStringAsFixed(2));
                  }),
                ),
                const SizedBox(width: 8),
                _QuickAdjustButton(
                  label: '+1.25',
                  onTap: () => setState(() {
                    _manualWeight = double.parse((_manualWeight + 1.25)
                        .clamp(0.0, 999.0)
                        .toStringAsFixed(2));
                  }),
                ),
                const SizedBox(width: 8),
                _QuickAdjustButton(
                  label: '+2.5',
                  onTap: () => setState(() {
                    _manualWeight = double.parse((_manualWeight + 2.5)
                        .clamp(0.0, 999.0)
                        .toStringAsFixed(1));
                  }),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _QuickValueDisplay(label: 'Reps', value: '$_manualReps'),
            const SizedBox(height: 8),
            Row(
              children: [
                _QuickAdjustButton(
                  label: '-1',
                  onTap: () => setState(() {
                    _manualReps = (_manualReps - 1).clamp(1, 99);
                  }),
                ),
                const SizedBox(width: 8),
                _QuickAdjustButton(
                  label: '+1',
                  onTap: () => setState(() {
                    _manualReps = (_manualReps + 1).clamp(1, 99);
                  }),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                const Text('RPE'),
                Expanded(
                  child: Slider(
                    value: (_manualRpe ?? 8.0).clamp(6.0, 10.0),
                    min: 6,
                    max: 10,
                    divisions: 8,
                    label: (_manualRpe ?? 8.0).toStringAsFixed(1),
                    onChanged: (value) {
                      setState(() => _manualRpe = value);
                    },
                  ),
                ),
                Text((_manualRpe ?? 8.0).toStringAsFixed(1)),
              ],
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: selectedManualMenu == null
                    ? null
                    : () => _logManualSet(state, selectedManualMenu),
                icon: const Icon(Icons.add_task),
                label: const Text('LOG CUSTOM SET'),
              ),
            ),
            if (!state.sessionActive)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(
                  'Start session to enable logging.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildSessionLogManager(WorkoutState state) {
    final filterOptions = <String>{'all'}
      ..addAll(state.sessionSets.map((set) => set.exerciseName));

    final filtered = state.sessionSets.where((set) {
      if (_logFilter == 'all') {
        return true;
      }
      return set.exerciseName == _logFilter;
    }).toList();

    switch (_logSort) {
      case 'oldest':
        filtered.setAll(0, filtered.reversed);
        break;
      case 'weight_desc':
        filtered.sort((a, b) => b.weight.compareTo(a.weight));
        break;
      case 'reps_desc':
        filtered.sort((a, b) => b.reps.compareTo(a.reps));
        break;
      case 'newest':
      default:
        // Keep insertion order from state.sessionSets (newest first).
        break;
    }

    final visibleSets = filtered.take(20).toList();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Log Manager',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                Text('${filtered.length} / ${state.sessionSets.length} sets'),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: _logFilter,
                    decoration: const InputDecoration(
                      labelText: 'Filter',
                    ),
                    items: filterOptions
                        .map(
                          (value) => DropdownMenuItem(
                            value: value,
                            child:
                                Text(value == 'all' ? 'All Exercises' : value),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value == null) return;
                      setState(() => _logFilter = value);
                    },
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: _logSort,
                    decoration: const InputDecoration(
                      labelText: 'Sort',
                    ),
                    items: const [
                      DropdownMenuItem(
                        value: 'newest',
                        child: Text('Newest'),
                      ),
                      DropdownMenuItem(
                        value: 'oldest',
                        child: Text('Oldest'),
                      ),
                      DropdownMenuItem(
                        value: 'weight_desc',
                        child: Text('Weight High-Low'),
                      ),
                      DropdownMenuItem(
                        value: 'reps_desc',
                        child: Text('Reps High-Low'),
                      ),
                    ],
                    onChanged: (value) {
                      if (value == null) return;
                      setState(() => _logSort = value);
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            if (visibleSets.isEmpty)
              Text(
                'No sets yet. Use Quick Log or Manual Log.',
                style: Theme.of(context).textTheme.bodySmall,
              )
            else
              ...visibleSets.map(
                (set) => Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.white12),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: ListTile(
                    dense: true,
                    title: Text(
                      '${set.exerciseName}  ${set.reps} x ${set.weight.toStringAsFixed(1)}kg',
                    ),
                    subtitle: Text(
                      set.rpe == null
                          ? (set.synced ? 'Synced' : 'Pending sync')
                          : 'RPE ${set.rpe!.toStringAsFixed(1)} • ${set.synced ? 'Synced' : 'Pending sync'}',
                    ),
                    trailing: Wrap(
                      spacing: 2,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.edit_outlined),
                          tooltip: 'Edit',
                          onPressed: () => _showEditSetDialog(set),
                        ),
                        IconButton(
                          icon: const Icon(Icons.delete_outline),
                          tooltip: 'Delete',
                          onPressed: () {
                            unawaited(ref
                                .read(workoutProvider.notifier)
                                .removeSessionSet(set.id));
                          },
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            if (filtered.length > 20)
              Text(
                'Showing top 20 results.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
          ],
        ),
      ),
    );
  }

  _QuickLogContext? _resolveQuickLogContext(WorkoutState state) {
    if (!state.sessionActive || state.plan == null) {
      return null;
    }

    final matchingDays =
        state.plan!.days.where((d) => d.dayIndex == state.activeDayIndex);
    if (matchingDays.isEmpty) {
      return null;
    }

    final day = matchingDays.first;
    if (day.exercises.isEmpty) {
      return null;
    }

    final safeIndex =
        _activeExercisePosition.clamp(0, day.exercises.length - 1).toInt();
    final exercise = day.exercises[safeIndex];
    final key = exercise.exerciseKey;
    final last = state.lastSetByExercise[key];
    final reps = _repsByExercise[key] ??
        (last?.reps ?? _suggestedReps(exercise.repRange));
    final weight = _weightByExercise[key] ?? (last?.weight ?? 0.0);
    final rpe = _rpeByExercise[key] ?? last?.rpe;
    final completedSets =
        state.sessionSets.where((set) => set.exerciseKey == key).length;
    final setNumber = (completedSets + 1).clamp(1, exercise.sets).toInt();

    return _QuickLogContext(
      day: day,
      exercise: exercise,
      key: key,
      last: last,
      reps: reps,
      weight: weight,
      rpe: rpe,
      safeIndex: safeIndex,
      setNumber: setNumber,
      targetSets: exercise.sets,
    );
  }

  Widget _sectionTitle(String text) {
    return Text(
      text,
      style: Theme.of(context)
          .textTheme
          .titleMedium
          ?.copyWith(fontWeight: FontWeight.bold),
    );
  }

  Widget _buildSessionControls(WorkoutState state) {
    if (state.plan == null) {
      return const Text('Generate a plan to start a session.');
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Choose Day', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: state.plan!.days
                  .map(
                    (day) => ChoiceChip(
                      label: Text('Day ${day.dayIndex} - ${day.focus}'),
                      selected: state.activeDayIndex == day.dayIndex,
                      onSelected: (_) {
                        setState(() => _activeExercisePosition = 0);
                        ref
                            .read(workoutProvider.notifier)
                            .startSession(dayIndex: day.dayIndex);
                      },
                    ),
                  )
                  .toList(),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: ElevatedButton(
                    onPressed: state.sessionActive
                        ? null
                        : () {
                            setState(() => _activeExercisePosition = 0);
                            ref
                                .read(workoutProvider.notifier)
                                .startSession(dayIndex: state.activeDayIndex);
                          },
                    child: const Text('Start Session'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton(
                    onPressed: state.sessionActive
                        ? () async {
                            await ref
                                .read(workoutProvider.notifier)
                                .endSession();
                            if (!mounted) return;
                            context.go('/session_summary');
                          }
                        : null,
                    child: const Text('End Session'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _buildScorecard({
    required WorkoutState state,
    required _QuickLogContext quickLog,
  }) {
    final day = quickLog.day;
    final exercise = quickLog.exercise;
    final key = quickLog.key;
    final last = quickLog.last;
    final reps = quickLog.reps;
    final weight = quickLog.weight;
    final safeIndex = quickLog.safeIndex;

    return [
      Card(
        margin: const EdgeInsets.only(bottom: 12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Quick Log Pad',
                style: Theme.of(context)
                    .textTheme
                    .titleMedium
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text(
                '${exercise.name} (${safeIndex + 1}/${day.exercises.length})',
                style:
                    const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 4),
              Text('Set ${quickLog.setNumber} / ${quickLog.targetSets}'),
              const SizedBox(height: 6),
              Text(
                '${exercise.sets} sets - ${exercise.repRange} - Rest ${_restForExercise(exercise)}s',
              ),
              if (last != null) ...[
                const SizedBox(height: 8),
                Text(
                  'Last: ${last.reps} reps @ ${last.weight.toStringAsFixed(1)}kg',
                ),
              ],
              const SizedBox(height: 16),
              _QuickValueDisplay(
                label: 'Weight',
                value: '${weight.toStringAsFixed(1)} kg',
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  _QuickAdjustButton(
                    label: '-2.5',
                    onTap: () => _adjustWeight(key, weight, -2.5),
                  ),
                  const SizedBox(width: 8),
                  _QuickAdjustButton(
                    label: '-1.25',
                    onTap: () => _adjustWeight(key, weight, -1.25),
                  ),
                  const SizedBox(width: 8),
                  _QuickAdjustButton(
                    label: '+1.25',
                    onTap: () => _adjustWeight(key, weight, 1.25),
                  ),
                  const SizedBox(width: 8),
                  _QuickAdjustButton(
                    label: '+2.5',
                    onTap: () => _adjustWeight(key, weight, 2.5),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              _QuickValueDisplay(label: 'Reps', value: '$reps'),
              const SizedBox(height: 8),
              Row(
                children: [
                  _QuickAdjustButton(
                    label: '-1',
                    onTap: () => _adjustReps(key, reps, -1),
                  ),
                  const SizedBox(width: 8),
                  _QuickAdjustButton(
                    label: '+1',
                    onTap: () => _adjustReps(key, reps, 1),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: last == null
                          ? null
                          : () => _logQuickSet(
                                state: state,
                                exercise: exercise,
                                reps: last.reps,
                                weight: last.weight,
                                rpe: last.rpe,
                              ),
                      child: const Text('Repeat Last Set'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: OutlinedButton(
                      onPressed: safeIndex == 0
                          ? null
                          : () => setState(() => _activeExercisePosition -= 1),
                      child: const Text('Prev'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: safeIndex >= day.exercises.length - 1
                      ? null
                      : () => setState(() => _activeExercisePosition += 1),
                  child: const Text('Next Exercise'),
                ),
              ),
              const SizedBox(height: 10),
              Text(
                'Adjust values, then tap LOG SET at bottom.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
    ];
  }

  Widget _buildStickyLogBar({
    required WorkoutState state,
    required _QuickLogContext quickLog,
  }) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
        child: SizedBox(
          height: 64,
          child: FilledButton(
            onPressed: () => _logQuickSet(
              state: state,
              exercise: quickLog.exercise,
              reps: quickLog.reps,
              weight: quickLog.weight,
              rpe: quickLog.rpe,
            ),
            child: Text(
              'LOG SET  ${quickLog.weight.toStringAsFixed(1)}kg x ${quickLog.reps}  (Set ${quickLog.setNumber})',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildRestTimer() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Rest Timer',
                    style: Theme.of(context).textTheme.titleMedium),
                Text(_restSeconds > 0 ? '${_restSeconds}s' : 'Ready'),
              ],
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                TextButton(
                  onPressed: () => _startRestTimer(60),
                  child: const Text('60s'),
                ),
                TextButton(
                  onPressed: () => _startRestTimer(90),
                  child: const Text('90s'),
                ),
                TextButton(
                  onPressed: () => _startRestTimer(120),
                  child: const Text('120s'),
                ),
                TextButton(
                  onPressed: () => _startRestTimer(_customRestSeconds),
                  child: Text('Start ${_customRestSeconds}s'),
                ),
                TextButton(
                  onPressed: () {
                    _restTimer?.cancel();
                    setState(() => _restSeconds = 0);
                  },
                  child: const Text('Reset'),
                ),
              ],
            ),
            Row(
              children: [
                Expanded(
                  child: Slider(
                    value: _customRestSeconds.toDouble(),
                    min: 30,
                    max: 300,
                    divisions: 18,
                    label: '${_customRestSeconds}s',
                    onChanged: (value) =>
                        setState(() => _customRestSeconds = value.round()),
                  ),
                ),
                Text('${_customRestSeconds}s'),
              ],
            ),
            SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              value: _useCustomRestForLog,
              onChanged: (value) =>
                  setState(() => _useCustomRestForLog = value),
              title: const Text('Use custom timer after Log Set'),
              subtitle: const Text('When off, plan rest seconds are used.'),
            ),
          ],
        ),
      ),
    );
  }
}

class _QuickAdjustButton extends StatelessWidget {
  const _QuickAdjustButton({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: SizedBox(
        height: 52,
        child: OutlinedButton(
          onPressed: onTap,
          child: Text(label, style: const TextStyle(fontSize: 16)),
        ),
      ),
    );
  }
}

class _QuickValueDisplay extends StatelessWidget {
  const _QuickValueDisplay({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: Theme.of(context).textTheme.bodyMedium),
        Text(
          value,
          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
        ),
      ],
    );
  }
}

class _PlanHeader extends StatelessWidget {
  final String planName;
  const _PlanHeader({required this.planName});

  @override
  Widget build(BuildContext context) {
    return Text(
      planName,
      style: Theme.of(context)
          .textTheme
          .headlineSmall
          ?.copyWith(fontWeight: FontWeight.bold),
    );
  }
}

class _DayCard extends StatelessWidget {
  final WorkoutDay day;
  const _DayCard({required this.day});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Day ${day.dayIndex} - ${day.focus}',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            ...day.exercises.map<Widget>((ex) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text(
                  '${ex.name} - ${ex.sets} sets - ${ex.repRange} - RPE ${ex.rpeTarget.toStringAsFixed(1)}',
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}

class _QuickLogContext {
  const _QuickLogContext({
    required this.day,
    required this.exercise,
    required this.key,
    required this.last,
    required this.reps,
    required this.weight,
    required this.rpe,
    required this.safeIndex,
    required this.setNumber,
    required this.targetSets,
  });

  final WorkoutDay day;
  final ExercisePrescription exercise;
  final String key;
  final SessionSet? last;
  final int reps;
  final double weight;
  final double? rpe;
  final int safeIndex;
  final int setNumber;
  final int targetSets;
}
