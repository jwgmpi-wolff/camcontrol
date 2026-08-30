package com.wolff.camcontrol;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.webkit.*;
import android.view.WindowManager;
import android.widget.EditText;

public class MainActivity extends Activity {
    private static final String PREF_URL = "gateway_url";
    private static final String DEFAULT_URL = "http://10.0.0.112:8080/";
    private WebView web;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setDomStorageEnabled(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);

        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView v, String url) {}
            @Override
            public void onReceivedError(WebView v, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) showUrlDialog("Cannot reach gateway. Enter your PC IP:");
            }
        });

        String saved = getPreferences(MODE_PRIVATE).getString(PREF_URL, null);
        if (saved == null) {
            showUrlDialog("Enter your PC gateway URL (default: " + DEFAULT_URL + "):");
        } else {
            web.loadUrl(saved);
        }
    }

    private void showUrlDialog(String msg) {
        EditText input = new EditText(this);
        input.setText(getPreferences(MODE_PRIVATE).getString(PREF_URL, DEFAULT_URL));
        input.setSelectAllOnFocus(true);
        new AlertDialog.Builder(this)
            .setTitle("CamControl")
            .setMessage(msg)
            .setView(input)
            .setPositiveButton("Connect", (d, w) -> {
                String url = input.getText().toString().trim();
                if (!url.startsWith("http")) url = "http://" + url;
                if (!url.contains(":")) url = url.replaceAll("/$","") + ":8080/";
                getPreferences(MODE_PRIVATE).edit().putString(PREF_URL, url).apply();
                web.loadUrl(url);
            })
            .setNegativeButton("Use Default", (d, w) -> {
                getPreferences(MODE_PRIVATE).edit().putString(PREF_URL, DEFAULT_URL).apply();
                web.loadUrl(DEFAULT_URL);
            })
            .setCancelable(false).show();
    }
}
