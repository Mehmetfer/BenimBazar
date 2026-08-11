import 'package:borsa_app/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Borsa home shows brand and Al button', (tester) async {
    await tester.pumpWidget(const BorsaApp());
    await tester.pumpAndSettle();
    expect(find.text('Borsa'), findsOneWidget);
    expect(find.text('Al'), findsWidgets);
    expect(find.text('Sat'), findsWidgets);
  });
}
