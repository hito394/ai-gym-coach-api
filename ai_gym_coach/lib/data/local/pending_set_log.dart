import 'package:hive_flutter/hive_flutter.dart';
import '../../shared/utils/exercise_key.dart';

class PendingSetLog {
  final String uuid;
  final String? clientId;
  final int userId;
  final String sessionId;
  final String exerciseName;
  final String? exerciseKeyRaw;
  final int reps;
  final double weight;
  final double? rpe;
  final int? restSeconds;
  final DateTime createdAt;
  final String status;
  final String operation;

  const PendingSetLog({
    required this.uuid,
    this.clientId,
    required this.userId,
    required this.sessionId,
    required this.exerciseName,
    this.exerciseKeyRaw,
    required this.reps,
    required this.weight,
    this.rpe,
    this.restSeconds,
    required this.createdAt,
    required this.status,
    this.operation = 'create',
  });

  String get exerciseKey {
    final explicit = (exerciseKeyRaw ?? '').trim();
    if (explicit.isNotEmpty) return explicit;
    return normalizeExerciseKey(exerciseName);
  }

  String get targetClientId {
    final explicit = (clientId ?? '').trim();
    if (explicit.isNotEmpty) return explicit;
    final parts = uuid.split(':');
    return parts.length == 2 ? parts.last : uuid;
  }

  String get normalizedOperation {
    final value = operation.trim().toLowerCase();
    if (value == 'update' || value == 'delete') {
      return value;
    }
    return 'create';
  }

  PendingSetLog copyWith({String? status, String? operation}) {
    return PendingSetLog(
      uuid: uuid,
      clientId: clientId,
      userId: userId,
      sessionId: sessionId,
      exerciseName: exerciseName,
      exerciseKeyRaw: exerciseKeyRaw,
      reps: reps,
      weight: weight,
      rpe: rpe,
      restSeconds: restSeconds,
      createdAt: createdAt,
      status: status ?? this.status,
      operation: operation ?? this.operation,
    );
  }
}

class PendingSetLogAdapter extends TypeAdapter<PendingSetLog> {
  @override
  final int typeId = 42;

  @override
  PendingSetLog read(BinaryReader reader) {
    int? restSeconds;
    bool hasRest = false;
    String? clientId;
    String? exerciseKeyRaw;
    String operation = 'create';
    return PendingSetLog(
      uuid: reader.readString(),
      userId: reader.readInt(),
      sessionId: reader.readString(),
      exerciseName: reader.readString(),
      reps: reader.readInt(),
      weight: reader.readDouble(),
      rpe: reader.readBool() ? reader.readDouble() : null,
      createdAt: DateTime.parse(reader.readString()),
      status: reader.readString(),
      restSeconds: (() {
        try {
          hasRest = reader.readBool();
          if (!hasRest) return null;
          restSeconds = reader.readInt();
          return restSeconds;
        } catch (_) {
          return null;
        }
      })(),
      clientId: (() {
        try {
          final hasClientId = reader.readBool();
          if (!hasClientId) return null;
          clientId = reader.readString();
          return clientId;
        } catch (_) {
          return null;
        }
      })(),
      exerciseKeyRaw: (() {
        try {
          final hasExerciseKey = reader.readBool();
          if (!hasExerciseKey) return null;
          exerciseKeyRaw = reader.readString();
          return exerciseKeyRaw;
        } catch (_) {
          return null;
        }
      })(),
      operation: (() {
        try {
          operation = reader.readString();
          return operation;
        } catch (_) {
          return 'create';
        }
      })(),
    );
  }

  @override
  void write(BinaryWriter writer, PendingSetLog obj) {
    writer.writeString(obj.uuid);
    writer.writeInt(obj.userId);
    writer.writeString(obj.sessionId);
    writer.writeString(obj.exerciseName);
    writer.writeInt(obj.reps);
    writer.writeDouble(obj.weight);
    writer.writeBool(obj.rpe != null);
    if (obj.rpe != null) {
      writer.writeDouble(obj.rpe!);
    }
    writer.writeString(obj.createdAt.toIso8601String());
    writer.writeString(obj.status);
    writer.writeBool(obj.restSeconds != null);
    if (obj.restSeconds != null) {
      writer.writeInt(obj.restSeconds!);
    }
    writer.writeBool(obj.clientId != null);
    if (obj.clientId != null) {
      writer.writeString(obj.clientId!);
    }
    writer.writeBool(obj.exerciseKeyRaw != null);
    if (obj.exerciseKeyRaw != null) {
      writer.writeString(obj.exerciseKeyRaw!);
    }
    writer.writeString(obj.operation);
  }
}
