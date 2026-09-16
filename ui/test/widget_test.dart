// Basic smoke test: the app shell builds without throwing.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:camcontrol/main.dart';
import 'package:camcontrol/models/gateway_profile.dart';

void main() {
  test('saved gateway profiles migrate from port 8080 to 21416', () {
    final profile = GatewayProfile.fromJson({
      'name': 'Local',
      'baseUrl': 'http://192.168.1.20:8080',
    });

    expect(profile.baseUrl, 'http://192.168.1.20:21416');
  });

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

  testWidgets('prompts for credentials when gateway authentication is required', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final state = AppState(prefs);

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: state,
        child: const CamControlApp(),
      ),
    );

    state.status = 'authenticationRequired';
    state.notifyListeners();
    await tester.pumpAndSettle();

    expect(find.text('Sign in to gateway'), findsOneWidget);
    expect(find.text('Use your Wolff Microsoft Entra account.'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
    expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
  });
}
