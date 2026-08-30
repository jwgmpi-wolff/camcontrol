package com.camplatform.android

import android.app.Application
import com.camplatform.android.data.GatewayPreferences
import com.camplatform.android.data.RetrofitClient

class CamPlatformApp : Application() {
    lateinit var prefs: GatewayPreferences
    lateinit var api: com.camplatform.android.data.CameraApiService

    override fun onCreate() {
        super.onCreate()
        prefs = GatewayPreferences(this)
        api = RetrofitClient.create(prefs)
    }
}
