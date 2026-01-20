#!/usr/bin/env python3
"""
Bot de Lista de Mercado para Telegram - Com Modo Mercado (HTML)
Usa HTML para texto riscado funcionar corretamente.
"""

import logging
import os
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)
from telegram.error import BadRequest

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados
STATE_NONE = 0
STATE_ADDING = 1
STATE_REMOVING = 2
STATE_MARKET_MODE = 3

# Armazenamento
shopping_lists = {}
user_states = {}
messages_to_delete = {}
menu_messages = {}


def get_user_state_key(chat_id, user_id):
    return f"{chat_id}_{user_id}"


def init_list(chat_id):
    """Inicializa lista se não existir"""
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}


def get_list_text(items: list, show_status: bool = True) -> str:
    """Formata a lista de compras usando HTML"""
    if not items:
        return "📋 Lista vazia"
    
    text = ""
    for i, item in enumerate(items, 1):
        name = item['name']
        bought = item.get('bought', False)
        
        if show_status and bought:
            # Usa <s> para texto riscado em HTML
            text += f"{i}. <s>{name}</s> ✅\n"
        else:
            text += f"{i}. {name}\n"
    
    return text.strip()


def get_main_menu_text(items: list) -> str:
    """Texto do menu principal com lista (HTML)"""
    if items:
        pending = sum(1 for item in items if not item.get('bought', False))
        bought = sum(1 for item in items if item.get('bought', False))
        
        list_text = get_list_text(items)
        status = f"📊 <b>{len(items)} item(ns)</b>"
        if bought > 0:
            status += f" | ✅ {bought} comprado(s)"
        
        return f"🛒 <b>LISTA DE MERCADO</b>\n━━━━━━━━━━━━━━━\n{list_text}\n━━━━━━━━━━━━━━━\n{status}"
    else:
        return "🛒 <b>LISTA DE MERCADO</b>\n━━━━━━━━━━━━━━━\n📋 Lista vazia\n━━━━━━━━━━━━━━━"


def get_main_menu_keyboard(has_items: bool = False):
    """Teclado do menu principal"""
    keyboard = [
        [
            InlineKeyboardButton("➕ Adicionar", callback_data='action_add'),
            InlineKeyboardButton("➖ Remover", callback_data='action_remove')
        ]
    ]
    
    if has_items:
        keyboard.append([
            InlineKeyboardButton("🛒 Modo Mercado", callback_data='action_market_mode')
        ])
    
    keyboard.append([
        InlineKeyboardButton("🗑️ Limpar Tudo", callback_data='action_clear')
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_cancel_keyboard():
    """Teclado de cancelar"""
    keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data='action_cancel')]]
    return InlineKeyboardMarkup(keyboard)


def get_market_mode_keyboard(items: list):
    """Teclado do modo mercado com checkboxes"""
    keyboard = []
    
    for i, item in enumerate(items):
        name = item['name']
        bought = item.get('bought', False)
        
        if bought:
            btn_text = f"✅ {name}"
        else:
            btn_text = f"⬜ {name}"
        
        keyboard.append([
            InlineKeyboardButton(btn_text, callback_data=f'toggle_{i}')
        ])
    
    keyboard.append([
        InlineKeyboardButton("✔️ Finalizar", callback_data='market_finish'),
        InlineKeyboardButton("❌ Cancelar", callback_data='market_cancel')
    ])
    
    has_bought = any(item.get('bought', False) for item in items)
    if has_bought:
        keyboard.append([
            InlineKeyboardButton("🧹 Remover Comprados", callback_data='market_clear_bought')
        ])
    
    return InlineKeyboardMarkup(keyboard)


async def delete_message_safe(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    """Tenta deletar mensagem de forma segura"""
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except:
        return False


async def track_message(chat_id: int, user_id: int, message_id: int):
    """Rastreia mensagem para deletar depois"""
    key = get_user_state_key(chat_id, user_id)
    if key not in messages_to_delete:
        messages_to_delete[key] = []
    messages_to_delete[key].append(message_id)


async def cleanup_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    """Limpa mensagens rastreadas"""
    key = get_user_state_key(chat_id, user_id)
    if key in messages_to_delete:
        for msg_id in messages_to_delete[key]:
            await delete_message_safe(context, chat_id, msg_id)
        messages_to_delete[key] = []


async def update_menu(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Atualiza o menu existente ou cria um novo"""
    init_list(chat_id)
    items = shopping_lists[chat_id]['items']
    menu_text = get_main_menu_text(items)
    has_items = len(items) > 0
    
    if chat_id in menu_messages:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=menu_messages[chat_id],
                text=menu_text,
                parse_mode='HTML',
                reply_markup=get_main_menu_keyboard(has_items)
            )
            return
        except BadRequest:
            pass
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=menu_text,
        parse_mode='HTML',
        reply_markup=get_main_menu_keyboard(has_items)
    )
    menu_messages[chat_id] = msg.message_id


async def set_bot_commands(application: Application) -> None:
    """Define os comandos do bot"""
    commands = [
        BotCommand("start", "Menu principal"),
        BotCommand("add", "Adicionar item"),
        BotCommand("list", "Ver lista"),
        BotCommand("remove", "Remover item"),
        BotCommand("market", "Modo mercado"),
        BotCommand("clear", "Limpar lista"),
        BotCommand("cancel", "Cancelar"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("✅ Comandos configurados!")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    init_list(chat_id)
    
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_NONE
    
    await delete_message_safe(context, chat_id, update.message.message_id)
    
    if chat_id in menu_messages:
        await delete_message_safe(context, chat_id, menu_messages[chat_id])
    
    items = shopping_lists[chat_id]['items']
    menu_text = get_main_menu_text(items)
    has_items = len(items) > 0
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=menu_text,
        parse_mode='HTML',
        reply_markup=get_main_menu_keyboard(has_items)
    )
    menu_messages[chat_id] = msg.message_id


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /list"""
    chat_id = update.effective_chat.id
    await delete_message_safe(context, chat_id, update.message.message_id)
    await update_menu(context, chat_id)


async def add_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /add"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    init_list(chat_id)
    
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_ADDING
    messages_to_delete[state_key] = []
    
    await delete_message_safe(context, chat_id, update.message.message_id)
    
    if chat_id in menu_messages:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=menu_messages[chat_id],
                text=f"📝 <b>{user_name}</b>, digite o item a adicionar:",
                parse_mode='HTML',
                reply_markup=get_cancel_keyboard()
            )
            return
        except BadRequest:
            pass
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"📝 <b>{user_name}</b>, digite o item a adicionar:",
        parse_mode='HTML',
        reply_markup=get_cancel_keyboard()
    )
    menu_messages[chat_id] = msg.message_id


async def remove_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /remove"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    init_list(chat_id)
    items = shopping_lists[chat_id]['items']
    
    await delete_message_safe(context, chat_id, update.message.message_id)
    
    if not items:
        msg = await context.bot.send_message(chat_id=chat_id, text="📋 <b>Lista vazia!</b>", parse_mode='HTML')
        await asyncio.sleep(2)
        await delete_message_safe(context, chat_id, msg.message_id)
        await update_menu(context, chat_id)
        return
    
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_REMOVING
    messages_to_delete[state_key] = []
    
    list_text = get_list_text(items, show_status=False)
    
    if chat_id in menu_messages:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=menu_messages[chat_id],
                text=f"📋 <b>Lista:</b>\n{list_text}\n\n🗑️ <b>{user_name}</b>, digite o número:",
                parse_mode='HTML',
                reply_markup=get_cancel_keyboard()
            )
            return
        except BadRequest:
            pass
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"📋 <b>Lista:</b>\n{list_text}\n\n🗑️ <b>{user_name}</b>, digite o número:",
        parse_mode='HTML',
        reply_markup=get_cancel_keyboard()
    )
    menu_messages[chat_id] = msg.message_id


async def market_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /market - Modo mercado"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    init_list(chat_id)
    items = shopping_lists[chat_id]['items']
    
    await delete_message_safe(context, chat_id, update.message.message_id)
    
    if not items:
        msg = await context.bot.send_message(chat_id=chat_id, text="📋 <b>Lista vazia!</b>", parse_mode='HTML')
        await asyncio.sleep(2)
        await delete_message_safe(context, chat_id, msg.message_id)
        await update_menu(context, chat_id)
        return
    
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_MARKET_MODE
    
    pending = sum(1 for item in items if not item.get('bought', False))
    
    if chat_id in menu_messages:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=menu_messages[chat_id],
                text=f"🛒 <b>MODO MERCADO</b>\n━━━━━━━━━━━━━━━\nToque nos itens para marcar:\n\n📦 <b>{pending} pendente(s)</b>",
                parse_mode='HTML',
                reply_markup=get_market_mode_keyboard(items)
            )
            return
        except BadRequest:
            pass
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🛒 <b>MODO MERCADO</b>\n━━━━━━━━━━━━━━━\nToque nos itens para marcar:\n\n📦 <b>{pending} pendente(s)</b>",
        parse_mode='HTML',
        reply_markup=get_market_mode_keyboard(items)
    )
    menu_messages[chat_id] = msg.message_id


async def clear_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /clear"""
    chat_id = update.effective_chat.id
    
    init_list(chat_id)
    
    await delete_message_safe(context, chat_id, update.message.message_id)
    
    if not shopping_lists[chat_id]['items']:
        msg = await context.bot.send_message(chat_id=chat_id, text="📋 <b>Lista já está vazia!</b>", parse_mode='HTML')
        await asyncio.sleep(2)
        await delete_message_safe(context, chat_id, msg.message_id)
        await update_menu(context, chat_id)
        return
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Sim, limpar", callback_data='confirm_clear'),
            InlineKeyboardButton("❌ Não", callback_data='cancel_clear')
        ]
    ]
    
    if chat_id in menu_messages:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=menu_messages[chat_id],
                text="⚠️ <b>Limpar toda a lista?</b>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        except BadRequest:
            pass
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ <b>Limpar toda a lista?</b>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    menu_messages[chat_id] = msg.message_id


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /cancel"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_NONE
    
    await delete_message_safe(context, chat_id, update.message.message_id)
    await cleanup_messages(context, chat_id, user_id)
    await update_menu(context, chat_id)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa mensagens de texto"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    text = update.message.text.strip()
    user_name = update.effective_user.first_name
    
    state_key = get_user_state_key(chat_id, user_id)
    current_state = user_states.get(state_key, STATE_NONE)
    
    if current_state == STATE_NONE:
        return
    
    await delete_message_safe(context, chat_id, update.message.message_id)
    
    # ADICIONANDO
    if current_state == STATE_ADDING:
        init_list(chat_id)
        
        if len(text) < 2:
            msg = await context.bot.send_message(chat_id=chat_id, text="❌ <b>Muito curto!</b>", parse_mode='HTML')
            await asyncio.sleep(1.5)
            await delete_message_safe(context, chat_id, msg.message_id)
            return
        
        items_names = [item['name'].lower() for item in shopping_lists[chat_id]['items']]
        if text.lower() in items_names:
            user_states[state_key] = STATE_NONE
            msg = await context.bot.send_message(chat_id=chat_id, text=f"⚠️ <b>'{text}' já existe!</b>", parse_mode='HTML')
            await asyncio.sleep(1.5)
            await delete_message_safe(context, chat_id, msg.message_id)
            await update_menu(context, chat_id)
            return
        
        shopping_lists[chat_id]['items'].append({'name': text, 'bought': False})
        user_states[state_key] = STATE_NONE
        
        msg = await context.bot.send_message(chat_id=chat_id, text=f"✅ <b>+{text}</b>", parse_mode='HTML')
        await asyncio.sleep(1)
        await delete_message_safe(context, chat_id, msg.message_id)
        await update_menu(context, chat_id)
    
    # REMOVENDO
    elif current_state == STATE_REMOVING:
        init_list(chat_id)
        items = shopping_lists[chat_id]['items']
        
        try:
            index = int(text) - 1
            
            if index < 0 or index >= len(items):
                msg = await context.bot.send_message(chat_id=chat_id, text=f"❌ <b>1 a {len(items)}!</b>", parse_mode='HTML')
                await asyncio.sleep(1.5)
                await delete_message_safe(context, chat_id, msg.message_id)
                return
            
            removed_item = items.pop(index)
            user_states[state_key] = STATE_NONE
            
            msg = await context.bot.send_message(chat_id=chat_id, text=f"✅ <b>-{removed_item['name']}</b>", parse_mode='HTML')
            await asyncio.sleep(1)
            await delete_message_safe(context, chat_id, msg.message_id)
            await update_menu(context, chat_id)
            
        except ValueError:
            msg = await context.bot.send_message(chat_id=chat_id, text="❌ <b>Digite o número!</b>", parse_mode='HTML')
            await asyncio.sleep(1.5)
            await delete_message_safe(context, chat_id, msg.message_id)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa cliques nos botões"""
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    user_name = query.from_user.first_name
    
    await query.answer()
    
    state_key = get_user_state_key(chat_id, user_id)
    init_list(chat_id)
    
    # ADICIONAR
    if query.data == 'action_add':
        user_states[state_key] = STATE_ADDING
        messages_to_delete[state_key] = []
        
        await query.edit_message_text(
            f"📝 <b>{user_name}</b>, digite o item a adicionar:",
            parse_mode='HTML',
            reply_markup=get_cancel_keyboard()
        )
    
    # REMOVER
    elif query.data == 'action_remove':
        items = shopping_lists[chat_id]['items']
        
        if not items:
            await query.edit_message_text(
                "📋 <b>Lista vazia!</b>\n\nUse ➕ Adicionar para começar.",
                parse_mode='HTML',
                reply_markup=get_main_menu_keyboard(False)
            )
            return
        
        user_states[state_key] = STATE_REMOVING
        messages_to_delete[state_key] = []
        
        list_text = get_list_text(items, show_status=False)
        await query.edit_message_text(
            f"📋 <b>Lista:</b>\n{list_text}\n\n🗑️ <b>{user_name}</b>, digite o número:",
            parse_mode='HTML',
            reply_markup=get_cancel_keyboard()
        )
    
    # MODO MERCADO
    elif query.data == 'action_market_mode':
        items = shopping_lists[chat_id]['items']
        
        if not items:
            await query.edit_message_text(
                "📋 <b>Lista vazia!</b>",
                parse_mode='HTML',
                reply_markup=get_main_menu_keyboard(False)
            )
            return
        
        user_states[state_key] = STATE_MARKET_MODE
        pending = sum(1 for item in items if not item.get('bought', False))
        
        await query.edit_message_text(
            f"🛒 <b>MODO MERCADO</b>\n━━━━━━━━━━━━━━━\nToque nos itens para marcar:\n\n📦 <b>{pending} pendente(s)</b>",
            parse_mode='HTML',
            reply_markup=get_market_mode_keyboard(items)
        )
    
    # TOGGLE ITEM
    elif query.data.startswith('toggle_'):
        index = int(query.data.split('_')[1])
        items = shopping_lists[chat_id]['items']
        
        if 0 <= index < len(items):
            items[index]['bought'] = not items[index].get('bought', False)
        
        pending = sum(1 for item in items if not item.get('bought', False))
        
        await query.edit_message_text(
            f"🛒 <b>MODO MERCADO</b>\n━━━━━━━━━━━━━━━\nToque nos itens para marcar:\n\n📦 <b>{pending} pendente(s)</b>",
            parse_mode='HTML',
            reply_markup=get_market_mode_keyboard(items)
        )
    
    # FINALIZAR MODO MERCADO
    elif query.data == 'market_finish':
        user_states[state_key] = STATE_NONE
        items = shopping_lists[chat_id]['items']
        
        bought_count = sum(1 for item in items if item.get('bought', False))
        
        menu_text = get_main_menu_text(items)
        has_items = len(items) > 0
        
        await query.edit_message_text(
            f"✅ <b>Compras finalizadas!</b>\n{bought_count} item(ns) marcado(s)\n\n{menu_text}",
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(has_items)
        )
    
    # CANCELAR MODO MERCADO
    elif query.data == 'market_cancel':
        user_states[state_key] = STATE_NONE
        
        items = shopping_lists[chat_id]['items']
        for item in items:
            item['bought'] = False
        
        menu_text = get_main_menu_text(items)
        has_items = len(items) > 0
        
        await query.edit_message_text(
            menu_text,
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(has_items)
        )
    
    # REMOVER COMPRADOS
    elif query.data == 'market_clear_bought':
        items = shopping_lists[chat_id]['items']
        
        removed_count = sum(1 for item in items if item.get('bought', False))
        shopping_lists[chat_id]['items'] = [item for item in items if not item.get('bought', False)]
        
        items = shopping_lists[chat_id]['items']
        
        if items:
            pending = sum(1 for item in items if not item.get('bought', False))
            await query.edit_message_text(
                f"🧹 <b>{removed_count} item(ns) removido(s)!</b>\n\n🛒 <b>MODO MERCADO</b>\n━━━━━━━━━━━━━━━\n📦 <b>{pending} pendente(s)</b>",
                parse_mode='HTML',
                reply_markup=get_market_mode_keyboard(items)
            )
        else:
            user_states[state_key] = STATE_NONE
            menu_text = get_main_menu_text([])
            await query.edit_message_text(
                f"🧹 <b>{removed_count} item(ns) removido(s)!</b>\n\n{menu_text}",
                parse_mode='HTML',
                reply_markup=get_main_menu_keyboard(False)
            )
    
    # LIMPAR TUDO
    elif query.data == 'action_clear':
        if not shopping_lists[chat_id]['items']:
            await query.edit_message_text(
                "📋 <b>Lista já está vazia!</b>",
                parse_mode='HTML',
                reply_markup=get_main_menu_keyboard(False)
            )
            return
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Sim", callback_data='confirm_clear'),
                InlineKeyboardButton("❌ Não", callback_data='cancel_clear')
            ]
        ]
        
        await query.edit_message_text(
            "⚠️ <b>Limpar toda a lista?</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # CANCELAR
    elif query.data == 'action_cancel':
        user_states[state_key] = STATE_NONE
        await cleanup_messages(context, chat_id, user_id)
        
        items = shopping_lists[chat_id]['items']
        menu_text = get_main_menu_text(items)
        has_items = len(items) > 0
        
        await query.edit_message_text(
            menu_text,
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(has_items)
        )
    
    # CONFIRMAR LIMPEZA
    elif query.data == 'confirm_clear':
        shopping_lists[chat_id]['items'] = []
        
        menu_text = get_main_menu_text([])
        await query.edit_message_text(
            menu_text,
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(False)
        )
    
    # CANCELAR LIMPEZA
    elif query.data == 'cancel_clear':
        items = shopping_lists[chat_id]['items']
        menu_text = get_main_menu_text(items)
        has_items = len(items) > 0
        
        await query.edit_message_text(
            menu_text,
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(has_items)
        )


def main() -> None:
    """Inicia o bot"""
    bot_token = os.getenv('BOT_TOKEN')
    
    if not bot_token:
        logger.error("❌ ERRO: BOT_TOKEN não encontrado!")
        return
    
    logger.info(f"✅ Token: {bot_token[:20]}...")
    
    application = Application.builder().token(bot_token).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", show_list))
    application.add_handler(CommandHandler("add", add_item_command))
    application.add_handler(CommandHandler("remove", remove_item_command))
    application.add_handler(CommandHandler("market", market_mode_command))
    application.add_handler(CommandHandler("clear", clear_list_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    application.post_init = set_bot_commands
    
    logger.info("🤖 Bot iniciado!")
    application.run_polling()


if __name__ == '__main__':
    main()
