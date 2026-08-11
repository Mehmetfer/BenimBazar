import 'package:borsa_app/market_service.dart';
import 'package:borsa_app/portfolio_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('market quotes available', () {
    final market = MarketService();
    final quotes = market.quotes();
    expect(quotes.length, greaterThanOrEqualTo(5));
    expect(market.priceOf('THYAO'), isNotNull);
  });

  test('buy and sell updates portfolio', () {
    final market = MarketService();
    final portfolio = PortfolioService();
    portfolio.reset();
    final price = market.priceOf('THYAO')!;
    final before = portfolio.cash;
    portfolio.buy('THYAO', 2, price);
    expect(portfolio.cash, lessThan(before));
    expect(portfolio.positions.any((p) => p.symbol == 'THYAO'), isTrue);
    portfolio.sell('THYAO', 1, price);
    expect(portfolio.trades.first.side, 'SELL');
  });
}
