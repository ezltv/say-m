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

# --- HTML ARAYÜZ ---
html_code = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stok Asistanı (Hibrit Mod)</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; text-align: center; padding: 10px; background: #f4f6f9; color: #333; }
        .card { background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); margin-bottom: 20px; }
        
        /* MİKROFON BUTONU */
        .mic-btn { 
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; border: none; 
            width: 90px; height: 90px; border-radius: 50%; font-size: 35px; cursor: pointer; 
            box-shadow: 0 5px 15px rgba(56, 239, 125, 0.4); transition: transform 0.2s;
            user-select: none; -webkit-user-select: none;
            -webkit-tap-highlight-color: transparent;
        }
        .mic-btn:active { transform: scale(0.95); }
        .mic-btn.listening { animation: pulse 1.5s infinite; background: #ff416c; }
        @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(255, 65, 108, 0.7); } 70% { box-shadow: 0 0 0 20px rgba(255, 65, 108, 0); } 100% { box-shadow: 0 0 0 0 rgba(255, 65, 108, 0); } }

        .editor-box { display: none; margin-top: 20px; text-align: left; }
        textarea { width: 100%; height: 80px; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 16px; font-family: sans-serif; box-sizing: border-box; }
        
        .action-btns { margin-top: 10px; display: flex; gap: 10px; }
        .btn-confirm { flex: 1; background: #28a745; color: white; border: none; padding: 12px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 16px; }
        .btn-cancel { flex: 1; background: #dc3545; color: white; border: none; padding: 12px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 16px; }
        
        .log-item { background: #e9ecef; padding: 10px; margin: 5px 0; border-radius: 8px; font-size: 14px; text-align: left; border-left: 4px solid #11998e; }
        .btn-excel { background: #217346; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; margin-top: 10px; }
        audio { width: 100%; margin-top: 5px; height: 30px; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🎤 Stok Asistanı</h2>
        <div id="micArea">
            <p style="color:#888; font-size:14px;">Basılı Tut ve Konuş</p>
            <button id="micBtn" class="mic-btn" onmousedown="baslat(event)" onmouseup="bitir(event)" ontouchstart="baslat(event)" ontouchend="bitir(event)">🎙️</button>
            <div id="status" style="margin-top:10px; font-weight:bold; color:#555; height: 20px;">Hazır</div>
        </div>

        <div id="editorArea" class="editor-box">
            <label style="font-size:12px; font-weight:bold; color:#666;">📝 Anlaşılan Metin:</label>
            <textarea id="textBox" placeholder="Ses metne çevrilemediyse buraya yazabilirsin..."></textarea>
            
            <div style="margin-top:5px;">
                <label style="font-size:12px; font-weight:bold; color:#666;">🔊 Ses Kaydı:</label>
                <audio id="audioPreview" controls src=""></audio>
            </div>

            <div class="action-btns">
                <button class="btn-cancel" onclick="iptalEt()">❌ İptal</button>
                <button class="btn-confirm" onclick="sunucuyaGonder()">✅ Kaydet</button>
            </div>
        </div>
    </div>

    <div class="card">
        <h3>📊 Kayıtlar</h3>
        <div id="logArea"></div>
        <br>
        <a href="/indir_excel" class="btn-excel" target="_blank">📥 Excel İndir</a>
    </div>

    <script>
        let recognition;
        let mediaRecorder;
        let audioChunks = [];
        let isRecording = false;
        let currentAudioBlob = null;
        let final_transcript = '';

        // 1. Tarayıcı Motorunu Ayarla
        if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
            alert("Bu özellik için Google Chrome kullanmalısın.");
        } else {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SpeechRecognition();
            recognition.lang = 'tr-TR';
            recognition.continuous = true;     // Sürekli dinle
            recognition.interimResults = true; // Anlık tahminleri getir
            recognition.maxAlternatives = 1;
        }

        async function baslat(event) {
            if (isRecording) return;
            if (event) event.preventDefault();
            
            isRecording = true;
            final_transcript = '';
            
            document.getElementById("textBox").value = "";
            document.getElementById("micBtn").classList.add("listening");
            document.getElementById("status").innerText = "🔴 Kayıt Başladı...";

            // Yazı motorunu başlat (Hata verirse yut, durmasın)
            try { recognition.start(); } catch(e) { console.log("Mic zaten aktif"); }

            // Ses dosyası kaydını başlat
            audioChunks = [];
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                mediaRecorder.ondataavailable = event => { audioChunks.push(event.data); };
                mediaRecorder.start();
            } catch(e) {
                alert("Mikrofon izni verilmedi!");
            }

            // Metni Yakala (Canlı)
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
        }

        function bitir(event) {
            if (!isRecording) return;
            if (event) event.preventDefault();
            
            isRecording = false;
            document.getElementById("micBtn").classList.remove("listening");
            document.getElementById("status").innerText = "⏳ İşleniyor...";

            // KRİTİK NOKTA: Yazı motorunu HEMEN durdurma!
            // Google'dan son kelimelerin gelmesi için 1.5 saniye bekle.
            setTimeout(() => {
                recognition.stop(); 
                
                // Ses dosyasını durdur ve hazırla
                if(mediaRecorder && mediaRecorder.state !== "inactive") {
                    mediaRecorder.stop();
                }

                if(mediaRecorder) {
                    mediaRecorder.onstop = () => {
                        currentAudioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                        document.getElementById("audioPreview").src = URL.createObjectURL(currentAudioBlob);
                        
                        // Ekran değiştir
                        document.getElementById("micArea").style.display = "none";
                        document.getElementById("editorArea").style.display = "block";
                        
                        // Durum mesajını güncelle
                        const textVal = document.getElementById("textBox").value.trim();
                        if(textVal === "") {
                             document.getElementById("textBox").placeholder = "Metin otomatik gelmedi, buraya yazabilirsin...";
                        }
                    };
                }
            }, 1500); // 1.5 Saniye Gecikmeli Kapanış
        }

        function iptalEt() {
            document.getElementById("editorArea").style.display = "none";
            document.getElementById("micArea").style.display = "block";
            document.getElementById("status").innerText = "Hazır.";
            document.getElementById("textBox").value = "";
            final_transcript = "";
            currentAudioBlob = null;
        }

        function sunucuyaGonder() {
            const editedText = document.getElementById("textBox").value;
            
            // Boş metin kontrolünü kaldırdım, belki sadece ses atmak istersin
            // Ama yine de uyarı verelim
            if (editedText.length < 1 && !confirm("Metin kutusu boş. Sadece ses kaydedilsin mi?")) {
                return;
            }
            
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
                
                let playerHtml = "";
                if (data.ses_url) {
                    playerHtml = `<br><audio controls src="${data.ses_url}"></audio>`;
                }
                
                const logHtml = `<div class="log-item"><b>${data.urun}</b><br>Adet: ${data.adet} | Kağıt: ${data.kagit}${playerHtml}</div>`;
                document.getElementById("logArea").innerHTML = logHtml + document.getElementById("logArea").innerHTML;
            })
            .catch(err => {
                alert("Hata: " + err);
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
            # Supabase'e yükle
            supabase.storage.from_("ses-kayitlari").upload(dosya_ismi, ses_dosyasi.read(), {"content-type": "audio/webm"})
            # Linki al
            public_ses_url = supabase.storage.from_("ses-kayitlari").get_public_url(dosya_ismi)
        except Exception as e:
            print(f"Ses yükleme hatası: {e}")

    # --- JARGON ÇEVİRİCİ ---
    # 1. Miktar
    miktar = 1
    miktar_match = re.search(r'(\d+)\s*(ADET|TANE)', metin)
    if miktar_match:
        miktar = int(miktar_match.group(1))
        metin_temiz = metin.replace(miktar_match.group(0), "") 
    else:
        metin_temiz = metin

    # 2. Kağıt No
    kagit = "-"
    kagit_match = re.search(r'KAĞIT\s*(\d+)', metin_temiz)
    if kagit_match:
        kagit = kagit_match.group(1)
        metin_temiz = metin_temiz.replace(kagit_match.group(0), "")

    # 3. Plaka
    plaka_match = re.search(r'\b(\d{1,3})\s+(\d{3,4})\s+(\d{3,4})\b', metin_temiz)
    if plaka_match:
        yeni_format = f"HRS {plaka_match.group(1)} MM {plaka_match.group(2)}X{plaka_match.group(3)}"
        metin_temiz = metin_temiz.replace(plaka_match.group(0), yeni_format)

    # 4. Kelime Değiştirme
    sozluk = { 
        "A ": "HEA ", "B ": "HEB ", "ST 44": "S275JR", "ST 37": "S235JR", 
        "ST 52": "S355JR", "BOY": "MT", "PLAKA": "HRS", "ON": "10", "YÜZ": "100" 
    }
    for k, v in sozluk.items():
        metin_temiz = metin_temiz.replace(k, v)
        
    urun_adi = " ".join(metin_temiz.split())
    
    # Veritabanına Yaz
    veri = {
        "kagit_no": kagit,
        "urun_adi": urun_adi,
        "adet": miktar,
        "ham_ses": request.form.get("metin", ""), 
        "ses_url": public_ses_url
    }
    
    if SUPABASE_URL:
        supabase.table("stok_loglari").insert(veri).execute()
    
    return jsonify(veri)

@app.route("/indir_excel")
def indir_excel():
    if not SUPABASE_URL: return "Veritabanı bağlı değil"
    response = supabase.table("stok_loglari").select("*").order("created_at", desc=True).execute()
    df = pd.DataFrame(response.data)
    
    # Sütunları Türkçeleştir
    column_mapping = {
        "created_at": "TARİH",
        "kagit_no": "KAĞIT NO",
        "urun_adi": "ÜRÜN ADI",
        "adet": "ADET",
        "ham_ses": "GİRİLEN METİN",
        "ses_url": "SES KAYDI LİNKİ",
        "id": "ID"
    }
    df = df.rename(columns=column_mapping)
    
    df.to_excel("stok_sesli.xlsx", index=False)
    return send_file("stok_sesli.xlsx", as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
