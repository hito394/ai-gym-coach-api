import 'dart:math';
import 'dart:typed_data';
import 'package:camera/camera.dart';
import 'package:tflite_flutter/tflite_flutter.dart';
import '../../../core/pose/pose_types.dart';

class InferenceResult {
  final List<Keypoint> keypoints;
  final PoseRect? roiRect;
  final PoseRect inputRect;
  final double brightness;
  final bool usedRoi;
  const InferenceResult({
    required this.keypoints,
    required this.roiRect,
    required this.inputRect,
    required this.brightness,
    required this.usedRoi,
  });
}

class FormInferenceService {
  Interpreter? _interpreter;
  List<int> _inputShape = const [1, 192, 192, 3];
  double _lastScale = 1.0;
  double _lastOffsetX = 0.0;
  double _lastOffsetY = 0.0;
  int _lastWidth = 1;
  int _lastHeight = 1;
  double _roiX = 0.0;
  double _roiY = 0.0;
  double _roiW = 0.0;
  double _roiH = 0.0;
  bool _usedRoi = false;
  List<Keypoint> _lastKeypoints = const [];
  PoseRect _lastInputRect = const PoseRect(x: 0, y: 0, width: 1, height: 1);

  Future<void> loadModel({required bool accuracyMode}) async {
    final options = InterpreterOptions()..threads = 2;
    if (accuracyMode) {
      _interpreter = await Interpreter.fromAsset(
        'movenet.tflite',
        options: options,
      );
    } else {
      try {
        _interpreter = await Interpreter.fromAsset(
          'movenet_lightning.tflite',
          options: options,
        );
      } catch (_) {
        _interpreter = await Interpreter.fromAsset(
          'movenet.tflite',
          options: options,
        );
      }
    }
    _inputShape = _interpreter!.getInputTensor(0).shape;
  }

  void dispose() {
    _interpreter?.close();
    _interpreter = null;
  }

  int get inputSize => _inputShape[1];

  Future<InferenceResult> infer(CameraImage image) async {
    final interpreter = _interpreter;
    if (interpreter == null) {
      return const InferenceResult(
        keypoints: [],
        roiRect: null,
        inputRect: PoseRect(x: 0, y: 0, width: 1, height: 1),
        brightness: 0.0,
        usedRoi: false,
      );
    }

    final inputSize = _inputShape[1];
    final brightness = _computeBrightness(image);
    final roi = _estimateRoi(image.width, image.height);
    final input = _preprocess(image, inputSize, inputSize, roi);
    final output = List.generate(
        1,
        (_) => List.generate(
            1, (_) => List.generate(17, (_) => List.filled(3, 0.0))));

    interpreter.run(input, output);

    final keypoints = <Keypoint>[];
    for (var i = 0; i < 17; i++) {
      final y = output[0][0][i][0];
      final x = output[0][0][i][1];
      final score = output[0][0][i][2];
      final px = _usedRoi
          ? _roiX + (x * _roiW)
          : (x * inputSize - _lastOffsetX) / _lastScale;
      final py = _usedRoi
          ? _roiY + (y * _roiH)
          : (y * inputSize - _lastOffsetY) / _lastScale;
      final nx = (px / _lastWidth).clamp(0.0, 1.0);
      final ny = (py / _lastHeight).clamp(0.0, 1.0);
      keypoints.add(Keypoint(x: nx, y: ny, score: score));
    }

    _lastKeypoints = keypoints;
    return InferenceResult(
      keypoints: keypoints,
      roiRect: roi,
      inputRect: _lastInputRect,
      brightness: brightness,
      usedRoi: _usedRoi,
    );
  }

  Float32List _preprocess(
      CameraImage image, int inputW, int inputH, PoseRect? roiRect) {
    final width = image.width;
    final height = image.height;
    _lastWidth = width;
    _lastHeight = height;

    if (image.planes.isEmpty) {
      return Float32List(inputW * inputH * 3);
    }

    final yPlane = image.planes[0].bytes;
    final yRowStride = image.planes[0].bytesPerRow;
    final planeCount = image.planes.length;
    final output = Float32List(inputW * inputH * 3);

    final Uint8List? uPlane = planeCount >= 3 ? image.planes[1].bytes : null;
    final Uint8List? vPlane = planeCount >= 3 ? image.planes[2].bytes : null;
    final int? uRowStride =
        planeCount >= 3 ? image.planes[1].bytesPerRow : null;
    final int? vRowStride =
        planeCount >= 3 ? image.planes[2].bytesPerRow : null;
    final int? uPixelStride =
        planeCount >= 3 ? (image.planes[1].bytesPerPixel ?? 1) : null;
    final int? vPixelStride =
        planeCount >= 3 ? (image.planes[2].bytesPerPixel ?? 1) : null;

    final Uint8List? uvPlane = planeCount == 2 ? image.planes[1].bytes : null;
    final int? uvRowStride =
        planeCount == 2 ? image.planes[1].bytesPerRow : null;
    final int? uvPixelStride =
        planeCount == 2 ? (image.planes[1].bytesPerPixel ?? 2) : null;
    final int plane0PixelStride = image.planes[0].bytesPerPixel ?? 1;

    void writePixel(Float32List out, int x, int y, int srcX, int srcY) {
      if (planeCount >= 3 &&
          uPlane != null &&
          vPlane != null &&
          uRowStride != null &&
          vRowStride != null &&
          uPixelStride != null &&
          vPixelStride != null) {
        _writePixelPlanarYuv(
          out,
          x,
          y,
          inputW,
          srcX,
          srcY,
          yPlane,
          uPlane,
          vPlane,
          yRowStride,
          uRowStride,
          vRowStride,
          uPixelStride,
          vPixelStride,
        );
        return;
      }

      if (planeCount == 2 && uvPlane != null && uvRowStride != null) {
        _writePixelBiPlanarYuv(
          out,
          x,
          y,
          inputW,
          srcX,
          srcY,
          yPlane,
          uvPlane,
          yRowStride,
          uvRowStride,
          uvPixelStride ?? 2,
        );
        return;
      }

      _writePixelSinglePlane(
        out,
        x,
        y,
        inputW,
        srcX,
        srcY,
        yPlane,
        yRowStride,
        plane0PixelStride,
      );
    }

    if (roiRect != null) {
      _usedRoi = true;
      _roiX = (roiRect.x * width).clamp(0.0, width.toDouble());
      _roiY = (roiRect.y * height).clamp(0.0, height.toDouble());
      _roiW = (roiRect.width * width).clamp(1.0, width.toDouble());
      _roiH = (roiRect.height * height).clamp(1.0, height.toDouble());
      _lastInputRect = roiRect;
      final scaleX = _roiW / inputW;
      final scaleY = _roiH / inputH;

      for (var y = 0; y < inputH; y++) {
        for (var x = 0; x < inputW; x++) {
          final srcX = (_roiX + (x * scaleX)).clamp(0, width - 1).toInt();
          final srcY = (_roiY + (y * scaleY)).clamp(0, height - 1).toInt();
          writePixel(output, x, y, srcX, srcY);
        }
      }
      return output;
    }

    _usedRoi = false;
    final scale = min(inputW / width, inputH / height);
    final resizedW = width * scale;
    final resizedH = height * scale;
    final offsetX = (inputW - resizedW) / 2;
    final offsetY = (inputH - resizedH) / 2;
    _lastScale = scale;
    _lastOffsetX = offsetX;
    _lastOffsetY = offsetY;
    _lastInputRect = const PoseRect(x: 0, y: 0, width: 1, height: 1);

    for (var y = 0; y < inputH; y++) {
      for (var x = 0; x < inputW; x++) {
        final srcX = ((x - offsetX) / scale).clamp(0, width - 1).toInt();
        final srcY = ((y - offsetY) / scale).clamp(0, height - 1).toInt();
        writePixel(output, x, y, srcX, srcY);
      }
    }

    return output;
  }

  void _writePixelPlanarYuv(
    Float32List output,
    int x,
    int y,
    int inputW,
    int srcX,
    int srcY,
    Uint8List yPlane,
    Uint8List uPlane,
    Uint8List vPlane,
    int yRowStride,
    int uRowStride,
    int vRowStride,
    int uPixelStride,
    int vPixelStride,
  ) {
    final yIndex = srcY * yRowStride + srcX;
    final uIndex = (srcY ~/ 2) * uRowStride + (srcX ~/ 2) * uPixelStride;
    final vIndex = (srcY ~/ 2) * vRowStride + (srcX ~/ 2) * vPixelStride;
    final yp = yPlane[yIndex];
    final up = uPlane[uIndex];
    final vp = vPlane[vIndex];

    _writeRgb(output, x, y, inputW, yp, up, vp);
  }

  void _writePixelBiPlanarYuv(
    Float32List output,
    int x,
    int y,
    int inputW,
    int srcX,
    int srcY,
    Uint8List yPlane,
    Uint8List uvPlane,
    int yRowStride,
    int uvRowStride,
    int uvPixelStride,
  ) {
    final yIndex = srcY * yRowStride + srcX;
    final uvIndex = (srcY ~/ 2) * uvRowStride + (srcX ~/ 2) * uvPixelStride;
    final yp = yPlane[yIndex];
    final up = uvPlane[uvIndex];
    final vp = uvPlane[min(uvIndex + 1, uvPlane.length - 1)];

    _writeRgb(output, x, y, inputW, yp, up, vp);
  }

  void _writePixelSinglePlane(
    Float32List output,
    int x,
    int y,
    int inputW,
    int srcX,
    int srcY,
    Uint8List plane,
    int rowStride,
    int pixelStride,
  ) {
    final baseIndex = srcY * rowStride + srcX * pixelStride;
    if (pixelStride >= 4 && baseIndex + 2 < plane.length) {
      // Camera plugin may provide BGRA on some platforms.
      final b = plane[baseIndex].toDouble();
      final g = plane[baseIndex + 1].toDouble();
      final r = plane[baseIndex + 2].toDouble();
      final idx = (y * inputW + x) * 3;
      output[idx] = r / 255.0;
      output[idx + 1] = g / 255.0;
      output[idx + 2] = b / 255.0;
      return;
    }

    final yOnly = plane[min(baseIndex, plane.length - 1)];
    final idx = (y * inputW + x) * 3;
    final normalized = yOnly / 255.0;
    output[idx] = normalized;
    output[idx + 1] = normalized;
    output[idx + 2] = normalized;
  }

  void _writeRgb(
    Float32List output,
    int x,
    int y,
    int inputW,
    int yp,
    int up,
    int vp,
  ) {
    final r = (yp + 1.370705 * (vp - 128)).clamp(0, 255).toDouble();
    final g = (yp - 0.698001 * (vp - 128) - 0.337633 * (up - 128))
        .clamp(0, 255)
        .toDouble();
    final b = (yp + 1.732446 * (up - 128)).clamp(0, 255).toDouble();

    final idx = (y * inputW + x) * 3;
    output[idx] = r / 255.0;
    output[idx + 1] = g / 255.0;
    output[idx + 2] = b / 255.0;
  }

  double _computeBrightness(CameraImage image) {
    final yPlane = image.planes[0].bytes;
    final step = max(1, yPlane.length ~/ 5000);
    var sum = 0.0;
    var count = 0;
    for (var i = 0; i < yPlane.length; i += step) {
      sum += yPlane[i];
      count++;
    }
    return count == 0 ? 0.0 : (sum / count) / 255.0;
  }

  PoseRect? _estimateRoi(int width, int height) {
    if (_lastKeypoints.isEmpty) return null;
    final visible = _lastKeypoints.where((kp) => kp.score >= 0.35).toList();
    if (visible.length < 6) return null;

    double minX = 1.0;
    double maxX = 0.0;
    double minY = 1.0;
    double maxY = 0.0;
    for (final kp in visible) {
      minX = min(minX, kp.x);
      maxX = max(maxX, kp.x);
      minY = min(minY, kp.y);
      maxY = max(maxY, kp.y);
    }

    const margin = 0.3;
    final w = (maxX - minX) * (1 + margin);
    final h = (maxY - minY) * (1 + margin);
    if (w <= 0 || h <= 0) return null;

    final cx = (minX + maxX) / 2;
    final cy = (minY + maxY) / 2;
    final rx = (cx - w / 2).clamp(0.0, 1.0);
    final ry = (cy - h / 2).clamp(0.0, 1.0);
    final rw = min(1.0 - rx, w);
    final rh = min(1.0 - ry, h);

    if (rw < 0.2 || rh < 0.2) {
      return null;
    }

    return PoseRect(x: rx, y: ry, width: rw, height: rh);
  }
}
