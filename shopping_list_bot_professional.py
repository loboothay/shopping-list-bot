#!/usr/bin/env python3
"""
Bot de Lista de Mercado para Telegram - Versão Limpa
Interface elegante com menos mensagens para não poluir o chat.
"""

import logging
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados possíveis
STATE_NONE = 0
STATE_ADDING = 1
STATE_REMOVING = 2

# Dicionário para armazenar listas por grupo
shopping_lists = {}
# Dicionário para armazenar estados por usuário/chat
user_states = {}


def get_user_state_key(chat_id, user_id):
    """Gera chave única para estado do usuário"""
    return f"{chat_id}_{user_id}"


def get_list_text(items: list, compact: bool = False) -> str:
    """Formata a lista de compras para exibição"""
    if not items:
        return "📋 *Lista vazia*"
    
    if compact:
        # Versão compacta para confirmações
        items_text = ", ".join(items)
        return f"📋 *Lista:* {items_text} ({len(items)})"
    
    # Versão completa
    text = "📋 *LISTA DE COMPRAS*\n"
    text += "━" * 20 + "\n"
    
    for i, item in enumerate(items, 1):
        text += f"{i}. {item}\n"
    
    text += "━" * 20
    text += f"\n📊 *{len(items)} item(ns)*"
    
    return text


def get_main_menu_keyboard():
    """Retorna o teclado do menu principal"""
    keyboard = [
        [
            InlineKeyboardButton("🛒 Adicionar", callback_data='action_add'),
            InlineKeyboardButton("📋 Ver Lista", callback_data='action_list')
        ],
        [
            InlineKeyboardButton("❌ Remover", callback_data='action_remove'),
            InlineKeyboardButton("🗑️ Limpar", callback_data='action_clear')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_cancel_keyboard():
    """Retorna teclado de cancelar (seletivo para grupos)"""
    return ReplyKeyboardMarkup(
        [["❌ Cancelar"]], 
        one_time_keyboard=True,
        selective=True,
        resize_keyboard=True
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
    logger.info("✅ Menu de comandos configurado!")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start"""
    chat_id = update.effective_chat.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    items = shopping_lists[chat_id]['items']
    
    if items:
        list_preview = get_list_text(items, compact=True)
        welcome_text = f"🛒 *Lista de Mercado*\n\n{list_preview}\n\nEscolha:"
    else:
        welcome_text = "🛒 *Lista de Mercado*\n\n📋 Lista vazia\n\nEscolha:"
    
    await update.message.reply_text(
        welcome_text, 
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /list"""
    chat_id = update.effective_chat.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    items = shopping_lists[chat_id]['items']
    list_text = get_list_text(items)
    
    await update.message.reply_text(list_text, parse_mode='Markdown')


async def add_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /add - Inicia adição de item"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_ADDING
    
    await update.message.reply_text(
        f"📝 *{user_name}*, digite o item:",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard(),
        reply_to_message_id=update.message.message_id
    )


async def remove_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /remove - Inicia remoção"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    items = shopping_lists[chat_id]['items']
    
    if not items:
        await update.message.reply_text("📋 *Lista vazia!*", parse_mode='Markdown')
        return
    
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_REMOVING
    
    list_text = get_list_text(items)
    
    await update.message.reply_text(
        f"{list_text}\n\n🗑️ *{user_name}*, qual número remover?",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard(),
        reply_to_message_id=update.message.message_id
    )


async def clear_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /clear - Limpa a lista"""
    chat_id = update.effective_chat.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    if not shopping_lists[chat_id]['items']:
        await update.message.reply_text("📋 *Lista já está vazia!*", parse_mode='Markdown')
        return
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Sim", callback_data='confirm_clear'),
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
    
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_NONE
    
    await update.message.reply_text(
        "❌ *Cancelado*",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove(selective=True)
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa mensagens de texto baseado no estado do usuário"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    text = update.message.text.strip()
    user_name = update.effective_user.first_name
    
    state_key = get_user_state_key(chat_id, user_id)
    current_state = user_states.get(state_key, STATE_NONE)
    
    # Se não está em nenhum estado, ignorar
    if current_state == STATE_NONE:
        return
    
    # Cancelamento
    if text.lower() in ["❌ cancelar", "cancelar"]:
        user_states[state_key] = STATE_NONE
        await update.message.reply_text(
            "❌ *Cancelado*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove(selective=True)
        )
        return
    
    # ADICIONANDO ITEM
    if current_state == STATE_ADDING:
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        if len(text) < 2:
            await update.message.reply_text(
                "❌ *Muito curto!*",
                parse_mode='Markdown',
                reply_to_message_id=update.message.message_id
            )
            return
        
        # Verificar duplicata
        items_lower = [item.lower() for item in shopping_lists[chat_id]['items']]
        if text.lower() in items_lower:
            user_states[state_key] = STATE_NONE
            await update.message.reply_text(
                f"⚠️ *'{text}' já está na lista!*",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove(selective=True)
            )
            return
        
        # Adicionar
        shopping_lists[chat_id]['items'].append(text)
        user_states[state_key] = STATE_NONE
        
        total = len(shopping_lists[chat_id]['items'])
        
        # UMA SÓ MENSAGEM com confirmação
        await update.message.reply_text(
            f"✅ *+{text}* (total: {total})",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove(selective=True)
        )
    
    # REMOVENDO ITEM
    elif current_state == STATE_REMOVING:
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        items = shopping_lists[chat_id]['items']
        
        try:
            index = int(text) - 1
            
            if index < 0 or index >= len(items):
                await update.message.reply_text(
                    f"❌ *1 a {len(items)}!*",
                    parse_mode='Markdown',
                    reply_to_message_id=update.message.message_id
                )
                return
            
            removed_item = items.pop(index)
            user_states[state_key] = STATE_NONE
            
            total = len(items)
            
            # UMA SÓ MENSAGEM
            await update.message.reply_text(
                f"✅ *-{removed_item}* (restam: {total})",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove(selective=True)
            )
            
        except ValueError:
            await update.message.reply_text(
                "❌ *Digite o número!*",
                parse_mode='Markdown',
                reply_to_message_id=update.message.message_id
            )


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
        
        await query.message.reply_text(
            f"📝 *{user_name}*, digite o item:",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
    
    # VER LISTA
    elif query.data == 'action_list':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        items = shopping_lists[chat_id]['items']
        list_text = get_list_text(items)
        await query.message.reply_text(list_text, parse_mode='Markdown')
    
    # REMOVER
    elif query.data == 'action_remove':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        items = shopping_lists[chat_id]['items']
        
        if not items:
            await query.message.reply_text("📋 *Lista vazia!*", parse_mode='Markdown')
            return
        
        user_states[state_key] = STATE_REMOVING
        
        list_text = get_list_text(items)
        
        await query.message.reply_text(
            f"{list_text}\n\n🗑️ *{user_name}*, qual número?",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
    
    # LIMPAR
    elif query.data == 'action_clear':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        if not shopping_lists[chat_id]['items']:
            await query.message.reply_text("📋 *Lista vazia!*", parse_mode='Markdown')
            return
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Sim", callback_data='confirm_clear'),
                InlineKeyboardButton("❌ Não", callback_data='cancel_clear')
            ]
        ]
        
        await query.message.reply_text(
            "⚠️ *Limpar toda a lista?*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # CONFIRMAR LIMPEZA
    elif query.data == 'confirm_clear':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        shopping_lists[chat_id]['items'] = []
        await query.edit_message_text(
            f"🗑️ *Lista limpa por {user_name}!*",
            parse_mode='Markdown'
        )
    
    elif query.data == 'cancel_clear':
        await query.edit_message_text("❌ *Cancelado*", parse_mode='Markdown')


def main() -> None:
    """Inicia o bot"""
    bot_token = os.getenv('BOT_TOKEN')
    
    if not bot_token:
        logger.error("❌ ERRO: Variável 'BOT_TOKEN' não encontrada!")
        return
    
    if bot_token == "YOUR_BOT_TOKEN":
        logger.error("❌ ERRO: Use seu token real do BotFather")
        return
    
    logger.info(f"✅ Token detectado: {bot_token[:20]}...")
    
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
