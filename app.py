from flask import Flask, render_template_string, request, jsonify, send_file
from supabase import create_client, Client
import speech_recognition as sr
from pydub import AudioSegment
import pandas as pd
import re
import os
import time
import io

app = Flask(__name__)

# --- AYARLAR ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("UYARI: Supabase ayarları eksik!")

# --- HTML ARAYÜZ (SERVER-SIDE KAYIT) ---
html_code = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stok Asistanı (Server Mod)</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; text-align: center; padding: 10px; background: #f4f6f9; color: #333; }
        .card { background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); margin-bottom: 20px; }
        
        .mic-btn { 
            background: #007bff; color: white; border: none; 
            width: 100%; height: 80px; border-radius: 12px; font-size: 22px; cursor: pointer; 
            box-shadow: 0 4px 10px rgba(0,123,255,0.3); transition: all 0.2s; font-weight: bold;
            display: flex; align-items: center; justify-content: center; gap: 10px;
        }
        .mic-btn.recording { background: #dc3545; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.8; } 100% { opacity: 1; } }

        .editor-box { display: none; margin-top: 20px; text-align: left; }
        textarea { width: 100%; height: 100px; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 18px; font-family: sans-serif; box-sizing: border-box; }
        
        .action-btns { margin-top: 10px; display: flex; gap: 10px; }
        .btn-confirm { flex: 1; background: #28a745; color: white; border: none; padding: 15px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 18px; }
        .btn-cancel { flex: 1; background: #6c757d; color: white; border: none; padding: 15px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 18px; }
        
        .log-item { background: #e9ecef; padding: 10px; margin: 5px 0; border-radius: 8px; font-size: 14px; text-align: left; border-left: 4px solid #007bff; }
        .btn-excel { background: #217346; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; margin-top: 10px; }

        /* YÜKLENİYOR SPINNER */
        .loader { border: 5px solid #f3f3f3; border-top: 5px solid #007bff; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; display: none; margin: 10px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="card">
        <h2>📡 Stok Sayım (Server)</h2>
        
        <div id="micArea">
            <button id="micBtn" class="mic-btn" onclick="kaydiYonet()">
                <span>🎙️</span> <span>KAYDI BAŞLAT</span>
            </button>
            <div id="loader" class="loader"></div>
            <div id="status" style="margin-top:10px; font-weight:bold; color:#555;">Hazır</div>
        </div>

        <div id="editorArea" class="editor-box">
            <textarea id="textBox" placeholder="Ses sunucuda işleniyor..."></textarea>
            <div class="action-btns">
                <button class="btn-cancel" onclick="iptalEt()">İPTAL</button>
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
        let mediaRecorder;
        let audioChunks = [];
        let isRecording = false;

        async function kaydiYonet() {
            if (!isRecording) {
                // BAŞLAT
                isRecording = true;
                audioChunks = [];
                document.getElementById("micBtn").innerHTML = "<span>⏹️</span> <span>KAYDI BİTİR</span>";
                document.getElementById("micBtn").classList.add("recording");
                document.getElementById("status").innerText = "🔴 Kayıt yapılıyor...";
                
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    mediaRecorder.ondataavailable = event => { audioChunks.push(event.data); };
                    mediaRecorder.start();
                } catch(e) {
                    alert("Mikrofon hatası: " + e);
                    isRecording = false;
                }
            } else {
                // BİTİR VE GÖNDER
                isRecording = false;
                document.getElementById("micBtn").innerHTML = "<span>🎙️</span> <span>KAYDI BAŞLAT</span>";
                document.getElementById("micBtn").classList.remove("recording");
                document.getElementById("status").innerText = "⏳ Sunucuya gönderiliyor...";
                document.getElementById("loader").style.display = "block";
                
                mediaRecorder.stop();
                mediaRecorder.onstop = () => {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    sesiCozumle(audioBlob);
                };
            }
        }

        function sesiCozumle(blob) {
            const formData = new FormData();
            formData.append("ses_dosyasi", blob, "kayit.webm");

            fetch('/sesi_yaziya_cevir', { method: 'POST', body: formData })
            .then(response => response.json())
            .then(data => {
                document.getElementById("loader").style.display = "none";
                document.getElementById("micArea").style.display = "none";
                document.getElementById("editorArea").style.display = "block";
                
                if(data.hata) {
                    document.getElementById("textBox").value = "";
                    document.getElementById("textBox").placeholder = "Hata: " + data.hata;
                } else {
                    document.getElementById("textBox").value = data.metin;
                }
            })
            .catch(err => {
                alert("Sunucu hatası: " + err);
                document.getElementById("loader").style.display = "none";
            });
        }

        function iptalEt() {
            document.getElementById("editorArea").style.display = "none";
            document.getElementById("micArea").style.display = "block";
            document.getElementById("status").innerText = "Hazır.";
            document.getElementById("textBox").value = "";
        }

        function sunucuyaGonder() {
            const editedText = document.getElementById("textBox").value;
            if (editedText.length < 1) { alert("Metin boş!"); return; }
            
            document.getElementById("status").innerText = "Veritabanına işleniyor...";
            
            fetch('/kaydet', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ metin: editedText })
            })
            .then(response => response.json())
            .then(data => {
                iptalEt(); 
                document.getElementById("status").innerText = "✅ Kayıt Başarılı!";
                const logHtml = `<div class="log-item"><b>${data.urun_adi}</b><br>Adet: ${data.adet} | Kağıt: ${data.kagit_no}</div>`;
                document.getElementById("logArea").innerHTML = logHtml + document.getElementById("logArea").innerHTML;
            });
        }
    </script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(html_code)

@app.route("/sesi_yaziya_cevir", methods=["POST"])
def sesi_yaziya_cevir():
    if 'ses_dosyasi' not in request.files:
        return jsonify({"hata": "Dosya yok"})
    
    file = request.files['ses_dosyasi']
    
    try:
        # 1. WebM dosyasını WAV'a çevir (Python tarafında)
        audio = AudioSegment.from_file(file)
        wav_io = io.BytesIO()
        audio.export(wav_io, format="wav")
        wav_io.seek(0)
        
        # 2. Google Speech Recognition (Backend)
        r = sr.Recognizer()
        with sr.AudioFile(wav_io) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="tr-TR")
            
        return jsonify({"metin": text.upper()})
        
    except Exception as e:
        print("Hata:", e)
        return jsonify({"hata": "Ses anlaşılamadı veya format sorunu."})

@app.route("/kaydet", methods=["POST"])
def kaydet():
    data = request.json
    metin = data.get("metin", "").upper()
    
    # --- AYRIŞTIRMA MANTIĞI ---
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
    if not urun_adi: urun_adi = "BELİRSİZ"

    veri = {
        "kagit_no": kagit, "urun_adi": urun_adi, "adet": miktar,
        "ham_ses": metin, "ses_url": "Server-Mode"
    }
    
    if SUPABASE_URL:
        supabase.table("stok_loglari").insert(veri).execute()
    
    return jsonify(veri)

@app.route("/indir_excel")
def indir_excel():
    if not SUPABASE_URL: return "Veritabanı bağlı değil"
    response = supabase.table("stok_loglari").select("*").order("created_at", desc=True).execute()
    df = pd.DataFrame(response.data)
    df.to_excel("stok_server.xlsx", index=False)
    return send_file("stok_server.xlsx", as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
