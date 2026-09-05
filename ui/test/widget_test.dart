// Basic smoke test: the app shell builds without throwing.

import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:camcontrol/main.dart';

void main() {
  testWidgets('App shell builds and shows bottom navigation', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();

    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => AppState(prefs),
        child: const CamControlApp(),
      ),
    );
    await tester.pump();

    expect(find.text('Cameras'), findsOneWidget);
    expect(find.text('Media'), findsOneWidget);
    expect(find.text('Settings'), findsOneWidget);
  });
}
