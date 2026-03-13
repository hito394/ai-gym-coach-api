import '../../core/network/api_client.dart';

class GymCoachApi {
  GymCoachApi(this._client);

  final ApiClient _client;

  Future<Map<String, dynamic>> createProfile(
      Map<String, dynamic> payload) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/users/profile',
      data: payload,
    );
    return response.data ?? {};
  }

  Future<Map<String, dynamic>> generateWorkout(
      Map<String, dynamic> payload) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/workouts/generate',
      data: payload,
    );
    return response.data ?? {};
  }

  Future<Map<String, dynamic>> chatCoach(Map<String, dynamic> payload) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/chat/coach',
      data: payload,
    );
    return response.data ?? {};
  }

  Future<Map<String, dynamic>> logSet(Map<String, dynamic> payload) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/workouts/log_set',
      data: payload,
    );
    return response.data ?? {};
  }

  Future<Map<String, dynamic>> deleteSet(Map<String, dynamic> payload) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/workouts/delete_set',
      data: payload,
    );
    return response.data ?? {};
  }

  Future<Map<String, dynamic>> workoutHistory(int userId,
      {int limit = 20}) async {
    final response = await _client.get<Map<String, dynamic>>(
      '/workouts/history/$userId?limit=$limit',
    );
    return response.data ?? {};
  }

  Future<Map<String, dynamic>> progressSummary(int userId) async {
    final response = await _client.get<Map<String, dynamic>>(
      '/analytics/summary/$userId',
    );
    return response.data ?? {};
  }

  Future<Map<String, dynamic>> formAnalyze(Map<String, dynamic> payload) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/form/analyze',
      data: payload,
    );
    return response.data ?? {};
  }

  Future<Map<String, dynamic>> adjustProgression(
      Map<String, dynamic> payload) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/progression/adjust',
      data: payload,
    );
    return response.data ?? {};
  }
}
