import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/pose/pose_types.dart';
import '../../../core/pose/squat_classifier.dart';
import '../models/form_state.dart';
import '../providers/form_provider.dart';

class FormCameraScreen extends ConsumerStatefulWidget {
  const FormCameraScreen({super.key});

  @override
  ConsumerState<FormCameraScreen> createState() => _FormCameraScreenState();
}

class _FormCameraScreenState extends ConsumerState<FormCameraScreen>
    with WidgetsBindingObserver {
  late final FormController _formController;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _formController = ref.read(formProvider.notifier);
    Future.microtask(() => _formController.initialize());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        _formController.initialize();
        break;
      case AppLifecycleState.inactive:
      case AppLifecycleState.hidden:
        break;
      case AppLifecycleState.paused:
      case AppLifecycleState.detached:
        _formController.disposeController();
        break;
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _formController.disposeController();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(formProvider);
    final controller = _formController.cameraController;
    final isPreviewReady = controller != null &&
        state.isInitialized &&
        controller.value.isInitialized;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () async {
            await _formController.disposeController();
            if (!context.mounted) return;
            if (context.canPop()) {
              context.pop();
              return;
            }
            context.go('/dashboard');
          },
          icon: const Icon(Icons.arrow_back),
        ),
        title: const Text('Form Lab'),
        actions: [
          IconButton(
            onPressed: () => context.push('/chat'),
            icon: const Icon(Icons.chat_bubble_outline),
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            children: [
              Expanded(
                flex: 7,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(28),
                  child: Container(
                    width: double.infinity,
                    color: const Color(0xFF030706),
                    child: !isPreviewReady
                        ? Center(child: Text(state.statusMessage))
                        : Stack(
                            fit: StackFit.expand,
                            children: [
                              _CameraViewport(
                                controller: controller,
                                lensDirection: state.lensDirection,
                                overlay: state.latest == null
                                    ? null
                                    : CustomPaint(
                                        painter: PoseOverlayPainter(
                                          keypoints: state.latest!.keypoints,
                                          quality: state.latest!.quality,
                                          metrics: state.latest!.metrics,
                                          roiRect: state.latest!.roiRect,
                                          inputRect: state.latest!.inputRect,
                                        ),
                                      ),
                              ),
                              Positioned(
                                left: 14,
                                top: 14,
                                child: _QualityChip(state: state),
                              ),
                              Positioned(
                                right: 14,
                                top: 14,
                                child: _CompactHint(
                                  text: state.lensDirection ==
                                          CameraLensDirection.front
                                      ? 'Selfie view'
                                      : 'Side-view check',
                                ),
                              ),
                            ],
                          ),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              Expanded(
                flex: 5,
                child: SingleChildScrollView(
                  child: Column(
                    children: [
                      _Controls(state: state),
                      const SizedBox(height: 12),
                      _BottomPanel(state: state),
                      if (state.error != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 12),
                          child: Text(
                            state.error!,
                            style: const TextStyle(color: Colors.redAccent),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CameraViewport extends StatelessWidget {
  const _CameraViewport({
    required this.controller,
    required this.lensDirection,
    this.overlay,
  });

  final CameraController controller;
  final CameraLensDirection lensDirection;
  final Widget? overlay;

  @override
  Widget build(BuildContext context) {
    final previewAspectRatio = 1 / controller.value.aspectRatio;

    return LayoutBuilder(
      builder: (context, constraints) {
        final viewportAspectRatio =
            constraints.maxWidth / constraints.maxHeight;
        final scale = previewAspectRatio / viewportAspectRatio;

        Widget preview = AspectRatio(
          aspectRatio: previewAspectRatio,
          child: Stack(
            fit: StackFit.expand,
            children: [
              CameraPreview(controller),
              if (overlay != null) overlay!,
            ],
          ),
        );

        final previewScale = scale < 1 ? 1 / scale : scale;
        preview = Transform(
          alignment: Alignment.center,
          transform: Matrix4.diagonal3Values(previewScale, previewScale, 1.0),
          child: preview,
        );

        if (lensDirection == CameraLensDirection.front) {
          preview = Transform(
            alignment: Alignment.center,
            transform: Matrix4.diagonal3Values(-1.0, 1.0, 1.0),
            child: preview,
          );
        }

        return ClipRect(child: Center(child: preview));
      },
    );
  }
}

class _Controls extends ConsumerWidget {
  const _Controls({required this.state});

  final FormCameraState state;
  static const _durations = [10, 15, 20];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.white.withAlpha(18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Form Check', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 6),
          Text(
            state.isRecording
                ? 'Recording now. Keep your full body visible.'
                : 'Tap Record for a quick squat check.',
            style: const TextStyle(color: Colors.white70),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton.icon(
                onPressed: () => ref.read(formProvider.notifier).switchCamera(),
                icon: const Icon(Icons.cameraswitch_outlined),
                label: Text(
                  state.lensDirection == CameraLensDirection.front
                      ? 'Switch to Back'
                      : 'Switch to Front',
                ),
              ),
              FilledButton.icon(
                onPressed: state.isRecording
                    ? () => ref.read(formProvider.notifier).stopRecording()
                    : () => ref.read(formProvider.notifier).startRecording(),
                icon: Icon(
                  state.isRecording ? Icons.stop : Icons.fiber_manual_record,
                ),
                label: Text(
                  state.isRecording ? 'Stop' : 'Record',
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          const Text('Clip length',
              style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final seconds in _durations)
                ChoiceChip(
                  label: Text('${seconds}s'),
                  selected: state.recordingSeconds == seconds,
                  onSelected: (_) => ref
                      .read(formProvider.notifier)
                      .setRecordingSeconds(seconds),
                ),
            ],
          ),
          const SizedBox(height: 14),
          SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            title: const Text('High accuracy mode'),
            subtitle: const Text(
              'Better grading, slightly slower on older devices',
            ),
            value: state.accuracyMode,
            onChanged: (value) =>
                ref.read(formProvider.notifier).toggleAccuracyMode(value),
          ),
        ],
      ),
    );
  }
}

class _CompactHint extends StatelessWidget {
  const _CompactHint({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.black45,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(text),
    );
  }
}

class _QualityChip extends StatelessWidget {
  const _QualityChip({required this.state});
  final FormCameraState state;

  @override
  Widget build(BuildContext context) {
    final quality = state.latest?.quality;
    final score = quality?.score ?? 0.0;
    final usable = quality?.isUsable ?? false;
    final color = usable ? Colors.green : Colors.orange;
    final tier = quality?.tier ?? 'Blocked';
    final jitter = quality?.jitter ?? 0.0;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withAlpha(204),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        'Pose quality ${score.toStringAsFixed(0)} ($tier) | Jitter ${(jitter * 1000).toStringAsFixed(1)}px',
      ),
    );
  }
}

class _BottomPanel extends StatelessWidget {
  const _BottomPanel({required this.state});
  final FormCameraState state;

  @override
  Widget build(BuildContext context) {
    final quality = state.latest?.quality;
    final result = state.recordedSummary ?? state.classification;
    final feedback = _primaryFeedback(result, state.guidanceMessage, quality);
    final cue = _primaryCue(result, state.guidanceMessage, quality);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.white.withAlpha(18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Result', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(
            feedback,
            style: Theme.of(context)
                .textTheme
                .titleSmall
                ?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 6),
          Text(cue, style: const TextStyle(color: Colors.white70)),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _ResultChip(
                label: state.isRecording ? 'Recording' : 'Ready',
                color: state.isRecording ? Colors.redAccent : Colors.green,
              ),
              _ResultChip(
                label: quality == null
                    ? 'Camera starting'
                    : 'Quality ${quality.tier}',
                color: quality?.isUsable == false ? Colors.orange : Colors.blue,
              ),
              _ResultChip(
                label: 'Reps ${state.repCount}',
                color: Colors.white24,
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _primaryFeedback(
    SquatClassificationResult? result,
    String guidanceMessage,
    PoseQuality? quality,
  ) {
    if (result != null && result.labels.isNotEmpty) {
      switch (result.labels.first.name) {
        case 'depth_insufficient':
          return 'Depth slightly shallow.';
        case 'knee_valgus':
          return 'Knees drift inward slightly.';
        case 'torso_collapse':
          return 'Chest drops a bit too much.';
        case 'asymmetry':
          return 'Left and right sides look uneven.';
        case 'heel_lift':
          return 'Heels rise during the rep.';
        case 'ok':
          return 'Form looks solid.';
        default:
          return 'Camera view needs adjustment.';
      }
    }

    if (guidanceMessage.isNotEmpty) {
      return guidanceMessage;
    }
    if (quality != null && !quality.isUsable) {
      return 'Need a clearer full-body view.';
    }
    return 'Ready for a quick check.';
  }

  String _primaryCue(
    SquatClassificationResult? result,
    String guidanceMessage,
    PoseQuality? quality,
  ) {
    if (result != null && result.cues.isNotEmpty) {
      return result.cues.first;
    }
    if (guidanceMessage.isNotEmpty) {
      return guidanceMessage;
    }
    if (quality != null && quality.reasons.isNotEmpty) {
      return quality.reasons.first;
    }
    return 'Keep your full body in frame from the side view.';
  }
}

class _ResultChip extends StatelessWidget {
  const _ResultChip({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withAlpha(50),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(label),
    );
  }
}

class PoseOverlayPainter extends CustomPainter {
  PoseOverlayPainter({
    required this.keypoints,
    required this.quality,
    required this.metrics,
    this.roiRect,
    this.inputRect,
  });

  final List<Keypoint> keypoints;
  final PoseQuality quality;
  final PoseMetrics metrics;
  final PoseRect? roiRect;
  final PoseRect? inputRect;

  static const _connections = [
    [5, 7],
    [7, 9],
    [6, 8],
    [8, 10],
    [5, 6],
    [5, 11],
    [6, 12],
    [11, 12],
    [11, 13],
    [13, 15],
    [12, 14],
    [14, 16],
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = quality.isUsable ? Colors.greenAccent : Colors.orangeAccent
      ..strokeWidth = 2;
    final pointPaint = Paint()..color = Colors.yellowAccent;
    final roiPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..color = Colors.cyanAccent;
    final inputPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..color = Colors.white54;

    for (final link in _connections) {
      final a = keypoints[link[0]];
      final b = keypoints[link[1]];
      canvas.drawLine(
        Offset(a.x * size.width, a.y * size.height),
        Offset(b.x * size.width, b.y * size.height),
        paint,
      );
    }

    for (final kp in keypoints) {
      canvas.drawCircle(
        Offset(kp.x * size.width, kp.y * size.height),
        3 + (kp.score * 2),
        pointPaint,
      );
    }

    final input = inputRect;
    if (input != null) {
      canvas.drawRect(
        Rect.fromLTWH(
          input.x * size.width,
          input.y * size.height,
          input.width * size.width,
          input.height * size.height,
        ),
        inputPaint,
      );
    }

    final roi = roiRect;
    if (roi != null) {
      canvas.drawRect(
        Rect.fromLTWH(
          roi.x * size.width,
          roi.y * size.height,
          roi.width * size.width,
          roi.height * size.height,
        ),
        roiPaint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant PoseOverlayPainter oldDelegate) {
    return oldDelegate.keypoints != keypoints ||
        oldDelegate.quality.score != quality.score;
  }
}
