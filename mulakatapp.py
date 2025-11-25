import streamlit as st
import google.generativeai as genai
from pypdf import PdfReader
import time
import plotly.graph_objects as go
from fpdf import FPDF
import os
import requests
import tempfile

# --- Sayfa Ayarları ---
st.set_page_config(page_title="AI Mülakat Simülasyonu", layout="wide")
st.title("🤖 AI Mülakat Simülasyonu")

# --- 1. FONKSİYONLAR ---
def check_and_download_fonts():
    fonts = {
        "Roboto-Regular.ttf": "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf",
        "Roboto-Bold.ttf": "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf"
    }
    for font_name, url in fonts.items():
        if not os.path.exists(font_name):
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    with open(font_name, 'wb') as f:
                        f.write(response.content)
            except: pass

def tr_to_en(text):
    if not text: return ""
    tr_map = {'ğ':'g','Ğ':'G','ş':'s','Ş':'S','ı':'i','İ':'I','ç':'c','Ç':'C','ü':'u','Ü':'U','ö':'o','Ö':'O'}
    for tr, en in tr_map.items(): text = text.replace(tr, en)
    return text

# --- SES FONKSİYONLARI (GÜVENLİ IMPORT) ---
def get_audio_recorder():
    # Kütüphane yoksa hata vermek yerine None döndürür
    try:
        from audio_recorder_streamlit import audio_recorder
        return audio_recorder
    except ImportError: return None

def speech_to_text(audio_bytes):
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_audio:
            tmp_audio.write(audio_bytes)
            tmp_path = tmp_audio.name
        with sr.AudioFile(tmp_path) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="tr-TR")
        os.remove(tmp_path)
        return text
    except Exception as e: return None

def text_to_speech(text):
    try:
        from gTTS import gTTS
        tts = gTTS(text=text, lang='tr')
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_mp3:
            tts.save(tmp_mp3.name)
            return tmp_mp3.name
    except: return None

def create_pdf_report(data):
    check_and_download_fonts()
    use_font = 'Arial'
    if os.path.exists('Roboto-Bold.ttf') and os.path.exists('Roboto-Regular.ttf'):
        use_font = 'Roboto'

    class PDF(FPDF):
        def header(self):
            if use_font == 'Roboto':
                try:
                    self.add_font('Roboto', 'B', 'Roboto-Bold.ttf', uni=True)
                    self.add_font('Roboto', '', 'Roboto-Regular.ttf', uni=True)
                except: pass
            self.set_font(use_font, 'B', 20)
            self.cell(0, 10, 'AI MULAKAT SONUC RAPORU', 0, 1, 'C')
            self.ln(10)
        def chapter_title(self, title):
            self.set_font(use_font, 'B', 14)
            self.set_fill_color(230, 230, 230)
            safe_title = title if use_font == 'Roboto' else tr_to_en(title)
            self.cell(0, 10, safe_title, 0, 1, 'L', fill=True)
            self.ln(4)
        def chapter_body(self, body):
            self.set_font(use_font, '', 11)
            safe_body = body if use_font == 'Roboto' else tr_to_en(body)
            if use_font == 'Arial': safe_body = safe_body.encode('latin-1', 'ignore').decode('latin-1')
            self.multi_cell(0, 6, safe_body)
            self.ln(5)

    pdf = PDF()
    if use_font == 'Roboto':
        try:
            pdf.add_font('Roboto', 'B', 'Roboto-Bold.ttf', uni=True)
            pdf.add_font('Roboto', '', 'Roboto-Regular.ttf', uni=True)
        except: pass
    pdf.add_page()
    
    pdf.set_font(use_font, 'B', 16)
    pdf.cell(0, 10, f"GENEL PUAN: {data['score']}/100", 0, 1, 'C')
    if "Olumlu" in data['decision']: pdf.set_text_color(0, 100, 0)
    else: pdf.set_text_color(200, 0, 0)
    safe_decision = data['decision'] if use_font == 'Roboto' else tr_to_en(data['decision'])
    pdf.cell(0, 10, f"KARAR: {safe_decision}", 0, 1, 'C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)
    
    pdf.chapter_title("YETKINLIK PUANLARI")
    pdf.set_font(use_font, '', 12)
    for cat, val in zip(data['categories'], data['values']):
        safe_cat = cat if use_font == 'Roboto' else tr_to_en(cat)
        pdf.cell(100, 8, f"- {safe_cat}", 0, 0)
        pdf.set_font(use_font, 'B', 12)
        pdf.cell(0, 8, f"{val}/100", 0, 1)
        pdf.set_font(use_font, '', 12)
    pdf.ln(10)
    
    pdf.chapter_title("YAPAY ZEKA DEGERLENDIRMESI")
    pdf.chapter_body(data['text'])
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        pdf.output(tmp_file.name)
        tmp_file.seek(0)
        pdf_bytes = tmp_file.read()
    return pdf_bytes

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Ayarlar")
    api_key = st.text_input("Google API Key", type="password")
    
    model_options = ["Önce API Key Girin"]
    if api_key:
        try:
            genai.configure(api_key=api_key)
            options = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    if "exp" not in m.name and "2.5" not in m.name: 
                        options.append(m.name)
            if options: model_options = options
        except: st.error("API Key geçersiz.")

    index = 0
    for i, name in enumerate(model_options):
        if "1.5" in name and "flash" in name: index = i; break
    selected_model = st.selectbox("Model Seçimi", model_options, index=index)

    with st.form("main_form"):
        st.info("Mülakat Detayları")
        job_description = st.text_area("İş İlanı (JD)", height=100)
        cv_file = st.file_uploader("CV (Zorunlu)", type="pdf")
        portfolio_files = st.file_uploader("Ek Dosyalar", type="pdf", accept_multiple_files=True)
        start_interview = st.form_submit_button("Mülakatı Başlat")
    
    st.markdown("---")
    if st.session_state.get('chat_session'):
        if st.button("🏁 Mülakatı Bitir ve Raporla", type="primary"):
            st.session_state['finish_requested'] = True

# --- Fonksiyonlar ---
def get_pdf_text(pdf_file):
    text = ""
    try:
        reader = PdfReader(pdf_file)
        for page in reader.pages: text += page.extract_text()
    except: pass
    return text

# --- Hafıza ---
if "messages" not in st.session_state: st.session_state.messages = [] 
if "chat_session" not in st.session_state: st.session_state.chat_session = None 
if "finish_requested" not in st.session_state: st.session_state.finish_requested = False
if "report_data" not in st.session_state: st.session_state.report_data = None 

# --- Güvenlik ---
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# --- Mülakat Başlatma ---
if start_interview:
    if not api_key or not cv_file:
        st.error("Eksik bilgi.")
    else:
        st.session_state.report_data = None
        genai.configure(api_key=api_key)
        cv_text = get_pdf_text(cv_file)
        portfolio_text = ""
        if portfolio_files:
            for file in portfolio_files:
                portfolio_text += f"\n--- DOSYA: {file.name} ---\n{get_pdf_text(file)}\n"
        try:
            system_prompt = f"""
            GÖREVİN: Verilen İŞ İLANI ({job_description}) için en uygun İşe Alım Yöneticisi ol.
            ADAY CV: {cv_text}
            EK DOSYALAR: {portfolio_text}
            STRATEJİ:
            1. Role gir.
            2. Zorlayıcı sorular sor.
            3. Senaryo sor.
            Kısa ve net ol. Tek soru sor.
            """
            model = genai.GenerativeModel(model_name=selected_model, safety_settings=safety_settings)
            chat = model.start_chat(history=[])
            st.session_state.chat_session = chat
            chat.send_message(system_prompt)
            response = chat.send_message("Mülakatı başlat.")
            st.session_state.messages = [{"role": "assistant", "content": response.text}]
            st.success("Başladı!")
        except Exception as e: st.error(f"Hata: {e}")

# --- Sohbet Akışı ---
if st.session_state.chat_session:
    for message in st.session_state.messages:
        role = "user" if message["role"] == "user" else "assistant"
        with st.chat_message(role):
            st.write(message["content"])

    # --- HİBRİT GİRDİ ALANI (SES + YAZI) ---
    col_mic, col_text = st.columns([1, 5])
    
    audio_bytes = None
    audio_recorder_func = get_audio_recorder() # Güvenli Çağrı
    
    if audio_recorder_func:
        with col_mic:
            audio_bytes = audio_recorder_func(
                text="",
                recording_color="#e8b62c",
                neutral_color="#6aa36f",
                icon_name="microphone",
                icon_size="2x",
            )
    else:
        with col_mic:
            st.warning("⚠️ Ses modülü yüklenemedi")

    user_input = None
    if audio_bytes:
        with st.spinner("Ses işleniyor..."):
            user_input = speech_to_text(audio_bytes)
            if user_input: st.info(f"🎤 {user_input}")
    
    # Yazı girişi her zaman aktif
    text_input = st.chat_input("Cevabın...")
    if text_input: user_input = text_input

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        if text_input: # Ses değilse ekrana bas
            with st.chat_message("user"): st.write(user_input)

        with st.spinner("..."):
            try:
                # Eğer son mesaj asistana aitse tekrar sorma (Çift cevap önleme)
                if st.session_state.messages[-1]["role"] != "assistant":
                    response = st.session_state.chat_session.send_message(user_input)
                    ai_text = response.text
                    st.session_state.messages.append({"role": "assistant", "content": ai_text})
                    
                    with st.chat_message("assistant"):
                        st.write(ai_text)
                        # Seslendirme
                        audio_path = text_to_speech(ai_text)
                        if audio_path:
                            st.audio(audio_path, format="audio/mp3", autoplay=True)
            except Exception as e: st.error(f"Hata: {e}")

# --- Raporlama ---
if st.session_state.finish_requested and st.session_state.chat_session:
    with st.spinner("Analiz ediliyor..."):
        try:
            report_prompt = """
            MÜLAKAT BİTTİ. Detaylı analiz yap.
            
            🚨 KURAL: EĞER ADAY CEVAP VERMEDİYSE ("...", "bilmem") PUAN 0 OLSUN.
            
            FORMAT:
            SKOR: (0-100)
            KARAR: (Olumlu / Olumsuz)
            -- PUAN DETAYLARI --
            TEKNİK: (0-100)
            İLETİŞİM: (0-100)
            PROBLEM_ÇÖZME: (0-100)
            TEORİK_BİLGİ: (0-100)
            POTANSİYEL: (0-100)
            -- SÖZEL RAPOR --
            (Kısa bir özet yaz)
            """
            response = st.session_state.chat_session.send_message(report_prompt)
            full_text = response.text
            
            try: score = int(full_text.split("SKOR:")[1].split("\n")[0].strip())
            except: score = 0
            try: decision = full_text.split("KARAR:")[1].split("\n")[0].strip()
            except: decision = "Belirsiz"
            
            categories = ["TEKNİK", "İLETİŞİM", "PROBLEM_ÇÖZME", "TEORİK_BİLGİ", "POTANSİYEL"]
            values = []
            for cat in categories:
                try: val = int(full_text.split(f"{cat}:")[1].split("\n")[0].strip())
                except: val = 50
                values.append(val)
            
            try: verbal_report = full_text.split("-- SÖZEL RAPOR --")[1]
            except: verbal_report = full_text

            st.session_state.report_data = {
                "score": score,
                "decision": decision,
                "categories": categories,
                "values": values,
                "text": verbal_report
            }
            st.session_state.finish_requested = False
            st.rerun()

        except Exception as e: st.error(f"Hata: {e}")

# --- EKRAN: Rapor ve PDF ---
if st.session_state.report_data:
    data = st.session_state.report_data
    
    st.markdown("---")
    st.header("📊 Mülakat Sonuç Karnesi")
    
    c1, c2 = st.columns(2)
    c1.metric("Genel Puan", f"{data['score']}/100")
    if "Olumlu" in data['decision']: c2.success(f"Karar: {data['decision']}")
    else: c2.error(f"Karar: {data['decision']}")
    
    st.progress(data['score'])
    
    col_chart, col_text = st.columns([1, 1])
    with col_chart:
        fig = go.Figure(data=go.Scatterpolar(
            r=data['values'], theta=data['categories'], fill='toself', name='Aday'
        ))
        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    
    with col_text:
        st.info(data['text'])
        
        st.markdown("### 📥 Raporu İndir")
        try:
            pdf_bytes = create_pdf_report(data)
            st.download_button(
                label="📄 Raporu PDF Olarak İndir",
                data=pdf_bytes,
                file_name="mulakat_karnesi.pdf",
                mime="application/pdf"
            )
        except Exception as e:
            st.error(f"PDF oluşturulamadı: {e}")
