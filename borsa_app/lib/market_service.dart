import 'dart:math';

import 'models.dart';

class MarketService {
  MarketService() {
    _prices = {
      for (final e in _seed.entries) e.key: e.value.$2,
    };
  }

  static const Map<String, (String, double)> _seed = {
    'THYAO': ('Türk Hava Yolları', 312.50),
    'ASELS': ('Aselsan', 78.40),
    'GARAN': ('Garanti BBVA', 118.20),
    'EREGL': ('Erdemir', 54.75),
    'BIMAS': ('BİM', 542.00),
    'AKBNK': ('Akbank', 64.30),
    'SAHOL': ('Sabancı Holding', 98.10),
    'KCHOL': ('Koç Holding', 186.40),
    'TUPRS': ('Tüpraş', 168.90),
    'SISE': ('Şişecam', 49.85),
  };

  late final Map<String, double> _prices;
  DateTime _lastTick = DateTime.fromMillisecondsSinceEpoch(0);

  void tick() {
    final now = DateTime.now();
    if (now.difference(_lastTick).inMilliseconds < 1500) return;
    _lastTick = now;
    final rng = Random(now.millisecondsSinceEpoch ~/ 1500);
    for (final symbol in _prices.keys.toList()) {
      final seed = _seed[symbol]!.$2;
      final base = _prices[symbol]!;
      final drift = (rng.nextDouble() * 0.024) - 0.012;
      final next = (base * (1 + drift)).clamp(seed * 0.7, seed * 1.4);
      _prices[symbol] = double.parse(next.toStringAsFixed(2));
    }
  }

  List<Quote> quotes() {
    tick();
    return _seed.entries.map((e) {
      final price = _prices[e.key]!;
      final change = ((price - e.value.$2) / e.value.$2) * 100;
      return Quote(
        symbol: e.key,
        name: e.value.$1,
        price: price,
        changePct: double.parse(change.toStringAsFixed(2)),
      );
    }).toList()
      ..sort((a, b) => a.symbol.compareTo(b.symbol));
  }

  double? priceOf(String symbol) {
    tick();
    return _prices[symbol.toUpperCase()];
  }

  Quote? quoteOf(String symbol) {
    final key = symbol.toUpperCase();
    if (!_seed.containsKey(key)) return null;
    final price = priceOf(key)!;
    final seed = _seed[key]!;
    final change = ((price - seed.$2) / seed.$2) * 100;
    return Quote(
      symbol: key,
      name: seed.$1,
      price: price,
      changePct: double.parse(change.toStringAsFixed(2)),
    );
  }
}
