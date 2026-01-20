#!/usr/bin/env python3
"""
Bot de Lista de Mercado para Telegram - Versão Auto-Limpeza
Apaga mensagens antigas e mantém apenas o menu principal.
"""

import logging
import os
import asyncio
from datetime import datetime
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
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

# Armazenamento
shopping_lists = {}
user_states = {}
messages_to_delete = {}  # Armazena IDs de mensagens para deletar


def get_user_state_key(chat_id, user_id):
    return f"{chat_id}_{user_id}"


def get_list_text(items: list) -> str:
    """Formata a lista de compras"""
    if not items:
        return "📋 Lista vazia"
    
    text = ""
    for i, item in enumerate(items, 1):
        text += f"{i}. {item}\n"
    return text.strip()


def get_main_menu_text(items: list) -> str:
    """Texto do menu principal com lista"""
    if items:
        list_text = get_list_text(items)
        return f"🛒 *LISTA DE MERCADO*\n━━━━━━━━━━━━━━━\n{list_text}\n━━━━━━━━━━━━━━━\n📊 *{len(items)} item(ns)*"
    else:
        return "🛒 *LISTA DE MERCADO*\n━━━━━━━━━━━━━━━\n📋 Lista vazia\n━━━━━━━━━━━━━━━"


def get_main_menu_keyboard():
    """Teclado do menu principal"""
    keyboard = [
        [
            InlineKeyboardButton("➕ Adicionar", callback_data='action_add'),
            InlineKeyboardButton("➖ Remover", callback_data='action_remove')
        ],
        [
            InlineKeyboardButton("🗑️ Limpar Tudo", callback_data='action_clear')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_cancel_keyboard():
    """Teclado de cancelar"""
    keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data='action_cancel')]]
    return InlineKeyboardMarkup(keyboard)


async def delete_message_safe(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    """Tenta deletar mensagem de forma segura"""
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except BadRequest as e:
        logger.debug(f"Não foi possível deletar mensagem: {e}")
    except Exception as e:
        logger.debug(f"Erro ao deletar: {e}")


async def track_message(chat_id: int, user_id: int, message_id: int):
    """Rastreia mensagem para deletar depois"""
    key = get_user_state_key(chat_id, user_id)
    if key not in messages_to_delete:
        messages_to_delete[key] = []
    messages_to_delete[key].append(message_id)


async def cleanup_and_show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    """Limpa mensagens antigas e mostra menu atualizado"""
    key = get_user_state_key(chat_id, user_id)
    
    # Deletar mensagens rastreadas
    if key in messages_to_delete:
        for msg_id in messages_to_delete[key]:
            await delete_message_safe(context, chat_id, msg_id)
        messages_to_delete[key] = []
    
    # Resetar estado
    user_states[key] = STATE_NONE
    
    # Mostrar menu atualizado
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    items = shopping_lists[chat_id]['items']
    menu_text = get_main_menu_text(items)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=menu_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )


async def set_bot_commands(application: Application) -> None:
    """Define os comandos do bot"""
    commands = [
        BotCommand("start", "Menu principal"),
        BotCommand("add", "Adicionar item"),
        BotCommand("list", "Ver lista"),
        BotCommand("remove", "Remover item"),
        BotCommand("clear", "Limpar lista"),
        BotCommand("cancel", "Cancelar"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("✅ Comandos configurados!")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start - Menu principal"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    # Resetar estado
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_NONE
    
    items = shopping_lists[chat_id]['items']
    menu_text = get_main_menu_text(items)
    
    # Deletar comando do usuário
    try:
        await update.message.delete()
    except:
        pass
    
    await update.message.reply_text(
        menu_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /list"""
    chat_id = update.effective_chat.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    items = shopping_lists[chat_id]['items']
    menu_text = get_main_menu_text(items)
    
    # Deletar comando
    try:
        await update.message.delete()
    except:
        pass
    
    await update.message.reply_text(
        menu_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )


async def add_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /add"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_ADDING
    messages_to_delete[state_key] = []
    
    # Rastrear comando do usuário
    await track_message(chat_id, user_id, update.message.message_id)
    
    msg = await update.message.reply_text(
        f"📝 *{user_name}*, digite o item a adicionar:",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )
    await track_message(chat_id, user_id, msg.message_id)


async def remove_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /remove"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    items = shopping_lists[chat_id]['items']
    
    if not items:
        try:
            await update.message.delete()
        except:
            pass
        msg = await update.message.reply_text("📋 *Lista vazia!*", parse_mode='Markdown')
        await asyncio.sleep(2)
        try:
            await msg.delete()
        except:
            pass
        return
    
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_REMOVING
    messages_to_delete[state_key] = []
    
    await track_message(chat_id, user_id, update.message.message_id)
    
    list_text = get_list_text(items)
    msg = await update.message.reply_text(
        f"📋 *Lista:*\n{list_text}\n\n🗑️ *{user_name}*, digite o número:",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard()
    )
    await track_message(chat_id, user_id, msg.message_id)


async def clear_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /clear"""
    chat_id = update.effective_chat.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    try:
        await update.message.delete()
    except:
        pass
    
    if not shopping_lists[chat_id]['items']:
        msg = await update.message.reply_text("📋 *Lista já está vazia!*", parse_mode='Markdown')
        await asyncio.sleep(2)
        try:
            await msg.delete()
        except:
            pass
        return
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Sim, limpar", callback_data='confirm_clear'),
            InlineKeyboardButton("❌ Não", callback_data='cancel_clear')
        ]
    ]
    
    await update.message.reply_text(
        "⚠️ *Limpar toda a lista?*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /cancel"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    await track_message(chat_id, user_id, update.message.message_id)
    await cleanup_and_show_menu(update, context, chat_id, user_id)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa mensagens de texto"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    text = update.message.text.strip()
    user_name = update.effective_user.first_name
    
    state_key = get_user_state_key(chat_id, user_id)
    current_state = user_states.get(state_key, STATE_NONE)
    
    # Ignorar se não está em nenhum estado
    if current_state == STATE_NONE:
        return
    
    # Rastrear mensagem do usuário
    await track_message(chat_id, user_id, update.message.message_id)
    
    # ADICIONANDO
    if current_state == STATE_ADDING:
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        if len(text) < 2:
            msg = await update.message.reply_text("❌ *Muito curto!*", parse_mode='Markdown')
            await track_message(chat_id, user_id, msg.message_id)
            return
        
        # Verificar duplicata
        items_lower = [item.lower() for item in shopping_lists[chat_id]['items']]
        if text.lower() in items_lower:
            msg = await update.message.reply_text(f"⚠️ *'{text}' já existe!*", parse_mode='Markdown')
            await track_message(chat_id, user_id, msg.message_id)
            await asyncio.sleep(1.5)
            await cleanup_and_show_menu(update, context, chat_id, user_id)
            return
        
        # Adicionar item
        shopping_lists[chat_id]['items'].append(text)
        
        # Feedback rápido
        msg = await update.message.reply_text(f"✅ *+{text}*", parse_mode='Markdown')
        await track_message(chat_id, user_id, msg.message_id)
        
        await asyncio.sleep(1)
        await cleanup_and_show_menu(update, context, chat_id, user_id)
    
    # REMOVENDO
    elif current_state == STATE_REMOVING:
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        items = shopping_lists[chat_id]['items']
        
        try:
            index = int(text) - 1
            
            if index < 0 or index >= len(items):
                msg = await update.message.reply_text(f"❌ *1 a {len(items)}!*", parse_mode='Markdown')
                await track_message(chat_id, user_id, msg.message_id)
                return
            
            removed_item = items.pop(index)
            
            msg = await update.message.reply_text(f"✅ *-{removed_item}*", parse_mode='Markdown')
            await track_message(chat_id, user_id, msg.message_id)
            
            await asyncio.sleep(1)
            await cleanup_and_show_menu(update, context, chat_id, user_id)
            
        except ValueError:
            msg = await update.message.reply_text("❌ *Digite o número!*", parse_mode='Markdown')
            await track_message(chat_id, user_id, msg.message_id)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa cliques nos botões"""
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    user_name = query.from_user.first_name
    
    await query.answer()
    
    state_key = get_user_state_key(chat_id, user_id)
    
    # ADICIONAR
    if query.data == 'action_add':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        user_states[state_key] = STATE_ADDING
        messages_to_delete[state_key] = []
        
        # Editar mensagem do menu para virar prompt
        await query.edit_message_text(
            f"📝 *{user_name}*, digite o item a adicionar:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        await track_message(chat_id, user_id, query.message.message_id)
    
    # REMOVER
    elif query.data == 'action_remove':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        items = shopping_lists[chat_id]['items']
        
        if not items:
            await query.edit_message_text(
                "📋 *Lista vazia!*\n\nUse ➕ Adicionar para começar.",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        user_states[state_key] = STATE_REMOVING
        messages_to_delete[state_key] = []
        
        list_text = get_list_text(items)
        await query.edit_message_text(
            f"📋 *Lista:*\n{list_text}\n\n🗑️ *{user_name}*, digite o número:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
        await track_message(chat_id, user_id, query.message.message_id)
    
    # LIMPAR
    elif query.data == 'action_clear':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        if not shopping_lists[chat_id]['items']:
            await query.edit_message_text(
                "📋 *Lista já está vazia!*",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Sim", callback_data='confirm_clear'),
                InlineKeyboardButton("❌ Não", callback_data='cancel_clear')
            ]
        ]
        
        await query.edit_message_text(
            "⚠️ *Limpar toda a lista?*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # CANCELAR
    elif query.data == 'action_cancel':
        user_states[state_key] = STATE_NONE
        
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        items = shopping_lists[chat_id]['items']
        menu_text = get_main_menu_text(items)
        
        # Limpar mensagens rastreadas (exceto o menu atual)
        if state_key in messages_to_delete:
            for msg_id in messages_to_delete[state_key]:
                if msg_id != query.message.message_id:
                    await delete_message_safe(context, chat_id, msg_id)
            messages_to_delete[state_key] = []
        
        await query.edit_message_text(
            menu_text,
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    
    # CONFIRMAR LIMPEZA
    elif query.data == 'confirm_clear':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        shopping_lists[chat_id]['items'] = []
        
        menu_text = get_main_menu_text([])
        await query.edit_message_text(
            f"🗑️ *Lista limpa!*\n\n{menu_text}",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    
    # CANCELAR LIMPEZA
    elif query.data == 'cancel_clear':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        items = shopping_lists[chat_id]['items']
        menu_text = get_main_menu_text(items)
        
        await query.edit_message_text(
            menu_text,
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )


def main() -> None:
    """Inicia o bot"""
    bot_token = os.getenv('BOT_TOKEN')
    
    if not bot_token:
        logger.error("❌ ERRO: BOT_TOKEN não encontrado!")
        return
    
    logger.info(f"✅ Token: {bot_token[:20]}...")
    
    application = Application.builder().token(bot_token).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", show_list))
    application.add_handler(CommandHandler("add", add_item_command))
    application.add_handler(CommandHandler("remove", remove_item_command))
    application.add_handler(CommandHandler("clear", clear_list_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    application.post_init = set_bot_commands
    
    logger.info("🤖 Bot iniciado!")
    application.run_polling()


if __name__ == '__main__':
    main()
