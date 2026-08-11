import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import 'market_service.dart';
import 'models.dart';
import 'portfolio_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
    ),
  );
  runApp(const BorsaApp());
}

class BorsaApp extends StatelessWidget {
  const BorsaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Borsa',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: const ColorScheme.dark(
          surface: Color(0xFF0B1220),
          primary: Color(0xFF1F9D6A),
          secondary: Color(0xFFC44B4B),
          onSurface: Color(0xFFE8EEF8),
        ),
        scaffoldBackgroundColor: const Color(0xFF0B1220),
      ),
      home: const TradingHomePage(),
    );
  }
}

class TradingHomePage extends StatefulWidget {
  const TradingHomePage({super.key});

  @override
  State<TradingHomePage> createState() => _TradingHomePageState();
}

class _TradingHomePageState extends State<TradingHomePage> {
  final _market = MarketService();
  final _portfolio = PortfolioService();
  final _qtyCtrl = TextEditingController(text: '10');
  final _money = NumberFormat.currency(locale: 'tr_TR', symbol: '₺');

  String _side = 'BUY';
  String? _symbol;
  String? _message;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _portfolio.reset();
    final quotes = _market.quotes();
    _symbol = quotes.isNotEmpty ? quotes.first.symbol : null;
    _timer = Timer.periodic(const Duration(seconds: 2), (_) {
      if (!mounted) return;
      setState(() => _market.tick());
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _qtyCtrl.dispose();
    super.dispose();
  }

  double _mark(String symbol) => _market.priceOf(symbol) ?? 0;

  void _submit() {
    final symbol = _symbol;
    final qty = double.tryParse(_qtyCtrl.text.replaceAll(',', '.'));
    if (symbol == null || qty == null) {
      setState(() => _message = 'Hisse ve lot seç.');
      return;
    }
    final price = _market.priceOf(symbol);
    if (price == null) {
      setState(() => _message = 'Fiyat yok.');
      return;
    }
    try {
      if (_side == 'BUY') {
        _portfolio.buy(symbol, qty, price);
        setState(() => _message = 'Alındı: $qty $symbol @ ${_money.format(price)}');
      } else {
        _portfolio.sell(symbol, qty, price);
        setState(() => _message = 'Satıldı: $qty $symbol @ ${_money.format(price)}');
      }
    } catch (e) {
      setState(() => _message = e.toString().replaceFirst('Bad state: ', ''));
    }
  }

  @override
  Widget build(BuildContext context) {
    final quotes = _market.quotes();
    final equity = _portfolio.equity(_mark);
    final pnl = equity - _portfolio.startingCash;
    final selected = quotes.cast<Quote?>().firstWhere(
          (q) => q!.symbol == _symbol,
          orElse: () => quotes.isEmpty ? null : quotes.first,
        );
    final qty = double.tryParse(_qtyCtrl.text.replaceAll(',', '.')) ?? 0;
    final total = (selected?.price ?? 0) * qty;

    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
          children: [
            _Header(
              equity: _money.format(equity),
              pnl: '${pnl >= 0 ? '+' : ''}${_money.format(pnl)}',
              pnlUp: pnl >= 0,
            ),
            const SizedBox(height: 14),
            _OrderCard(
              side: _side,
              symbol: _symbol,
              quotes: quotes,
              qtyCtrl: _qtyCtrl,
              priceText: selected == null ? '—' : _money.format(selected.price),
              totalText: _money.format(total),
              message: _message,
              onSide: (s) => setState(() => _side = s),
              onSymbol: (s) => setState(() => _symbol = s),
              onChangedQty: (_) => setState(() {}),
              onSubmit: _submit,
            ),
            const SizedBox(height: 14),
            _Section(
              title: 'Piyasa',
              trailing: TextButton(
                onPressed: () => setState(() => _market.tick()),
                child: const Text('Yenile'),
              ),
              child: Column(
                children: quotes
                    .map(
                      (q) => Material(
                        color: Colors.transparent,
                        child: _QuoteTile(
                          quote: q,
                          money: _money,
                          selected: q.symbol == _symbol,
                          onTap: () => setState(() {
                            _symbol = q.symbol;
                            _side = 'BUY';
                          }),
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
            const SizedBox(height: 14),
            _Section(
              title: 'Pozisyonlar',
              trailing: TextButton(
                onPressed: () {
                  setState(() {
                    _portfolio.reset();
                    _message = 'Portföy sıfırlandı.';
                  });
                },
                child: const Text('Sıfırla'),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (_portfolio.positions.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: Text('Pozisyon yok', style: TextStyle(color: Color(0xFF8FA0B8))),
                    )
                  else
                    ..._portfolio.positions.map((p) {
                      final mark = _mark(p.symbol);
                      final posPnl = (mark - p.avgCost) * p.quantity;
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        onTap: () => setState(() {
                          _symbol = p.symbol;
                          _side = 'SELL';
                        }),
                        title: Text(p.symbol, style: const TextStyle(fontWeight: FontWeight.w600)),
                        subtitle: Text('${p.quantity} lot · maliyet ${_money.format(p.avgCost)}'),
                        trailing: Text(
                          _money.format(posPnl),
                          style: TextStyle(
                            color: posPnl >= 0 ? const Color(0xFF3DD68C) : const Color(0xFFFF6B6B),
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      );
                    }),
                  const SizedBox(height: 4),
                  Text(
                    'Nakit: ${_money.format(_portfolio.cash)}',
                    style: const TextStyle(color: Color(0xFF8FA0B8)),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            _Section(
              title: 'Son işlemler',
              child: Column(
                children: [
                  if (_portfolio.trades.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: Text('İşlem yok', style: TextStyle(color: Color(0xFF8FA0B8))),
                      ),
                    )
                  else
                    ..._portfolio.trades.take(12).map((t) {
                      final buy = t.side == 'BUY';
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        dense: true,
                        title: Text('${buy ? 'AL' : 'SAT'}  ${t.symbol}'),
                        subtitle: Text('${t.quantity} lot'),
                        trailing: Text(
                          _money.format(t.price),
                          style: TextStyle(
                            color: buy ? const Color(0xFF3DD68C) : const Color(0xFFFF6B6B),
                          ),
                        ),
                      );
                    }),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.equity,
    required this.pnl,
    required this.pnlUp,
  });

  final String equity;
  final String pnl;
  final bool pnlUp;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        const Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Borsa',
                style: TextStyle(
                  fontSize: 40,
                  height: 0.95,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -1.2,
                ),
              ),
              SizedBox(height: 6),
              Text('Kağıt üstü al–sat', style: TextStyle(color: Color(0xFF8FA0B8))),
            ],
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: const Color(0xE6101A28),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0x22E8EEF8)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              const Text('Portföy', style: TextStyle(color: Color(0xFF8FA0B8), fontSize: 12)),
              Text(equity, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
              Text(
                pnl,
                style: TextStyle(
                  color: pnlUp ? const Color(0xFF3DD68C) : const Color(0xFFFF6B6B),
                  fontSize: 13,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _OrderCard extends StatelessWidget {
  const _OrderCard({
    required this.side,
    required this.symbol,
    required this.quotes,
    required this.qtyCtrl,
    required this.priceText,
    required this.totalText,
    required this.message,
    required this.onSide,
    required this.onSymbol,
    required this.onChangedQty,
    required this.onSubmit,
  });

  final String side;
  final String? symbol;
  final List<Quote> quotes;
  final TextEditingController qtyCtrl;
  final String priceText;
  final String totalText;
  final String? message;
  final ValueChanged<String> onSide;
  final ValueChanged<String?> onSymbol;
  final ValueChanged<String> onChangedQty;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    final buy = side == 'BUY';
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xE6101A28),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0x22E8EEF8)),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: _SideButton(
                  label: 'Al',
                  active: buy,
                  color: const Color(0xFF1F9D6A),
                  onTap: () => onSide('BUY'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _SideButton(
                  label: 'Sat',
                  active: !buy,
                  color: const Color(0xFFC44B4B),
                  onTap: () => onSide('SELL'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                flex: 3,
                child: DropdownButtonFormField<String>(
                  value: symbol,
                  isExpanded: true,
                  decoration: const InputDecoration(
                    labelText: 'Hisse',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                  items: quotes
                      .map(
                        (q) => DropdownMenuItem(
                          value: q.symbol,
                          child: Text(q.symbol, overflow: TextOverflow.ellipsis),
                        ),
                      )
                      .toList(),
                  onChanged: onSymbol,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                flex: 2,
                child: TextField(
                  controller: qtyCtrl,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  onChanged: onChangedQty,
                  decoration: const InputDecoration(
                    labelText: 'Lot',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Fiyat: $priceText', style: const TextStyle(color: Color(0xFF8FA0B8))),
              Text('Toplam: $totalText', style: const TextStyle(color: Color(0xFF8FA0B8))),
            ],
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: buy ? const Color(0xFF1F9D6A) : const Color(0xFFC44B4B),
              ),
              onPressed: onSubmit,
              child: Text(buy ? 'Al' : 'Sat', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            ),
          ),
          if (message != null && message!.isNotEmpty) ...[
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(message!, style: const TextStyle(fontSize: 13)),
            ),
          ],
        ],
      ),
    );
  }
}

class _SideButton extends StatelessWidget {
  const _SideButton({
    required this.label,
    required this.active,
    required this.color,
    required this.onTap,
  });

  final String label;
  final bool active;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: active ? color : Colors.transparent,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          height: 42,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: active ? color : const Color(0x33E8EEF8)),
          ),
          child: Text(label, style: const TextStyle(fontWeight: FontWeight.w700)),
        ),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({
    required this.title,
    required this.child,
    this.trailing,
  });

  final String title;
  final Widget child;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 10, 8, 12),
      decoration: BoxDecoration(
        color: const Color(0xE6101A28),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0x22E8EEF8)),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title.toUpperCase(),
                  style: const TextStyle(
                    color: Color(0xFF8FA0B8),
                    fontSize: 12,
                    letterSpacing: 0.8,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              if (trailing != null) trailing!,
            ],
          ),
          child,
        ],
      ),
    );
  }
}

class _QuoteTile extends StatelessWidget {
  const _QuoteTile({
    required this.quote,
    required this.money,
    required this.selected,
    required this.onTap,
  });

  final Quote quote;
  final NumberFormat money;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final up = quote.changePct >= 0;
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 6),
      selected: selected,
      selectedTileColor: const Color(0x221F9D6A),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      onTap: onTap,
      title: Text(quote.symbol, style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: Text(quote.name),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(money.format(quote.price), style: const TextStyle(fontWeight: FontWeight.w600)),
          Text(
            '${up ? '+' : ''}${quote.changePct}%',
            style: TextStyle(
              color: up ? const Color(0xFF3DD68C) : const Color(0xFFFF6B6B),
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}
