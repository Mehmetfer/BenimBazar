import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:changex/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('CHANGE X splash shows brand', (tester) async {
    await tester.pumpWidget(const ChangeXApp());
    expect(find.textContaining('CHANGE'), findsWidgets);
    expect(find.text('X'), findsOneWidget);
    expect(find.textContaining('TAKAS'), findsWidgets);
    // Don't pumpAndSettle — splash schedules network + navigation timers.
    await tester.pump(const Duration(milliseconds: 100));
  });
}
