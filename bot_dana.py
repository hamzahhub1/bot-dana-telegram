import time
import random
import string
from datetime import datetime
import telebot
from telebot import types
import pymongo

# ==================== KONFIGURASI ====================
BOT_TOKEN = "9225079811:AAEm_Lvf6y9iUBhqofMKrXiYKhYVHCojNCQ"
ADMIN_ID = "5173482211"

MONGO_URI = "mongodb+srv://akbarcahyawigunaamirhamzah_db_user:db_HmhuSJeNKstY0KSG@keysmousebot.7dktb65.mongodb.net/?retryWrites=true&w=majority"

NO_DANA = "08979104406"
NAMA_DANA = "Akbar Cahyawiguna"
HARGA = "Rp 5.000"
DURASI_HARI = 3

# ==================== KONEKSI MONGO DB ====================
client = pymongo.MongoClient(MONGO_URI)
db = client["dana_bot_db"]
users_col = db["users"]
vouchers_col = db["vouchers"]

bot = telebot.TeleBot(BOT_TOKEN)

def generate_key(prefix="VIP", length=8):
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-" + ''.join(random.choice(chars) for _ in range(length))

# ==================== PERINTAH USER ====================

@bot.message_handler(commands=['start', 'buy', 'beli'])
def handle_buy(message):
    name = message.from_user.first_name or "Pengguna"
    text = (
        f"Halo *{name}*! 👋\n\n"
        f"💳 *PEMBAYARAN VIA DANA*\n"
        f"• Produk: *Akses Premium {DURASI_HARI} Hari*\n"
        f"• Harga: *{HARGA}*\n\n"
        f"📌 *Tujuan Pembayaran:*\n"
        f"• **Nomor DANA:** `{NO_DANA}`\n"
        f"• **A.N.:** *{NAMA_DANA}*\n\n"
        f"📩 *Cara Konfirmasi:*\n"
        f"Silakan transfer ke nomor di atas lalu **KIRIM FOTO BUKTI TRANSFER** ke chat bot ini."
    )
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def handle_proof_photo(message):
    user_id = str(message.chat.id)
    user_name = message.from_user.first_name or "User"
    username = f"@{message.from_user.username}" if message.from_user.username else "Tidak Ada Username"

    file_id = message.photo[-1].file_id

    markup = types.InlineKeyboardMarkup()
    btn_approve = types.InlineKeyboardButton("✅ Setujui (Kirim Key)", callback_data=f"app_{user_id}")
    btn_reject = types.InlineKeyboardButton("❌ Tolak", callback_data=f"rej_{user_id}")
    markup.add(btn_approve, btn_reject)

    caption_admin = (
        f"📩 *BUKTI PEMBAYARAN BARU*\n\n"
        f"👤 Nama: *{user_name}*\n"
        f"🔗 Username: {username}\n"
        f"🆔 ID Telegram: `{user_id}`\n"
        f"💰 Tagihan: *{HARGA}*\n\n"
        f"Klik tombol di bawah untuk memverifikasi:"
    )

    try:
        bot.send_photo(ADMIN_ID, file_id, caption=caption_admin, parse_mode="Markdown", reply_markup=markup)
        bot.reply_to(message, "⏳ Bukti pembayaran Anda berhasil dikirim ke Admin. Harap tunggu verifikasi sebentar...")
    except Exception as e:
        bot.reply_to(message, f"❌ Gagal mengirim bukti ke Admin: {e}")

# ==================== FITUR VERIFIKASI ADMIN ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith(('app_', 'rej_')))
def handle_admin_action(call):
    if str(call.message.chat.id) != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Akses Ditolak!")
        return

    action, target_user_id = call.data.split('_')

    if action == "app":
        now = int(time.time())
        duration_seconds = DURASI_HARI * 24 * 3600

        user_data = users_col.find_one({"_id": target_user_id})
        current_expire = user_data.get("expires_at", 0) if user_data else 0

        if current_expire > now:
            new_expires_at = current_expire + duration_seconds
        else:
            new_expires_at = now + duration_seconds

        new_key = generate_key()

        users_col.update_one(
            {"_id": target_user_id},
            {"$set": {"key": new_key, "expires_at": new_expires_at}},
            upsert=True
        )

        vouchers_col.insert_one({
            "_id": new_key,
            "days": DURASI_HARI,
            "is_used": True,
            "used_by": target_user_id,
            "created_at": now
        })

        expire_date_str = datetime.fromtimestamp(new_expires_at).strftime('%Y-%m-%d %H:%M:%S WIB')

        msg_user = (
            f"🎉 *PEMBAYARAN DANA DISETUJUI!*\n\n"
            f"🔑 License Key Anda: `{new_key}`\n"
            f"⏳ Masa Aktif: {DURASI_HARI} Hari\n"
            f"📅 Berlaku Sampai: `{expire_date_str}`\n\n"
            f"Gunakan key di atas untuk masuk ke aplikasi."
        )
        try:
            bot.send_message(target_user_id, msg_user, parse_mode="Markdown")
            bot.edit_message_caption("✅ *PEMBAYARAN DISETUJUI & KEY TERKIRIM*", chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")
            bot.answer_callback_query(call.id, "Sukses menyetujui dan mengirim key!")
        except Exception as e:
            bot.answer_callback_query(call.id, f"Gagal kirim ke user: {e}")

    elif action == "rej":
        msg_reject = "❌ Bukti pembayaran DANA Anda ditolak / tidak valid. Silakan hubungi Admin jika ada kekeliruan."
        try:
            bot.send_message(target_user_id, msg_reject)
            bot.edit_message_caption("❌ *PEMBAYARAN DITOLAK*", chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")
            bot.answer_callback_query(call.id, "Pembayaran ditolak.")
        except Exception as e:
            bot.answer_callback_query(call.id, f"Gagal respon: {e}")

# ==================== FITUR CEK SISA AKTIF ====================

@bot.message_handler(commands=['cek', 'mykey'])
def handle_check(message):
    chat_id = str(message.chat.id)
    user_data = users_col.find_one({"_id": chat_id})

    if not user_data:
        bot.reply_to(message, "❌ Anda belum memiliki key aktif.")
        return

    key = user_data["key"]
    expires_at = user_data["expires_at"]
    now = int(time.time())

    if now > expires_at:
        bot.reply_to(message, "❌ Masa berlaku key Anda telah **KADALUARSA**.", parse_mode="Markdown")
    else:
        sisa_jam = round((expires_at - now) / 3600, 1)
        expire_date_str = datetime.fromtimestamp(expires_at).strftime('%Y-%m-%d %H:%M:%S WIB')
        
        bot.reply_to(
            message,
            f"🔑 *Key Aktif Anda:* `{key}`\n"
            f"⏳ *Sisa Waktu:* ±{sisa_jam} Jam\n"
            f"📅 *Kadaluarsa:* `{expire_date_str}`",
            parse_mode="Markdown"
        )

if __name__ == "__main__":
    print("[+] Bot Telegram DANA (MongoDB Cloud) Aktif!")
    bot.infinity_polling()
