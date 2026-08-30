package com.camplatform.android.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.camplatform.android.CamPlatformApp
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(nav: NavController) {
    val ctx = LocalContext.current
    val app = ctx.applicationContext as CamPlatformApp
    val scope = rememberCoroutineScope()

    var url by remember { mutableStateOf(app.prefs.getBaseUrl()) }
    var key by remember { mutableStateOf(app.prefs.getApiKey()) }
    var obscureKey by remember { mutableStateOf(true) }
    var saved by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = { nav.popBackStack() }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(Modifier.padding(padding).padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            OutlinedTextField(
                value = url,
                onValueChange = { url = it; saved = false },
                label = { Text("Gateway URL") },
                placeholder = { Text("http://192.168.1.x:5000") },
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = key,
                onValueChange = { key = it; saved = false },
                label = { Text("API Key (optional)") },
                visualTransformation = if (obscureKey) PasswordVisualTransformation() else VisualTransformation.None,
                trailingIcon = {
                    TextButton(onClick = { obscureKey = !obscureKey }) {
                        Text(if (obscureKey) "Show" else "Hide")
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            )
            FilledButton(
                onClick = {
                    scope.launch {
                        app.prefs.save(url.trim(), key.trim())
                        saved = true
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            ) { Text(if (saved) "Saved ✓" else "Save") }

            HorizontalDivider()
            Text("Camera", style = MaterialTheme.typography.titleMedium)
            _InfoRow("Model", "YI Outdoor Camera 1080p (YHS.3017)")
            _InfoRow("FCC ID", "2AFIB-YHS3017")
            _InfoRow("Manufacturer", "Shanghai Xiaoyi Technology Co.,Ltd.")
            _InfoRow("Connection type", "WiFi / local RTSP (if exposed)")
            Text(
                "This app reads from whatever RTSP URL the gateway reports. No camera " +
                "firmware is modified. Set RTSP_URL in the gateway .env to the stream " +
                "URL provided by your camera or vendor documentation.",
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun _InfoRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth()) {
        Text(label, Modifier.width(140.dp), style = MaterialTheme.typography.bodyMedium)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun FilledButton(onClick: () -> Unit, modifier: Modifier, content: @Composable RowScope.() -> Unit) =
    Button(onClick = onClick, modifier = modifier, content = content)
