package tw.mars.trainmath;

import android.speech.tts.TextToSpeech;
import android.speech.tts.Voice;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;

@CapacitorPlugin(name = "OfflineSpeech")
public class OfflineSpeechPlugin extends Plugin implements TextToSpeech.OnInitListener {
    private TextToSpeech speech;
    private boolean initialized = false;
    private Voice localVoice;
    private final List<PluginCall> waiting = new ArrayList<>();

    @Override public void load() {
        try { speech = new TextToSpeech(getContext(), this); }
        catch (Exception exception) { initialized = true; }
    }
    @Override public synchronized void onInit(int status) {
        if (status == TextToSpeech.SUCCESS && speech != null) {
            try {
                Set<Voice> voices = speech.getVoices();
                if (voices != null) for (Voice voice : voices) {
                    Locale locale = voice.getLocale();
                    if (!voice.isNetworkConnectionRequired() && "zh".equals(locale.getLanguage()) && "TW".equals(locale.getCountry())) {
                        if (localVoice == null || voice.getQuality() > localVoice.getQuality()) localVoice = voice;
                    }
                }
                if (localVoice != null) {
                    if (speech.setVoice(localVoice) == TextToSpeech.ERROR) localVoice = null;
                    speech.setSpeechRate(0.82f);
                }
            } catch (Exception exception) { localVoice = null; }
        }
        initialized = true;
        for (PluginCall call : waiting) resolveStatus(call);
        waiting.clear();
    }
    private void resolveStatus(PluginCall call) {
        JSObject result = new JSObject();
        result.put("available", localVoice != null);
        result.put("offline", localVoice != null);
        result.put("language", "zh-TW");
        call.resolve(result);
    }
    @PluginMethod public synchronized void getStatus(PluginCall call) {
        if (!initialized) waiting.add(call); else resolveStatus(call);
    }
    @PluginMethod public synchronized void speak(PluginCall call) {
        String text = call.getString("text", "").trim();
        if (localVoice == null || speech == null || text.isEmpty() || text.length() > 3000) {
            call.reject("LOCAL_VOICE_UNAVAILABLE"); return;
        }
        speech.stop();
        int result = speech.speak(text, TextToSpeech.QUEUE_FLUSH, null, "train-math-guidance");
        if (result == TextToSpeech.ERROR) call.reject("LOCAL_SPEECH_FAILED"); else call.resolve();
    }
    @PluginMethod public synchronized void stop(PluginCall call) {
        if (speech != null) speech.stop(); call.resolve();
    }
    @Override protected void handleOnPause() { if (speech != null) speech.stop(); }
    @Override protected void handleOnDestroy() {
        if (speech != null) { speech.stop(); speech.shutdown(); }
        for (PluginCall call : waiting) call.reject("APP_CLOSED");
        waiting.clear();
    }
}
