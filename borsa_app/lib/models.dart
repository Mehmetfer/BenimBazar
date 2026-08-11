class Quote {
  const Quote({
    required this.symbol,
    required this.name,
    required this.price,
    required this.changePct,
  });

  final String symbol;
  final String name;
  final double price;
  final double changePct;
}

class Position {
  const Position({
    required this.symbol,
    required this.quantity,
    required this.avgCost,
  });

  final String symbol;
  final double quantity;
  final double avgCost;

  Position copyWith({double? quantity, double? avgCost}) {
    return Position(
      symbol: symbol,
      quantity: quantity ?? this.quantity,
      avgCost: avgCost ?? this.avgCost,
    );
  }
}

class Trade {
  const Trade({
    required this.side,
    required this.symbol,
    required this.quantity,
    required this.price,
    required this.createdAt,
  });

  final String side; // BUY | SELL
  final String symbol;
  final double quantity;
  final double price;
  final DateTime createdAt;

  double get total => quantity * price;
}
