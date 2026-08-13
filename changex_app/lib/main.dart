import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'screens/splash_screen.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
    ),
  );
  runApp(const ChangeXApp());
}

class ChangeXApp extends StatelessWidget {
  const ChangeXApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CHANGE X',
      debugShowCheckedModeBanner: false,
      theme: buildChangeXTheme(),
      home: const SplashScreen(),
    );
  }
}
