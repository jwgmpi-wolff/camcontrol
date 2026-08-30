package com.camplatform.android.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.camplatform.android.CamPlatformApp
import com.camplatform.android.data.Camera

@Composable
fun CameraListScreen(nav: NavController) {
    val ctx = LocalContext.current
    val app = ctx.applicationContext as CamPlatformApp
    var cameras by remember { mutableStateOf<List<Camera>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        runCatching { app.api.listCameras() }
            .onSuccess { cameras = it }
            .onFailure { error = it.message }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("CamPlatform") },
                actions = {
                    IconButton(onClick = { nav.navigate("settings") }) {
                        Icon(Icons.Default.Settings, "Settings")
                    }
                },
            )
        },
    ) { padding ->
        Column(Modifier.padding(padding)) {
            error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(16.dp)) }
            if (cameras.isEmpty() && error == null) {
                Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) {
                    CircularProgressIndicator()
                }
            }
            LazyColumn {
                items(cameras) { cam ->
                    ListItem(
                        headlineContent = { Text(cam.name) },
                        supportingContent = { Text("${cam.ipAddress}  •  ${cam.status}") },
                        leadingContent = { Icon(Icons.Default.Videocam, null) },
                        modifier = Modifier.clickable { nav.navigate("live/${cam.id}") },
                    )
                    HorizontalDivider()
                }
            }
        }
    }
}
