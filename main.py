import streamlit as st
import google.generativeai as genai
from pypdf import PdfReader
import time
import plotly.graph_objects as go
from fpdf import FPDF
import os
import requests
import tempfile
import re
from streamlit_mic_recorder import speech_to_text 

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
if "fetched_models" not in st.session_state: st.session_state.fetched_models = []
# [YENİ] Süre takibi için değişken
if "question_start_time" not in st.session_state: st.session_state.question_start_time = None

# --- Sidebar ---
with st.sidebar:
    try:
        st.image("logo2.jpg", width=250) 
    except:
        st.warning("Logo dosyası bulunamadı (logo2.jpg)")

    st.header("⚙️ Ayarlar")
    
    api_key_input = st.text_input("Google API Key", type="password")
    
    if api_key_input:
        if not st.session_state.fetched_models:
            if st.button("🔄 Modelleri Getir (Bağlan)"):
                try:
                    genai.configure(api_key=api_key_input)
                    models = genai.list_models()
                    valid_models = []
                    for m in models:
                        if 'generateContent' in m.supported_generation_methods:
                            valid_models.append(m.name)
                    
                    if valid_models:
                        valid_models.sort(key=lambda x: "flash" not in x)
                        st.session_state.fetched_models = valid_models
                        st.success("Modeller yüklendi!")
                    else:
                        st.error("Hiç model bulunamadı.")
                except Exception as e:
                    st.error(f"Bağlantı hatası: {e}")

    options = st.session_state.fetched_models if st.session_state.fetched_models else ["models/gemini-1.5-flash", "gemini-1.5-flash"]
    selected_model_name = st.selectbox("Kullanılacak Model", options)

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

# --- Güvenlik ---
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# --- Mülakat Başlatma ---
if start_interview:
    if not api_key_input or not cv_file:
        st.error("Eksik bilgi: API Key veya CV yok.")
    else:
        st.session_state.report_data = None
        
        genai.configure(api_key=api_key_input)
        
        cv_text = get_pdf_text(cv_file)
        portfolio_text = ""
        if portfolio_files:
            for file in portfolio_files:
                portfolio_text += f"\n--- DOSYA: {file.name} ---\n{get_pdf_text(file)}\n"
        try:
            system_prompt = f"""
            === SİSTEM KİMLİĞİ VE AMACI ===
            SEN, "AI-Powered Senior Talent Assessment Agent" (Yapay Zeka Destekli Kıdemli Yetenek Değerlendirme Uzmanı) OLARAK GÖREV YAPMAKTASIN. 
            AMACIN: Aşağıda sunulan veri setlerini analiz ederek, aday ile gerçekçi, yetkinlik bazlı ve yapılandırılmış bir teknik mülakat gerçekleştirmektir.
            
            === BAĞLAMSAL VERİ SETİ (CONTEXT) ===
            1. HEDEF POZİSYON (JD): {job_description}
            2. ADAY PROFİLİ (CV): {cv_text}
            3. EK DÖKÜMANLAR (PORTFOLYO): {portfolio_text}
            
            === YÜRÜTME ALGORİTMASI (EXECUTION PROTOCOL) ===
            
            ADIM 1: DİNAMİK ROL ADAPTASYONU (DYNAMIC PERSONA)
            - İş İlanını (JD) analiz et ve sektörü belirle (Örn: Yazılım, Eğitim, Finans).
            - İlgili sektöre uygun "Hiring Manager" (İşe Alım Yöneticisi) kimliğine bürün.
            - Dil ve Ton Ayarı: Sektörel jargon kullan (Örn: Yazılımcı için "Tech Stack", Öğretmen için "Pedagojik Formasyon").
            
            ADIM 2: YETKİNLİK SORGULAMA STRATEJİSİ (CBI - Competency Based Interviewing)
            - Adayın beyanlarını asla yüzeyden kabul etme. "Derinlemesine Sorgulama" (Deep-Dive) yap.
            - STAR Metodolojisi Entegrasyonu (Implicit Guidance): Adaya doğrudan "STAR kullan" demek yerine, sorularınla onu yönlendir.
            - Tutarlılık Analizi: CV'deki iddialar ile sohbet sırasındaki cevaplar arasındaki tutarsızlıkları yakala.
            
            ADIM 3: SENARYO BAZLI TEST (SITUATIONAL JUDGEMENT)
            - Adayı teorik bilgiden çıkarıp pratik uygulamaya yönlendir.
            - Anlık kriz senaryoları üret (Örn: "Sistem çöktü", "Veli şikayet etti") ve çözüm reflekslerini ölç.
            
            === KISITLAMALAR VE KURALLAR (CONSTRAINTS) ===
            1. TEK SORU PRENSİBİ: Bilişsel yükü yönetmek için her seferinde SADECE BİR soru sor.
            2. OBJEKTİFLİK: Duygusal tepkiler verme, analitik ve profesyonel kal.
            3. KOPYALA-YAPIŞTIR ENGELİ: Adayın yapay veya ezber cevap verdiğini hissedersen, "Bunu kendi deneyiminle örneklendir" diyerek müdahale et.
            
            === BAŞLATMA ===
            Analizini tamamla, belirlediğin kimliğe bürün, kendini profesyonelce tanıt ve CV/Portfolyo analizine dayalı en kritik ilk sorunu yönelt.
            """
            
            welcome_text = """
            **👋 Mülakat Simülasyonuna Hoş Geldiniz!**

            Bu mülakat, yapay zeka destekli bir simülasyon üzerinden gerçekleştirilecektir. Amaç, sizi tanımak ve deneyimlerinizi daha iyi anlayabilmektir; stres yaratmak değil.

            ℹ️ **İşleyiş:**
            * Mülakat sırasında sorulara ister **yazarak** ister **konuşarak** cevap verebilirsiniz.
            * 🎤 **Mikrofon:** Butona bir kez bastığınızda kayıt başlar, tekrar bastığınızda kayıt durur. Tarayıcınız sesinizi otomatik olarak yazıya çevirecektir.
            * ⏳ **Süre:** Her bir soru için maksimum 5 dakikalık bir süre bulunmaktadır. **5 dakika içinde cevap vermezseniz sistem mülakatı sonlandıracaktır.**
            * 💡 **İpucu:** Sorulara kendi deneyimlerinizi yansıtan, samimi ve açık cevaplar vermeniz yeterlidir.

            *Not: Yapay zeka, insan kaynaklarının yerini almaz; yalnızca değerlendirme sürecini destekleyen bir araç olarak kullanılmaktadır.*
            
            **Size iyi bir mülakat deneyimi dileriz, başarılar! 🍀**
            """

            model = genai.GenerativeModel(model_name=selected_model_name, safety_settings=safety_settings)
            chat = model.start_chat(history=[])
            st.session_state.chat_session = chat
            
            chat.send_message(system_prompt)
            response = chat.send_message("ANALİZİNİ TAMAMLA VE MÜLAKATI BAŞLAT. Şimdi belirlenen kimliğe bürün, kendini tanıt ve adaya ilk sorunu sor.")
            
            st.session_state.messages = [
                {"role": "assistant", "content": welcome_text},
                {"role": "assistant", "content": response.text}
            ]
            
            # [YENİ] Sayacı Başlat (İlk soru için)
            st.session_state.question_start_time = time.time()
            
            st.success(f"Başladı! (Model: {selected_model_name})")
        except Exception as e: st.error(f"Başlatma Hatası: {e}")

# --- Sohbet Akışı ---
if st.session_state.chat_session:
    for message in st.session_state.messages:
        role = "user" if message["role"] == "user" else "assistant"
        with st.chat_message(role):
            st.write(message["content"])

    if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
        # Süre uyarısını göster
        st.caption("⏳ Bu soruya cevap vermek için 5 dakikanız var.")
        
        with st.expander("💡 Takıldınız mı? İpucu Alın"):
            if st.button("AI Koçundan Yardım İste"):
                with st.spinner("Koç soruyu analiz ediyor..."):
                    try:
                        coach_model = genai.GenerativeModel(selected_model_name)
                        last_question = st.session_state.messages[-1]["content"]
                        hint_prompt = f"Adaya şu soru için cevabı söylemeden bir ipucu ver: {last_question}"
                        hint_response = coach_model.generate_content(hint_prompt)
                        st.info(f"🔑 **İpucu:** {hint_response.text}")
                    except: st.warning("İpucu alınamadı.")

    col_mic, col_text = st.columns([1, 5])
    
    user_input = None
    
    with col_mic:
        st.write("Cevabını Konuş:")
        text_from_mic = speech_to_text(
            language='tr',
            start_prompt="🎤 Başlat",
            stop_prompt="⏹️ Durdur",
            just_once=True,
            key='STT'
        )
    
    if text_from_mic:
        user_input = text_from_mic
        st.info(f"🎤 Algılanan: {user_input}")

    text_input = st.chat_input("Veya yazarak cevapla...")
    if text_input: user_input = text_input

    # --- SÜRE KONTROLÜ VE CEVAP İŞLEME ---
    if user_input:
        # 1. Süreyi Kontrol Et
        current_time = time.time()
        # Eğer start_time yoksa (örn. sayfa yeni açıldıysa) şimdiki zamanı alıp geç
        start_time = st.session_state.get('question_start_time', current_time) 
        elapsed_time = current_time - start_time
        time_limit = 300  # 5 dakika = 300 saniye

        if elapsed_time > time_limit:
            # SÜRE DOLDUYSA
            st.error(f"⚠️ Süre Doldu! (Geçen süre: {int(elapsed_time/60)} dakika). Mülakat sonlandırılıyor.")
            st.session_state.messages.append({"role": "user", "content": "Süre doldu, cevap veremedim."}) # Loglara düşsün
            st.session_state.finish_requested = True
            st.rerun()
        else:
            # SÜRE İÇİNDEYSE -> İşleme Devam Et
            st.session_state.messages.append({"role": "user", "content": user_input})
            if text_input:
                with st.chat_message("user"): st.write(user_input)

            with st.spinner("Yapay Zeka düşünüyor..."):
                try:
                    if st.session_state.messages[-1]["role"] != "assistant":
                        response = st.session_state.chat_session.send_message(user_input)
                        ai_text = response.text
                        st.session_state.messages.append({"role": "assistant", "content": ai_text})
                        
                        # [YENİ] Yapay zeka cevap verince, YENİ SORU İÇİN sayacı sıfırla
                        st.session_state.question_start_time = time.time()
                        
                        with st.chat_message("assistant"):
                            st.write(ai_text)
                            audio_path = text_to_speech(ai_text)
                            if audio_path: st.audio(audio_path, format="audio/mp3", autoplay=True)
                except Exception as e: st.error(f"Hata: {e}")

# --- Raporlama ---
if st.session_state.finish_requested and st.session_state.chat_session:
    with st.spinner("Mülakat bitti, analiz yapılıyor..."):
        max_retries = 3
        retry_count = 0
        success = False
        
        while retry_count < max_retries and not success:
            try:
                report_prompt = """
                MÜLAKAT BİTTİ. Detaylı analiz yap.
                🚨 KURAL: EĞER ADAY CEVAP VERMEDİYSE VEYA SÜRE DOLDUYSA PUAN 0 OLSUN.
                FORMAT:
                SKOR: (0-100 arası sadece sayı)
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
                success = True
            except Exception as e:
                if "429" in str(e):
                    retry_count += 1
                    time.sleep(10)
                else: break

        if success:
            score = 0
            decision = "Belirsiz"
            
            score_match = re.search(r"SKOR[:\s*]*(\d+)", full_text, re.IGNORECASE)
            if score_match: score = int(score_match.group(1))
            
            decision_match = re.search(r"KARAR[:\s*]*(.+)", full_text, re.IGNORECASE)
            if decision_match: decision = decision_match.group(1).strip()

            categories = ["TEKNİK", "İLETİŞİM", "PROBLEM_ÇÖZME", "TEORİK_BİLGİ", "POTANSİYEL"]
            values = []
            for cat in categories:
                cat_match = re.search(rf"{cat}[:\s*]*(\d+)", full_text, re.IGNORECASE)
                if cat_match: values.append(int(cat_match.group(1)))
                else: values.append(50)
            
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
        else:
            st.error("Rapor oluşturulamadı.")

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
        fig = go.Figure(data=go.Scatterpolar(r=data['values'], theta=data['categories'], fill='toself', name='Aday'))
        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with col_text:
        st.info(data['text'])
        try:
            pdf_bytes = create_pdf_report(data)
            st.download_button(label="📄 Raporu İndir (PDF)", data=pdf_bytes, file_name="mulakat_karnesi.pdf", mime="application/pdf")
        except Exception as e: st.error(f"PDF Hatası: {e}")
