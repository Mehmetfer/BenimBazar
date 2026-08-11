import 'models.dart';

class PortfolioService {
  PortfolioService({this.startingCash = 100000});

  final double startingCash;
  double cash = 0;
  final Map<String, Position> _positions = {};
  final List<Trade> trades = [];

  void reset() {
    cash = startingCash;
    _positions.clear();
    trades.clear();
  }

  List<Position> get positions =>
      _positions.values.where((p) => p.quantity > 0).toList()
        ..sort((a, b) => a.symbol.compareTo(b.symbol));

  void buy(String symbol, double quantity, double price) {
    if (quantity <= 0) {
      throw StateError('Miktar 0\'dan büyük olmalı.');
    }
    final total = quantity * price;
    if (total > cash) {
      throw StateError(
        'Yetersiz bakiye. Gerekli: ${total.toStringAsFixed(2)} TL',
      );
    }
    cash -= total;
    final existing = _positions[symbol];
    if (existing == null) {
      _positions[symbol] = Position(
        symbol: symbol,
        quantity: quantity,
        avgCost: price,
      );
    } else {
      final newQty = existing.quantity + quantity;
      final newCost =
          ((existing.quantity * existing.avgCost) + total) / newQty;
      _positions[symbol] = existing.copyWith(
        quantity: newQty,
        avgCost: newCost,
      );
    }
    trades.insert(
      0,
      Trade(
        side: 'BUY',
        symbol: symbol,
        quantity: quantity,
        price: price,
        createdAt: DateTime.now(),
      ),
    );
  }

  void sell(String symbol, double quantity, double price) {
    if (quantity <= 0) {
      throw StateError('Miktar 0\'dan büyük olmalı.');
    }
    final existing = _positions[symbol];
    if (existing == null || existing.quantity < quantity) {
      final have = existing?.quantity ?? 0;
      throw StateError('Yetersiz lot. Elinde: $have');
    }
    cash += quantity * price;
    final left = existing.quantity - quantity;
    if (left <= 1e-9) {
      _positions.remove(symbol);
    } else {
      _positions[symbol] = existing.copyWith(quantity: left);
    }
    trades.insert(
      0,
      Trade(
        side: 'SELL',
        symbol: symbol,
        quantity: quantity,
        price: price,
        createdAt: DateTime.now(),
      ),
    );
  }

  double holdingsValue(double Function(String symbol) markPrice) {
    var total = 0.0;
    for (final p in positions) {
      total += p.quantity * markPrice(p.symbol);
    }
    return total;
  }

  double equity(double Function(String symbol) markPrice) =>
      cash + holdingsValue(markPrice);
}
