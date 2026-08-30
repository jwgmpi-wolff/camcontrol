package com.camplatform.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.camplatform.android.ui.CameraListScreen
import com.camplatform.android.ui.LiveViewScreen
import com.camplatform.android.ui.RecordingsScreen
import com.camplatform.android.ui.SettingsScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                val nav = rememberNavController()
                NavHost(nav, startDestination = "cameras") {
                    composable("cameras") { CameraListScreen(nav) }
                    composable("live/{cameraId}") { back ->
                        LiveViewScreen(nav, back.arguments?.getString("cameraId")?.toIntOrNull() ?: 0)
                    }
                    composable("recordings/{cameraId}") { back ->
                        RecordingsScreen(nav, back.arguments?.getString("cameraId")?.toIntOrNull() ?: 0)
                    }
                    composable("settings") { SettingsScreen(nav) }
                }
            }
        }
    }
}
