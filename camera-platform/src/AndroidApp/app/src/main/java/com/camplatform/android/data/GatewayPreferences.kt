package com.camplatform.android.data

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking

private val Context.dataStore by preferencesDataStore("settings")

class GatewayPreferences(private val ctx: Context) {
    private val BASE_URL = stringPreferencesKey("base_url")
    private val API_KEY  = stringPreferencesKey("api_key")

    fun getBaseUrl(): String = runBlocking {
        ctx.dataStore.data.first()[BASE_URL] ?: "http://192.168.1.x:5000"
    }

    fun getApiKey(): String = runBlocking {
        ctx.dataStore.data.first()[API_KEY] ?: ""
    }

    suspend fun save(baseUrl: String, apiKey: String) {
        ctx.dataStore.edit {
            it[BASE_URL] = baseUrl
            it[API_KEY]  = apiKey
        }
    }
}
