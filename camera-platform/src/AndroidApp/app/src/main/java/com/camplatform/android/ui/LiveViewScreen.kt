package com.camplatform.android.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FiberManualRecord
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.rtsp.RtspMediaSource
import androidx.media3.ui.PlayerView
import androidx.navigation.NavController
import com.camplatform.android.CamPlatformApp
import kotlinx.coroutines.launch

/**
 * Live view screen backed by ExoPlayer RTSP source.
 * The RTSP URL is fetched from the gateway API; credentials are supplied by
 * the device owner and never guessed or brute-forced.
 */
@Composable
fun LiveViewScreen(nav: NavController, cameraId: Int) {
    val ctx = LocalContext.current
    val app = ctx.applicationContext as CamPlatformApp
    val scope = rememberCoroutineScope()

    var rtspUrl by remember { mutableStateOf<String?>(null) }
    var recording by remember { mutableStateOf(false) }
    var snackMessage by remember { mutableStateOf<String?>(null) }
    val snackState = remember { SnackbarHostState() }

    // Load camera details including RTSP URL from gateway
    LaunchedEffect(cameraId) {
        runCatching { app.api.cameraStatus(cameraId) }.onSuccess { status ->
            @Suppress("UNCHECKED_CAST")
            rtspUrl = (status["rtspUrl"] as? String)
        }
    }

    LaunchedEffect(snackMessage) {
        snackMessage?.let { snackState.showSnackbar(it); snackMessage = null }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackState) },
        topBar = {
            TopAppBar(
                title = { Text("Live View – Camera $cameraId") },
                actions = {
                    IconButton(onClick = {
                        scope.launch {
                            runCatching { app.api.command(cameraId, "captureSnapshot") }
                                .onSuccess { snackMessage = "Snapshot saved" }
                                .onFailure { snackMessage = "Snapshot failed: ${it.message}" }
                        }
                    }) { Icon(Icons.Default.PhotoCamera, "Snapshot") }

                    IconButton(onClick = {
                        scope.launch {
                            val method = if (recording) "stopRecording" else "startRecording"
                            runCatching { app.api.command(cameraId, method) }
                                .onSuccess { recording = !recording }
                                .onFailure { snackMessage = "Command failed: ${it.message}" }
                        }
                    }) {
                        Icon(
                            if (recording) Icons.Default.Stop else Icons.Default.FiberManualRecord,
                            if (recording) "Stop" else "Record",
                            tint = if (recording) Color.Red else LocalContentColor.current,
                        )
                    }
                },
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
            when {
                rtspUrl == null -> CircularProgressIndicator()
                rtspUrl!!.isBlank() -> Text("No RTSP endpoint configured for this camera.")
                else -> ExoPlayerRtspView(rtspUrl!!)
            }
        }
    }
}

@Composable
private fun ExoPlayerRtspView(rtspUrl: String) {
    val ctx = LocalContext.current
    val player = remember {
        ExoPlayer.Builder(ctx).build().apply {
            val source = RtspMediaSource.Factory()
                .setForceUseRtpTcp(true)         // TCP avoids packet loss on WiFi
                .createMediaSource(MediaItem.fromUri(rtspUrl))
            setMediaSource(source)
            prepare()
            playWhenReady = true
        }
    }
    DisposableEffect(Unit) { onDispose { player.release() } }

    AndroidView(
        factory = { PlayerView(it).apply { this.player = player } },
        modifier = Modifier.fillMaxSize(),
    )
}
