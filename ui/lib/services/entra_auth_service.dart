import 'package:msal_auth/msal_auth.dart';

class EntraAuthService {
  static const _clientId = 'b2fa29ad-7625-43f7-b230-e6d51c337aa6';
  static const _tenantId = 'e594a530-1ec9-4192-a8d4-a9111f8cffa7';
  static const _redirectUri =
      'msauth://com.wolff.camcontrol/0OPsbHC7ri61DVy%2FklVoAgrmLYo%3D';
  static const _scopes = [
    'api://1a89197c-5004-4285-b520-22b6275fbeb8/access_as_user',
  ];
  static const _authority =
      'https://login.microsoftonline.com/$_tenantId';

  SingleAccountPca? _client;
  AuthenticationResult? _result;

  String get username => _result?.account.username ?? '';

  Future<void> initialize() async {
    _client ??= await SingleAccountPca.create(
      clientId: _clientId,
      androidConfig: AndroidConfig(
        configFilePath: 'assets/msal_config.json',
        redirectUri: _redirectUri,
      ),
      appleConfig: AppleConfig(
        authority: _authority,
        authorityType: AuthorityType.aad,
        broker: Broker.safariBrowser,
      ),
    );
    try {
      _result = await _client!.acquireTokenSilent(scopes: _scopes);
    } on MsalException {
      _result = null;
    }
  }

  Future<String> accessToken() async {
    if (_client == null) await initialize();
    final current = _result;
    if (current != null &&
        current.expiresOn.isAfter(
          DateTime.now().add(const Duration(minutes: 1)),
        )) {
      return current.accessToken;
    }
    try {
      _result = await _client!.acquireTokenSilent(scopes: _scopes);
    } on MsalException {
      return '';
    }
    return _result!.accessToken;
  }

  Future<String> signIn() async {
    if (_client == null) await initialize();
    try {
      await _client!.signOut();
    } on MsalException {
      // There is no cached account to remove on a first-time sign-in.
    }
    _result = await _client!.acquireToken(
      scopes: _scopes,
      prompt: Prompt.selectAccount,
      authority: _authority,
    );
    return _result!.account.username ??
        _result!.account.name ??
        'Microsoft account';
  }

  Future<void> signOut() async {
    if (_client != null) await _client!.signOut();
    _result = null;
  }
}