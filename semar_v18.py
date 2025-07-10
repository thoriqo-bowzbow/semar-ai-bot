# -*- coding: utf-8 -*-
# SEMAR AI v18.0 (No Pandas, Full AI)
# Deskripsi: Versi final yang membuang pandas untuk analisis dan menyerahkan data mentah
# sepenuhnya kepada Gemini untuk diinterpretasikan dan dihitung.

import os
import json
import re
from datetime import datetime
import google.generativeai as genai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, HttpError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)

# === BAGIAN KONFIGURASI ===
TELEGRAM_BOT_TOKEN = "7515399798:AAGEPxRUppPEeSrc7nvGc8b9sRrXNMeos54"
GOOGLE_API_KEY = "AIzaSyCl7-RKbPxFB7QEQtjWvb0VTR8MyuWYOUY"
SEARCH_ENGINE_ID = "d182542e29d7344fb"

SPREADSHEETS = {
    "keuangan": "1PGAIXmiEjIk2fZ-bQ-sb_0BSvfDciNOc1ah_6oWISFw",
    "kasmasuk": "1eYAzwQvtXGRY_rzXJCu44PfjWhSJ0pwTIwqHN0slr5I",
    "kaskeluar": "1IMIg0kQQ1fGkZdvS2qdSLoVII4ZDx7aDCjXCVgxxvMw",
}

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDENTIALS_FILE = 'kredensial/credentials.json'
TOKEN_FILE = 'kredensial/token.json'
# ===========================

# --- FUNGSI ALAT (TOOLBOX) ---

def get_sheets_service():
    creds = None
    try:
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        return build('sheets', 'v4', credentials=creds)
    except Exception as e:
        print(f"❌ Gagal otentikasi Google Sheets: {e}")
        return None

def spreadsheet_analyzer(user_query: str) -> str:
    """Fungsi utama untuk tugas spreadsheet, kini sepenuhnya berbasis AI."""
    print(f"--- Menganalisis Perintah Spreadsheet (Mode Full AI): \"{user_query}\"")
    
    # Otak #1: Menerjemahkan perintah natural ke parameter
    parser_model = genai.GenerativeModel('gemini-1.5-flash')
    parser_prompt = f"""
    Anda adalah parser cerdas. Ekstrak 'spreadsheet_name' dan 'sheet_name' dari permintaan.
    Spreadsheet valid: {list(SPREADSHEETS.keys())}
    Contoh: "total pemasukan di kasmasuk sheet juli" -> {{"spreadsheet_name": "kasmasuk", "sheet_name": "juli"}}
    Permintaan: "{user_query}"
    JSON:
    """
    try:
        response = parser_model.generate_content(parser_prompt)
        params = json.loads(response.text.strip().replace('`', '').replace('json', ''))
        spreadsheet_name = params.get("spreadsheet_name")
        sheet_name = params.get("sheet_name")
        if not all([spreadsheet_name, sheet_name]):
            return "Perintah kurang jelas. Sebutkan nama spreadsheet dan sheet."
    except Exception as e:
        return f"Gagal memahami perintah Anda: {e}"

    spreadsheet_id = SPREADSHEETS.get(spreadsheet_name.lower())
    if not spreadsheet_id: return f"Nama spreadsheet '{spreadsheet_name}' tidak ada di konfigurasi."
    
    service = get_sheets_service()
    if not service: return "Tidak bisa terhubung ke Google Sheets."

    try:
        # Langkah 1: Bot Mengumpulkan Semua Data Mentah
        print(f"--> Langkah 1: Mengambil data mentah dari '{sheet_name}'...")
        range_name = f"{sheet_name}!A:Z"
        result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        if not values: return f"Tidak ada data sama sekali di sheet '{sheet_name}'."

        # Langkah 2: Menyerahkan Segalanya ke Otak Analis AI
        print("--> Langkah 2: Menyerahkan data mentah dan pertanyaan ke Gemini untuk dianalisis...")
        analyzer_model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Mengubah data mentah menjadi string yang mudah dibaca AI
        data_string = "\n".join([", ".join(map(str, row)) for row in values])

        analyzer_prompt = f"""
        Anda adalah seorang akuntan dan analis data yang sangat teliti.
        Berikut adalah data mentah dari sebuah spreadsheet. Data ini mungkin tidak rapi dan memiliki banyak baris serta kolom kosong.
        
        DATA MENTAH:
        ---
        {data_string}
        ---
        
        TUGAS ANDA:
        1.  Pahami permintaan pengguna: "{user_query}".
        2.  Dari data mentah di atas, temukan kolom yang paling relevan dengan permintaan pengguna (misalnya, kolom "MASUK" untuk "total pemasukan").
        3.  Abaikan teks atau simbol mata uang (seperti 'Rp'). Fokus hanya pada angka.
        4.  Jumlahkan semua angka yang valid di kolom yang telah Anda identifikasi tersebut.
        5.  Sajikan jawaban akhir dalam satu kalimat yang jelas dan sopan.

        Contoh Jawaban: "Tentu, total pemasukan dari kolom 'MASUK' di sheet 'Juli' adalah Rp 4.293.000."
        
        JAWABAN ANDA:
        """
        
        final_response = analyzer_model.generate_content(analyzer_prompt)
        return final_response.text

    except Exception as e:
        return f"Terjadi kesalahan saat memproses data: {e}"

# --- Alur Kerja Bot (Handlers Manual) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = None
    keyboard = [
        [InlineKeyboardButton("📊 Analisis Spreadsheet", callback_data='mode_spreadsheet')],
        [InlineKeyboardButton("🌐 Cari di Internet", callback_data='mode_search')],
        [InlineKeyboardButton("💬 Ngobrol Biasa", callback_data='mode_chat')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Halo! Saya SEMAR AI v18.0. Silakan pilih mode:",
        reply_markup=reply_markup,
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['mode'] = query.data
    mode_text = {
        'mode_spreadsheet': "**Mode Spreadsheet**.\nKetik perintah analisis Anda.",
        'mode_search': "**Mode Pencarian Internet**.\nKetik apa yang ingin Anda cari.",
        'mode_chat': "**Mode Ngobrol**.\nSilakan mulai percakapan."
    }
    await query.edit_message_text(text=f"Anda sekarang dalam {mode_text.get(query.data)}\n\nKirim /start untuk kembali ke menu utama.", parse_mode='Markdown')

async def main_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get('mode')
    user_text = update.message.text
    if not mode:
        await update.message.reply_text("Silakan pilih mode terlebih dahulu dengan mengirim /start.")
        return

    await context.bot.send_message(chat_id=update.effective_chat.id, text="⏳ Memproses...")
    
    result_text = "Maaf, terjadi kesalahan."
    if mode == 'mode_spreadsheet':
        result_text = spreadsheet_analyzer(user_text)
    elif mode == 'mode_search':
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(f"Jawab pertanyaan ini berdasarkan pencarian internet: {user_text}")
        result_text = response.text
    elif mode == 'mode_chat':
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(user_text)
        result_text = response.text
        
    await update.message.reply_text(result_text, parse_mode='Markdown')

def main():
    if "MASUKKAN_" in TELEGRAM_BOT_TOKEN:
        print("❌ KESALAHAN: Isi dulu kunci API di 'BAGIAN KONFIGURASI'.")
        return

    print("--- SEMAR AI v18.0 (No Pandas, Full AI) Dimulai ---")
    genai.configure(api_key=GOOGLE_API_KEY)
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_message_handler))
    
    print("Bot sedang mendengarkan... Kirim /start untuk memulai.")
    application.run_polling()

if __name__ == '__main__':
    main()