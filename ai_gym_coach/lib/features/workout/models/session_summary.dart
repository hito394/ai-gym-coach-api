class SessionSummary {
  final String sessionId;
  final int totalSets;
  final double totalVolume;
  final Map<String, double> sessionPrs;
  final Map<String, String> recommendations;
  final List<String> coachHighlights;

  const SessionSummary({
    required this.sessionId,
    required this.totalSets,
    required this.totalVolume,
    required this.sessionPrs,
    required this.recommendations,
    this.coachHighlights = const [],
  });
}
