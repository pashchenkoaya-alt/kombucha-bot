import json
import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, ConversationHandler
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_BOTFATHER_TOKEN_HERE")

MENU_FILE = "menu.json"
ADMINS_FILE = "admins.json"

WAITING_CONTACT = 1


# ---------- file storage ----------
def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_menu():
    return load_json(MENU_FILE, {
        "Passion fruit, Pineapple & Ginger (240ml bottle)": 120,
    })


def get_admins():
    return load_json(ADMINS_FILE, [])


def is_admin(user_id):
    return user_id in get_admins()


# ---------- cart (in memory, per chat_id) ----------
orders = {}


def cart_text(cart):
    if not cart:
        return "Your cart is empty."
    lines = []
    total = 0
    for name, qty in cart.items():
        price = get_menu().get(name, 0)
        lines.append(f"{name} x{qty} = {price*qty} ฿")
        total += price * qty
    lines.append(f"\nTotal: {total} ฿")
    return "\n".join(lines)


def menu_keyboard():
    menu = get_menu()
    buttons = [
        [InlineKeyboardButton(f"{name} — {price}฿", callback_data=f"add:{name}")]
        for name, price in menu.items()
    ]
    buttons.append([InlineKeyboardButton("🛒 Cart / Checkout", callback_data="checkout")])
    return InlineKeyboardMarkup(buttons)


# ---------- customer commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders.setdefault(update.effective_chat.id, {})
    await update.message.reply_text(
        "Hi! Welcome to our Homemade Kombucha 🍹\nPick your flavor below:",
        reply_markup=menu_keyboard()
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    orders.setdefault(chat_id, {})
    await query.answer()

    if query.data.startswith("add:"):
        name = query.data.split("add:", 1)[1]
        orders[chat_id][name] = orders[chat_id].get(name, 0) + 1
        await query.message.reply_text(
            f"Added: {name}\n\n{cart_text(orders[chat_id])}",
            reply_markup=menu_keyboard()
        )
    elif query.data == "checkout":
        if not orders[chat_id]:
            await query.message.reply_text("Your cart is empty, pick something first 🙂")
            return ConversationHandler.END
        await query.message.reply_text(
            f"{cart_text(orders[chat_id])}\n\nPlease send your name, phone/WhatsApp and delivery location in one message."
        )
        return WAITING_CONTACT
    return ConversationHandler.END


async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    cart = orders.get(chat_id, {})
    contact_info = update.message.text
    user = update.effective_user

    order_text = (
        f"🧾 New order!\n"
        f"From: {user.full_name} (@{user.username or '-'})\n\n"
        f"{cart_text(cart)}\n\n"
        f"Contact/delivery: {contact_info}"
    )

    for admin_id in get_admins():
        try:
            await context.bot.send_message(chat_id=admin_id, text=order_text)
        except Exception as e:
            logging.warning(f"Could not message admin {admin_id}: {e}")

    await update.message.reply_text("Thank you! Your order has been received, we'll contact you soon 🙌")
    orders[chat_id] = {}
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders[update.effective_chat.id] = {}
    await update.message.reply_text("Order cancelled.")
    return ConversationHandler.END


# ---------- admin commands ----------
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram ID: {update.effective_user.id}")


async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = get_admins()
    if admins and not is_admin(update.effective_user.id):
        await update.message.reply_text("Only an admin can add other admins.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /addadmin <id>")
        return
    new_id = int(context.args[0])
    if new_id not in admins:
        admins.append(new_id)
        save_json(ADMINS_FILE, admins)
    await update.message.reply_text(f"Admin {new_id} added. Current admins: {admins}")


async def addmenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Only an admin can edit the menu.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addmenu Name Price  (e.g. /addmenu Mint 120)")
        return
    price = int(context.args[-1])
    name = " ".join(context.args[:-1])
    menu = get_menu()
    menu[name] = price
    save_json(MENU_FILE, menu)
    await update.message.reply_text(f"Added/updated: {name} — {price}฿")


async def removemenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Only an admin can edit the menu.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /removemenu Name")
        return
    name = " ".join(context.args)
    menu = get_menu()
    if name in menu:
        del menu[name]
        save_json(MENU_FILE, menu)
        await update.message.reply_text(f"Removed: {name}")
    else:
        await update.message.reply_text("That item isn't in the menu.")


async def listmenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu = get_menu()
    text = "\n".join(f"{n} — {p}฿" for n, p in menu.items())
    await update.message.reply_text(f"Current menu:\n{text}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler)],
        states={WAITING_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_contact)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("addadmin", addadmin))
    app.add_handler(CommandHandler("addmenu", addmenu))
    app.add_handler(CommandHandler("removemenu", removemenu))
    app.add_handler(CommandHandler("listmenu", listmenu))

    app.run_polling()


if __name__ == "__main__":
    main()
