from flask import Flask, render_template_string, request, jsonify, send_file
from supabase import create_client, Client
import pandas as pd
import re
import os
import time

app = Flask(__name__)

# --- AYARLAR ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("UYARI: Supabase ayarları eksik!")

# --- HTML ARAYÜZ (ZOMBİ MODLU) ---
html_code = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stok Asistanı V4</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; text-align: center; padding: 10px; background: #f4f6f9; color: #333; }
        .card { background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); margin-bottom: 20px; }
        
        .mic-btn { 
            background: #007bff; color: white; border: none; 
            width: 100%; height: 80px; border-radius: 10px; font-size: 24px; cursor: pointer; 
            box-shadow: 0 4px 10px rgba(0,123,255,0.3); transition: all 0.2s; font-weight: bold;
        }
        .mic-btn.recording { background: #dc3545; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }

        .editor-box { display: none; margin-top: 20px; text-align: left; }
        textarea { width: 100%; height: 100px; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 18px; font-family: sans-serif; box-sizing: border-box; }
        
        .action-btns { margin-top: 10px; display: flex; gap: 10px; }
        .btn-confirm { flex: 1; background: #28a745; color: white; border: none; padding: 15px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 18px; }
        .btn-cancel { flex: 1; background: #6c757d; color: white; border: none; padding: 15px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 18px; }
        
        .log-item { background: #e9ecef; padding: 10px; margin: 5px 0; border-radius: 8px; font-size: 14px; text-align: left; border-left: 4px solid #007bff; }
        .btn-excel { background: #217346; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; margin-top: 10px; }
        
        #debugLog { font-size: 10px; color: red; text-align: left; margin-top: 10px; display:block; }
    </style>
</head>
<body>
    <div class="card">
        <h2>📦 Stok Sayım V4</h2>
        
        <div id="micArea">
            <button id="micBtn" class="mic-btn" onclick="kaydiYonet()">🎙️ BAŞLAT</button>
            <div id="status" style="margin-top:15px; font-weight:bold; color:#555;">Hazır</div>
            <div id="debugLog"></div>
        </div>

        <div id="editorArea" class="editor-box">
            <textarea id="textBox" placeholder="Ses buraya yazılacak..."></textarea>
            <div style="margin-top:5px;"><audio id="audioPreview" controls style="width:100%; height:30px;"></audio></div>
            <div class="action-btns">
                <button class="btn-cancel" onclick="iptalEt()">Sil</button>
                <button class="btn-confirm" onclick="sunucuyaGonder()">KAYDET</button>
            </div>
        </div>
    </div>

    <div class="card">
        <h3>Son Kayıtlar</h3>
        <div id="logArea"></div>
        <a href="/indir_excel" class="btn-excel" target="_blank">📥 Excel İndir</a>
    </div>

    <script>
        let recognition;
        let mediaRecorder;
        let audioChunks = [];
        let isRecording = false;
        let currentAudioBlob = null;
        let manuelDurdurma = false; // Kullanıcı mı durdurdu yoksa telefon mu kesti?

        function logYaz(mesaj) {
            document.getElementById("debugLog").innerText = mesaj;
            console.log(mesaj);
        }

        // 1. Yazı Motoru Kurulumu
        if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
            alert("Lütfen Chrome kullanın.");
        } else {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SpeechRecognition();
            recognition.lang = 'tr-TR';
            recognition.continuous = true;     
            recognition.interimResults = true; 
        }

        // --- ZOMBİ MODU (Sürekli Dinle) ---
        recognition.onend = function() {
            if (isRecording && !manuelDurdurma) {
                logYaz("♻️ Mic kapandı, zorla tekrar açılıyor...");
                try { recognition.start(); } catch(e) {}
            } else {
                logYaz("🛑 Dinleme tamamen bitti.");
            }
        };

        recognition.onresult = function(event) {
            let final = "";
            let interim = "";
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    final += event.results[i][0].transcript;
                } else {
                    interim += event.results[i][0].transcript;
                }
            }
            // DUYDUĞUNU ANINDA KUTUYA BAS (Beklemek yok)
            let mevcutYazi = document.getElementById("textBox").value;
            // Sadece yeni geleni ekle veya güncelle
            if(final) {
                document.getElementById("textBox").value = document.getElementById("textBox").value + " " + final;
            }
            // Geçici yazıyı status bar'da göster
            if(interim) {
                document.getElementById("status").innerText = "👂 " + interim;
            }
        };
        
        recognition.onerror = function(event) {
            logYaz("HATA: " + event.error);
        };

        function kaydiYonet() {
            if (!isRecording) baslat();
            else bitir();
        }

        async function baslat() {
            isRecording = true;
            manuelDurdurma = false;
            document.getElementById("textBox").value = "";
            document.getElementById("micBtn").innerHTML = "⏹️ BİTİR";
            document.getElementById("micBtn").classList.add("recording");
            document.getElementById("status").innerText = "🔴 Dinliyor...";

            try { recognition.start(); } catch(e) {}

            // Ses Kaydı
            audioChunks = [];
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                mediaRecorder.ondataavailable = event => { audioChunks.push(event.data); };
                mediaRecorder.start();
            } catch(e) { logYaz("Mic izni yok!"); }
        }

        function bitir() {
            manuelDurdurma = true; // Evet, kullanıcı bilerek durdurdu
            isRecording = false;
            
            document.getElementById("micBtn").innerHTML = "🎙️ BAŞLAT";
            document.getElementById("micBtn").classList.remove("recording");
            document.getElementById("status").innerText = "İşleniyor...";

            recognition.stop();
            if(mediaRecorder) mediaRecorder.stop();

            setTimeout(() => {
                if(mediaRecorder) {
                    currentAudioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    document.getElementById("audioPreview").src = URL.createObjectURL(currentAudioBlob);
                }
                document.getElementById("micArea").style.display = "none";
                document.getElementById("editorArea").style.display = "block";

                // Eğer kutu boşsa
                if(document.getElementById("textBox").value.trim() === "") {
                    document.getElementById("textBox").placeholder = "Ses anlaşılamadı. Buraya elle yazabilirsin.";
                }
            }, 1000);
        }

        function iptalEt() {
            document.getElementById("editorArea").style.display = "none";
            document.getElementById("micArea").style.display = "block";
            document.getElementById("status").innerText = "Hazır.";
            document.getElementById("textBox").value = "";
            document.getElementById("debugLog").innerText = "";
        }

        function sunucuyaGonder() {
            const editedText = document.getElementById("textBox").value;
            if (editedText.length < 1) {
                if(!confirm("Yazı yok, sadece ses gönderilsin mi?")) return;
            }
            
            document.getElementById("status").innerText = "Gönderiliyor...";
            const formData = new FormData();
            if (currentAudioBlob) formData.append("ses_dosyasi", currentAudioBlob, "kayit.webm");
            formData.append("metin", editedText);

            fetch('/analiz', { method: 'POST', body: formData })
            .then(response => response.json())
            .then(data => {
                iptalEt(); 
                document.getElementById("status").innerText = "✅ Kaydedildi!";
                
                let playerHtml = data.ses_url ? `<br><audio controls src="${data.ses_url}"></audio>` : "";
                const logHtml = `<div class="log-item"><b>${data.urun}</b><br>Adet: ${data.adet} | Kağıt: ${data.kagit}${playerHtml}</div>`;
                document.getElementById("logArea").innerHTML = logHtml + document.getElementById("logArea").innerHTML;
            })
            .catch(err => { alert("Hata: " + err); iptalEt(); });
        }
    </script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(html_code)

@app.route("/analiz", methods=["POST"])
def analiz():
    metin = request.form.get("metin", "").upper()
    ses_dosyasi = request.files.get("ses_dosyasi")
    
    public_ses_url = ""
    if ses_dosyasi and SUPABASE_URL:
        try:
            dosya_ismi = f"kayit_{int(time.time())}.webm"
            supabase.storage.from_("ses-kayitlari").upload(dosya_ismi, ses_dosyasi.read(), {"content-type": "audio/webm"})
            public_ses_url = supabase.storage.from_("ses-kayitlari").get_public_url(dosya_ismi)
        except Exception as e:
            print(f"Ses yükleme hatası: {e}")

    # --- AYRIŞTIRMA (Boş metin gelse bile patlamaz) ---
    miktar = 1
    miktar_match = re.search(r'(\d+)\s*(ADET|TANE)', metin)
    if miktar_match:
        miktar = int(miktar_match.group(1))
        metin_temiz = metin.replace(miktar_match.group(0), "") 
    else:
        metin_temiz = metin

    kagit = "-"
    kagit_match = re.search(r'KAĞIT\s*(\d+)', metin_temiz)
    if kagit_match:
        kagit = kagit_match.group(1)
        metin_temiz = metin_temiz.replace(kagit_match.group(0), "")

    plaka_match = re.search(r'\b(\d{1,3})\s+(\d{3,4})\s+(\d{3,4})\b', metin_temiz)
    if plaka_match:
        yeni_format = f"HRS {plaka_match.group(1)} MM {plaka_match.group(2)}X{plaka_match.group(3)}"
        metin_temiz = metin_temiz.replace(plaka_match.group(0), yeni_format)

    sozluk = { "A ": "HEA ", "B ": "HEB ", "ST 44": "S275JR", "ST 37": "S235JR", "ST 52": "S355JR", "BOY": "MT", "PLAKA": "HRS", "ON": "10", "YÜZ": "100" }
    for k, v in sozluk.items():
        metin_temiz = metin_temiz.replace(k, v)
        
    urun_adi = " ".join(metin_temiz.split())
    if not urun_adi: urun_adi = "BELİRSİZ (SES KAYDINI DİNLE)"

    veri = {
        "kagit_no": kagit, "urun_adi": urun_adi, "adet": miktar,
        "ham_ses": request.form.get("metin", ""), "ses_url": public_ses_url
    }
    
    if SUPABASE_URL:
        supabase.table("stok_loglari").insert(veri).execute()
    
    return jsonify(veri)

@app.route("/indir_excel")
def indir_excel():
    if not SUPABASE_URL: return "Veritabanı bağlı değil"
    response = supabase.table("stok_loglari").select("*").order("created_at", desc=True).execute()
    df = pd.DataFrame(response.data)
    
    column_mapping = {
        "created_at": "TARİH", "kagit_no": "KAĞIT NO", "urun_adi": "ÜRÜN ADI",
        "adet": "ADET", "ham_ses": "GİRİLEN METİN", "ses_url": "SES KAYDI LİNKİ", "id": "ID"
    }
    df = df.rename(columns=column_mapping)
    df.to_excel("stok_sesli.xlsx", index=False)
    return send_file("stok_sesli.xlsx", as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
