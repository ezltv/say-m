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

# --- HTML ARAYÜZ (AÇ-KAPA MANTIKLI) ---
html_code = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stok Asistanı V3</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; text-align: center; padding: 10px; background: #f4f6f9; color: #333; }
        .card { background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); margin-bottom: 20px; }
        
        /* MİKROFON BUTONU (KARE YAPTIM DAHA RAHAT BASILSIN) */
        .mic-btn { 
            background: #007bff; color: white; border: none; 
            width: 120px; height: 60px; border-radius: 10px; font-size: 20px; cursor: pointer; 
            box-shadow: 0 4px 10px rgba(0,123,255,0.3); transition: all 0.2s;
            font-weight: bold;
        }
        .mic-btn.recording { 
            background: #dc3545; /* Kayıttayken Kırmızı Olsun */
            animation: pulse 1.5s infinite; 
        }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }

        .editor-box { display: none; margin-top: 20px; text-align: left; }
        textarea { width: 100%; height: 80px; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 16px; font-family: sans-serif; box-sizing: border-box; }
        
        .action-btns { margin-top: 10px; display: flex; gap: 10px; }
        .btn-confirm { flex: 1; background: #28a745; color: white; border: none; padding: 12px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 16px; }
        .btn-cancel { flex: 1; background: #6c757d; color: white; border: none; padding: 12px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 16px; }
        
        .log-item { background: #e9ecef; padding: 10px; margin: 5px 0; border-radius: 8px; font-size: 14px; text-align: left; border-left: 4px solid #007bff; }
        .btn-excel { background: #217346; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; margin-top: 10px; }
        
        /* HATA GÜNLÜĞÜ (DEBUG) */
        #debugLog { font-size: 10px; color: #999; text-align: left; margin-top: 20px; border-top: 1px solid #ddd; padding-top: 10px; display:none; }
    </style>
</head>
<body>
    <div class="card">
        <h2>📦 Stok Sayım V3</h2>
        
        <div id="micArea">
            <p id="instruction" style="color:#666;">Mikrofona bas, konuş, tekrar bas.</p>
            <button id="micBtn" class="mic-btn" onclick="kaydiYonet()">🎙️ BAŞLAT</button>
            <div id="status" style="margin-top:15px; font-weight:bold; color:#555; min-height: 20px;">Hazır</div>
        </div>

        <div id="editorArea" class="editor-box">
            <label>📝 Metni Kontrol Et:</label>
            <textarea id="textBox"></textarea>
            
            <div style="margin-top:5px;">
                <audio id="audioPreview" controls style="width:100%; height:30px;"></audio>
            </div>

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

    <div id="debugLog"><b>Sistem Logları:</b><br></div>

    <script>
        let recognition;
        let mediaRecorder;
        let audioChunks = [];
        let isRecording = false;
        let currentAudioBlob = null;
        let final_transcript = '';

        // Ekrana hata yazdırma fonksiyonu (Senin sorunu anlamamız için)
        function logYaz(mesaj) {
            console.log(mesaj);
            const logDiv = document.getElementById("debugLog");
            logDiv.style.display = "block";
            logDiv.innerHTML += mesaj + "<br>";
        }

        // Tarayıcı Kontrolü
        if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
            alert("Lütfen Chrome kullanın.");
            logYaz("HATA: SpeechRecognition bulunamadı.");
        } else {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SpeechRecognition();
            recognition.lang = 'tr-TR';
            recognition.continuous = true; 
            recognition.interimResults = true; 
            logYaz("Sistem hazır. Chrome algılandı.");
        }

        // AÇ - KAPA FONKSİYONU
        function kaydiYonet() {
            if (!isRecording) {
                baslat();
            } else {
                bitir();
            }
        }

        async function baslat() {
            isRecording = true;
            final_transcript = '';
            document.getElementById("textBox").value = "";
            
            const btn = document.getElementById("micBtn");
            btn.innerHTML = "⏹️ BİTİR";
            btn.classList.add("recording");
            document.getElementById("status").innerText = "🔴 Dinliyorum... Konuşabilirsin.";
            document.getElementById("instruction").innerText = "İşin bitince butona tekrar bas.";

            // 1. Yazı Motoru
            try { 
                recognition.start(); 
                logYaz("Yazı motoru başlatıldı.");
            } catch(e) { 
                logYaz("Mic zaten açık olabilir: " + e); 
            }

            // 2. Ses Kaydı
            audioChunks = [];
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                mediaRecorder.ondataavailable = event => { audioChunks.push(event.data); };
                mediaRecorder.start();
                logYaz("Ses kaydı başlatıldı.");
            } catch(e) {
                alert("Mikrofon izni verilmeli!");
                logYaz("HATA: Mikrofon izni yok.");
            }

            // Yazı geldikçe kutuya bas
            recognition.onresult = function(event) {
                let interim_transcript = '';
                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        final_transcript += event.results[i][0].transcript;
                    } else {
                        interim_transcript += event.results[i][0].transcript;
                    }
                }
                document.getElementById("textBox").value = final_transcript + interim_transcript;
            };

            recognition.onerror = function(event) {
                logYaz("HATA (Google): " + event.error);
                if(event.error === 'no-speech') {
                    // Ses yoksa bile kapatma, bekle
                    logYaz("Ses algılanmadı uyarısı yoksayıldı.");
                }
            };
        }

        function bitir() {
            isRecording = false;
            const btn = document.getElementById("micBtn");
            btn.innerHTML = "🎙️ BAŞLAT";
            btn.classList.remove("recording");
            document.getElementById("status").innerText = "⏳ İşleniyor... Bekle.";
            document.getElementById("instruction").innerText = "Mikrofona bas, konuş, tekrar bas.";

            logYaz("Durdurma komutu verildi.");

            // Motorları durdur
            recognition.stop();
            if(mediaRecorder) mediaRecorder.stop();

            if(mediaRecorder) {
                mediaRecorder.onstop = () => {
                    logYaz("Ses dosyası oluşturuldu.");
                    currentAudioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    document.getElementById("audioPreview").src = URL.createObjectURL(currentAudioBlob);
                    
                    // Ekran değiştir
                    document.getElementById("micArea").style.display = "none";
                    document.getElementById("editorArea").style.display = "block";
                    
                    if(document.getElementById("textBox").value.trim() === "") {
                         document.getElementById("status").innerText = "⚠️ Yazı gelmedi, elle giriniz.";
                         logYaz("UYARI: Google metin döndürmedi.");
                    }
                };
            }
        }

        function iptalEt() {
            document.getElementById("editorArea").style.display = "none";
            document.getElementById("micArea").style.display = "block";
            document.getElementById("status").innerText = "Hazır.";
            document.getElementById("textBox").value = "";
            logYaz("İşlem iptal edildi.");
        }

        function sunucuyaGonder() {
            const editedText = document.getElementById("textBox").value;
            logYaz("Sunucuya gönderiliyor: " + editedText);
            
            document.getElementById("status").innerText = "🚀 Gönderiliyor...";
            const formData = new FormData();
            
            if (currentAudioBlob) {
                formData.append("ses_dosyasi", currentAudioBlob, "kayit.webm");
            }
            formData.append("metin", editedText);

            fetch('/analiz', { method: 'POST', body: formData })
            .then(response => response.json())
            .then(data => {
                iptalEt(); 
                document.getElementById("status").innerText = "✅ Kayıt Başarılı!";
                logYaz("Kayıt başarılı ID: " + data.urun_adi);
                
                let playerHtml = data.ses_url ? `<br><audio controls src="${data.ses_url}"></audio>` : "";
                const logHtml = `<div class="log-item"><b>${data.urun}</b><br>Adet: ${data.adet} | Kağıt: ${data.kagit}${playerHtml}</div>`;
                document.getElementById("logArea").innerHTML = logHtml + document.getElementById("logArea").innerHTML;
            })
            .catch(err => {
                alert("Hata: " + err);
                logYaz("Sunucu Hatası: " + err);
                iptalEt();
            });
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

    # --- JARGON ÇEVİRİCİ ---
    miktar = 1
    miktar_match = re.search(r'(\d+)\s*(ADET|TANE)', metin)
    if miktar_match:
        miktar = int(miktar_match.group(1))
        metin = metin.replace(miktar_match.group(0), "") 

    kagit = "-"
    kagit_match = re.search(r'KAĞIT\s*(\d+)', metin)
    if kagit_match:
        kagit = kagit_match.group(1)
        metin = metin.replace(kagit_match.group(0), "")

    plaka_match = re.search(r'\b(\d{1,3})\s+(\d{3,4})\s+(\d{3,4})\b', metin)
    if plaka_match:
        yeni_format = f"HRS {plaka_match.group(1)} MM {plaka_match.group(2)}X{plaka_match.group(3)}"
        metin = metin.replace(plaka_match.group(0), yeni_format)

    sozluk = { "A ": "HEA ", "B ": "HEB ", "ST 44": "S275JR", "ST 37": "S235JR", "ST 52": "S355JR", "BOY": "MT", "PLAKA": "HRS", "ON": "10", "YÜZ": "100" }
    for k, v in sozluk.items():
        metin = metin.replace(k, v)
        
    urun_adi = " ".join(metin.split())
    
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
