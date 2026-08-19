import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'core/auth_provider.dart';
import 'core/theme.dart';
import 'features/home/home_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final auth = AuthProvider();
  await auth.init(); // kayıtlı token ile kullanıcıyı yükle
  runApp(
    ChangeNotifierProvider.value(
      value: auth,
      child: const BenimBazarApp(),
    ),
  );
}

class BenimBazarApp extends StatelessWidget {
  const BenimBazarApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BenimBazar',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      home: const HomeScreen(),
    );
  }
}
