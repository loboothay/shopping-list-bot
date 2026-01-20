#!/usr/bin/env python3
"""
Bot de Lista de Mercado para Telegram - Versão Estável
Permite que membros do grupo gerenciem uma lista de compras compartilhada.
Versão simplificada e confiável com comandos tradicionais.
"""

import logging
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados da conversa
ADDING_ITEM = 1
REMOVING_ITEM = 2

# Dicionário para armazenar listas por grupo
shopping_lists = {}


def get_list_text(items: list) -> str:
    """Formata a lista de compras para exibição"""
    if not items:
        return "📋 *Lista de Compras Vazia*\n\n_Use /add para começar!_"
    
    text = "📋 *LISTA DE COMPRAS*\n"
    text += "━" * 30 + "\n\n"
    
    for i, item in enumerate(items, 1):
        text += f"{i}. ✓ {item}\n"
    
    text += "\n" + "━" * 30
    text += f"\n\n📊 *Total:* {len(items)} item(ns)"
    
    return text


async def set_bot_commands(application: Application) -> None:
    """Define os comandos do bot"""
    commands = [
        BotCommand("start", "Iniciar o bot"),
        BotCommand("add", "Adicionar item à lista"),
        BotCommand("list", "Ver lista de compras"),
        BotCommand("remove", "Remover item da lista"),
        BotCommand("clear", "Limpar toda a lista"),
        BotCommand("help", "Ver ajuda"),
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
        "*Comandos Disponíveis:*\n"
        "🛒 /add - Adicionar item\n"
        "📋 /list - Ver lista\n"
        "❌ /remove - Remover item\n"
        "🗑️ /clear - Limpar lista\n"
        "❓ /help - Ajuda\n\n"
        "💡 Comece com /add!"
    )
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')


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
        "💡 Qualquer membro pode adicionar/remover!"
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


async def add_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Comando /add - Inicia adição de item"""
    chat_id = update.effective_chat.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    reply_keyboard = [["❌ Cancelar"]]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(
        "📝 *Qual item você quer adicionar?*",
        parse_mode='Markdown',
        reply_markup=markup
    )
    
    return ADDING_ITEM


async def receive_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o nome do item"""
    chat_id = update.effective_chat.id
    item_name = update.message.text.strip()
    
    if item_name.lower() == "❌ cancelar" or item_name.lower() == "cancelar":
        await update.message.reply_text(
            "❌ *Cancelado*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    if not item_name or len(item_name) < 2:
        await update.message.reply_text(
            "❌ *Erro:* Nome muito curto (mínimo 2 caracteres)",
            parse_mode='Markdown'
        )
        return ADDING_ITEM
    
    # Evitar duplicatas
    items_lower = [item.lower() for item in shopping_lists[chat_id]['items']]
    if item_name.lower() in items_lower:
        await update.message.reply_text(
            f"⚠️ *'{item_name}' já está na lista!*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    # Adicionar item
    shopping_lists[chat_id]['items'].append(item_name)
    items = shopping_lists[chat_id]['items']
    list_text = get_list_text(items)
    
    await update.message.reply_text(
        f"✅ *'{item_name}' adicionado!*",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    
    await update.message.reply_text(list_text, parse_mode='Markdown')
    
    return ConversationHandler.END


async def remove_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Comando /remove - Inicia remoção"""
    chat_id = update.effective_chat.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}
    
    items = shopping_lists[chat_id]['items']
    
    if not items:
        await update.message.reply_text(
            "📋 *A lista está vazia!*",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    list_text = get_list_text(items)
    reply_keyboard = [["❌ Cancelar"]]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(list_text, parse_mode='Markdown')
    await update.message.reply_text(
        "🗑️ *Digite o número do item a remover:*",
        parse_mode='Markdown',
        reply_markup=markup
    )
    
    return REMOVING_ITEM


async def receive_removal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o número do item a remover"""
    chat_id = update.effective_chat.id
    user_input = update.message.text.strip()
    
    if user_input.lower() == "❌ cancelar" or user_input.lower() == "cancelar":
        await update.message.reply_text(
            "❌ *Cancelado*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    items = shopping_lists[chat_id]['items']
    
    try:
        index = int(user_input) - 1
        
        if index < 0 or index >= len(items):
            await update.message.reply_text(
                f"❌ *Número inválido! (1 a {len(items)})*",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        removed_item = items.pop(index)
        list_text = get_list_text(items)
        
        await update.message.reply_text(
            f"✅ *'{removed_item}' removido!*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        
        await update.message.reply_text(list_text, parse_mode='Markdown')
        
    except ValueError:
        await update.message.reply_text(
            "❌ *Digite apenas o número do item*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return REMOVING_ITEM
    
    return ConversationHandler.END


async def clear_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    
    # Pedir confirmação
    reply_keyboard = [["✅ Sim, limpar", "❌ Cancelar"]]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(
        "⚠️ *Tem certeza que quer limpar TODA a lista?*",
        parse_mode='Markdown',
        reply_markup=markup
    )
    
    context.user_data['waiting_clear_confirmation'] = True


async def handle_clear_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa confirmação de limpeza"""
    chat_id = update.effective_chat.id
    response = update.message.text.strip()
    
    if response == "✅ Sim, limpar":
        shopping_lists[chat_id]['items'] = []
        await update.message.reply_text(
            "🗑️ *Lista limpa com sucesso!*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text(
            "❌ *Cancelado*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
    
    context.user_data['waiting_clear_confirmation'] = False


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela operação"""
    await update.message.reply_text(
        "❌ *Cancelado*",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


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
    
    # Handlers de conversação
    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_item)],
        states={
            ADDING_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_item)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    remove_conv = ConversationHandler(
        entry_points=[CommandHandler("remove", remove_item)],
        states={
            REMOVING_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_removal)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Registrar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", show_list))
    application.add_handler(CommandHandler("clear", clear_list))
    application.add_handler(add_conv)
    application.add_handler(remove_conv)
    
    # Handler para confirmação de limpeza
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^(✅ Sim, limpar|❌ Cancelar)$"),
        handle_clear_confirmation
    ))
    
    application.post_init = set_bot_commands
    
    logger.info("🤖 Bot iniciado! Pressione Ctrl+C para parar.")
    application.run_polling()


if __name__ == '__main__':
    main()
