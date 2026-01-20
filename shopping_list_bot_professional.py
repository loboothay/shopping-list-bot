#!/usr/bin/env python3
"""
Bot de Lista de Mercado para Telegram - Versão para Grupos
Interface elegante com botões que funcionam em grupos corretamente.
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


def get_list_text(items: list) -> str:
    """Formata a lista de compras para exibição"""
    if not items:
        return "📋 *Lista de Compras Vazia*\n\n_Use /add para começar!_"
    
    text = "📋 *LISTA DE COMPRAS*\n"
    text += "━" * 25 + "\n\n"
    
    for i, item in enumerate(items, 1):
        text += f"{i}. ✓ {item}\n"
    
    text += "\n" + "━" * 25
    text += f"\n\n📊 *Total:* {len(items)} item(ns)"
    
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
        ],
        [
            InlineKeyboardButton("❓ Ajuda", callback_data='action_help')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_cancel_keyboard():
    """Retorna teclado de cancelar (seletivo para grupos)"""
    return ReplyKeyboardMarkup(
        [["❌ Cancelar"]], 
        one_time_keyboard=True,
        selective=True  # Aparece só para quem enviou o comando
    )


async def set_bot_commands(application: Application) -> None:
    """Define os comandos do bot"""
    commands = [
        BotCommand("start", "Iniciar o bot"),
        BotCommand("add", "Adicionar item à lista"),
        BotCommand("list", "Ver lista de compras"),
        BotCommand("remove", "Remover item da lista"),
        BotCommand("clear", "Limpar toda a lista"),
        BotCommand("help", "Ver ajuda"),
        BotCommand("cancel", "Cancelar operação atual"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("✅ Menu de comandos configurado!")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start"""
    chat_id = update.effective_chat.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    welcome_text = (
        "👋 *Bem-vindo ao Bot de Lista de Mercado!*\n\n"
        "Gerenciador de compras para sua família.\n\n"
        "Escolha uma opção abaixo:"
    )
    
    await update.message.reply_text(
        welcome_text, 
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /help"""
    help_text = (
        "📚 *GUIA DE USO*\n\n"
        "*🛒 Adicionar Itens*\n"
        "Use: /add\n"
        "Digite o nome do item\n\n"
        "*❌ Remover Itens*\n"
        "Use: /remove\n"
        "Digite o número do item\n\n"
        "*📋 Ver Lista*\n"
        "Use: /list\n\n"
        "*🗑️ Limpar Lista*\n"
        "Use: /clear\n\n"
        "*🚫 Cancelar*\n"
        "Use: /cancel\n\n"
        "💡 Qualquer membro pode usar!"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


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
    
    # Definir estado do usuário
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_ADDING
    
    await update.message.reply_text(
        f"📝 *{user_name}, qual item você quer adicionar?*\n\n_Digite o nome ou /cancel para cancelar_",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard(),
        reply_to_message_id=update.message.message_id  # Responde à mensagem original
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
        await update.message.reply_text(
            "📋 *A lista está vazia!*",
            parse_mode='Markdown'
        )
        return
    
    # Definir estado do usuário
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_REMOVING
    
    list_text = get_list_text(items)
    
    await update.message.reply_text(list_text, parse_mode='Markdown')
    await update.message.reply_text(
        f"🗑️ *{user_name}, digite o número do item a remover:*\n\n_Ou /cancel para cancelar_",
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
        await update.message.reply_text(
            "📋 *A lista já está vazia!*",
            parse_mode='Markdown'
        )
        return
    
    # Botões de confirmação
    keyboard = [
        [
            InlineKeyboardButton("✅ Sim, limpar", callback_data='confirm_clear'),
            InlineKeyboardButton("❌ Cancelar", callback_data='cancel_clear')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚠️ *Tem certeza que quer limpar TODA a lista?*",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /cancel - Cancela operação atual"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    state_key = get_user_state_key(chat_id, user_id)
    user_states[state_key] = STATE_NONE
    
    await update.message.reply_text(
        "❌ *Operação cancelada*",
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
    
    # Se o usuário não está em nenhum estado, ignorar a mensagem
    if current_state == STATE_NONE:
        return
    
    # Verificar cancelamento
    if text.lower() == "❌ cancelar" or text.lower() == "cancelar":
        user_states[state_key] = STATE_NONE
        await update.message.reply_text(
            "❌ *Cancelado*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove(selective=True)
        )
        return
    
    # Estado: Adicionando item
    if current_state == STATE_ADDING:
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        if not text or len(text) < 2:
            await update.message.reply_text(
                f"❌ *{user_name}, nome muito curto!* (mínimo 2 caracteres)",
                parse_mode='Markdown',
                reply_to_message_id=update.message.message_id
            )
            return
        
        # Evitar duplicatas
        items_lower = [item.lower() for item in shopping_lists[chat_id]['items']]
        if text.lower() in items_lower:
            user_states[state_key] = STATE_NONE
            await update.message.reply_text(
                f"⚠️ *'{text}' já está na lista!*",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove(selective=True)
            )
            return
        
        # Adicionar item
        shopping_lists[chat_id]['items'].append(text)
        user_states[state_key] = STATE_NONE
        
        items = shopping_lists[chat_id]['items']
        list_text = get_list_text(items)
        
        await update.message.reply_text(
            f"✅ *'{text}' adicionado por {user_name}!*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove(selective=True)
        )
        await update.message.reply_text(list_text, parse_mode='Markdown')
    
    # Estado: Removendo item
    elif current_state == STATE_REMOVING:
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        items = shopping_lists[chat_id]['items']
        
        try:
            index = int(text) - 1
            
            if index < 0 or index >= len(items):
                await update.message.reply_text(
                    f"❌ *{user_name}, número inválido!* (1 a {len(items)})",
                    parse_mode='Markdown',
                    reply_to_message_id=update.message.message_id
                )
                return
            
            removed_item = items.pop(index)
            user_states[state_key] = STATE_NONE
            
            list_text = get_list_text(items)
            
            await update.message.reply_text(
                f"✅ *'{removed_item}' removido por {user_name}!*",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove(selective=True)
            )
            await update.message.reply_text(list_text, parse_mode='Markdown')
            
        except ValueError:
            await update.message.reply_text(
                f"❌ *{user_name}, digite apenas o número do item*",
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
    
    # Botão Adicionar - Inicia o processo diretamente
    if query.data == 'action_add':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        user_states[state_key] = STATE_ADDING
        
        await query.message.reply_text(
            f"📝 *{user_name}, qual item você quer adicionar?*\n\n_Digite o nome ou /cancel para cancelar_",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
    
    # Botão Ver Lista
    elif query.data == 'action_list':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        items = shopping_lists[chat_id]['items']
        list_text = get_list_text(items)
        await query.message.reply_text(list_text, parse_mode='Markdown')
    
    # Botão Remover - Inicia o processo diretamente
    elif query.data == 'action_remove':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        items = shopping_lists[chat_id]['items']
        
        if not items:
            await query.message.reply_text(
                "📋 *A lista está vazia!*",
                parse_mode='Markdown'
            )
            return
        
        user_states[state_key] = STATE_REMOVING
        
        list_text = get_list_text(items)
        
        await query.message.reply_text(list_text, parse_mode='Markdown')
        await query.message.reply_text(
            f"🗑️ *{user_name}, digite o número do item a remover:*\n\n_Ou /cancel para cancelar_",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
    
    # Botão Limpar
    elif query.data == 'action_clear':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        if not shopping_lists[chat_id]['items']:
            await query.message.reply_text(
                "📋 *A lista já está vazia!*",
                parse_mode='Markdown'
            )
            return
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Sim, limpar", callback_data='confirm_clear'),
                InlineKeyboardButton("❌ Cancelar", callback_data='cancel_clear')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            "⚠️ *Tem certeza que quer limpar TODA a lista?*",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    # Botão Ajuda
    elif query.data == 'action_help':
        help_text = (
            "📚 *GUIA DE USO*\n\n"
            "*🛒 Adicionar:* /add\n"
            "*📋 Ver Lista:* /list\n"
            "*❌ Remover:* /remove\n"
            "*🗑️ Limpar:* /clear\n"
            "*🚫 Cancelar:* /cancel\n\n"
            "💡 Use os botões ou comandos!"
        )
        await query.message.reply_text(help_text, parse_mode='Markdown')
    
    # Confirmação de limpeza
    elif query.data == 'confirm_clear':
        if chat_id not in shopping_lists:
            shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
        
        shopping_lists[chat_id]['items'] = []
        await query.edit_message_text(
            f"🗑️ *Lista limpa por {user_name}!*",
            parse_mode='Markdown'
        )
    
    elif query.data == 'cancel_clear':
        await query.edit_message_text(
            "❌ *Cancelado*",
            parse_mode='Markdown'
        )


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
    
    # Registrar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", show_list))
    application.add_handler(CommandHandler("add", add_item_command))
    application.add_handler(CommandHandler("remove", remove_item_command))
    application.add_handler(CommandHandler("clear", clear_list_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Handler para mensagens de texto (processa baseado no estado)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    application.post_init = set_bot_commands
    
    logger.info("🤖 Bot iniciado! Pressione Ctrl+C para parar.")
    application.run_polling()


if __name__ == '__main__':
    main()
