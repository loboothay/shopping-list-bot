#!/usr/bin/env python3
"""
Bot de Lista de Mercado para Telegram - Versão Final
Permite que membros do grupo gerenciem uma lista de compras compartilhada com interface elegante.
Inclui menu de comandos interativo.
"""

import logging
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
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

# Estados da conversa
ADDING_ITEM = 1
REMOVING_ITEM = 2

# Dicionário para armazenar listas por grupo com metadados
shopping_lists = {}


def get_list_text(items: list, show_count: bool = True) -> str:
    """Formata a lista de compras para exibição com estilo profissional"""
    if not items:
        return "📋 *Lista de Compras Vazia*\n\n_Comece adicionando itens com /add_"
    
    text = "📋 *LISTA DE COMPRAS*\n"
    text += "━" * 30 + "\n\n"
    
    for i, item in enumerate(items, 1):
        text += f"{i}. ✓ {item}\n"
    
    text += "\n" + "━" * 30
    
    if show_count:
        text += f"\n\n📊 *Total:* {len(items)} item(ns)"
    
    return text


async def set_bot_commands(application: Application) -> None:
    """Define os comandos do bot que aparecem no menu /"""
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
    """Comando /start - Apresenta o bot com mensagem profissional"""
    chat_id = update.effective_chat.id
    
    # Inicializar lista se não existir
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {
            'items': [],
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
    
    # Mensagem de boas-vindas com botões
    welcome_text = (
        "👋 *Bem-vindo ao Bot de Lista de Mercado!*\n\n"
        "Gerenciador de compras compartilhado para sua família.\n\n"
        "Toque em um comando abaixo para começar:"
    )
    
    # Criar botões com os comandos principais
    keyboard = [
        [InlineKeyboardButton("🛒 Adicionar Item", callback_data='cmd_add')],
        [InlineKeyboardButton("📋 Ver Lista", callback_data='cmd_list')],
        [InlineKeyboardButton("❌ Remover Item", callback_data='cmd_remove')],
        [InlineKeyboardButton("🗑️ Limpar Lista", callback_data='cmd_clear')],
        [InlineKeyboardButton("❓ Ajuda", callback_data='cmd_help')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=reply_markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /help - Mostra ajuda detalhada"""
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
        "💡 Qualquer membro pode adicionar/remover itens!"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /list - Mostra a lista atual com formatação profissional"""
    chat_id = update.effective_chat.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {
            'items': [],
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
    
    items = shopping_lists[chat_id]['items']
    list_text = get_list_text(items)
    
    await update.message.reply_text(list_text, parse_mode='Markdown')


async def add_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Comando /add - Inicia processo de adicionar item"""
    chat_id = update.effective_chat.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {
            'items': [],
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
    
    reply_keyboard = [["❌ Cancelar"]]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(
        "📝 *Qual item você quer adicionar?*",
        parse_mode='Markdown',
        reply_markup=markup
    )
    
    return ADDING_ITEM


async def receive_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o item a ser adicionado"""
    chat_id = update.effective_chat.id
    item_name = update.message.text.strip()
    
    if item_name.lower() == "❌ cancelar" or item_name.lower() == "cancelar":
        await update.message.reply_text(
            "❌ *Operação cancelada*",
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
    
    # Evitar duplicatas (case-insensitive)
    items_lower = [item.lower() for item in shopping_lists[chat_id]['items']]
    if item_name.lower() in items_lower:
        await update.message.reply_text(
            f"⚠️ *Aviso:* '{item_name}' já está na lista!",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    # Adicionar item
    shopping_lists[chat_id]['items'].append(item_name)
    shopping_lists[chat_id]['updated_at'] = datetime.now()
    
    items = shopping_lists[chat_id]['items']
    list_text = get_list_text(items)
    
    await update.message.reply_text(
        f"✅ *Sucesso!*\n\n'{item_name}' foi adicionado!",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Enviar a lista em uma mensagem separada
    await update.message.reply_text(list_text, parse_mode='Markdown')
    
    return ConversationHandler.END


async def remove_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Comando /remove - Inicia processo de remover item"""
    chat_id = update.effective_chat.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {
            'items': [],
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
    
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
    
    await update.message.reply_text(
        list_text,
        parse_mode='Markdown'
    )
    
    await update.message.reply_text(
        "🗑️ *Digite o número do item a remover:*",
        parse_mode='Markdown',
        reply_markup=markup
    )
    
    return REMOVING_ITEM


async def receive_removal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o número do item a ser removido"""
    chat_id = update.effective_chat.id
    user_input = update.message.text.strip()
    
    if user_input.lower() == "❌ cancelar" or user_input.lower() == "cancelar":
        await update.message.reply_text(
            "❌ *Operação cancelada*",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    items = shopping_lists[chat_id]['items']
    
    try:
        index = int(user_input) - 1
        
        if index < 0 or index >= len(items):
            await update.message.reply_text(
                f"❌ *Erro:* Número inválido! (1 a {len(items)})",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        removed_item = items.pop(index)
        shopping_lists[chat_id]['updated_at'] = datetime.now()
        
        list_text = get_list_text(items)
        
        await update.message.reply_text(
            f"✅ *Sucesso!*\n\n'{removed_item}' foi removido!",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Enviar a lista em uma mensagem separada
        await update.message.reply_text(list_text, parse_mode='Markdown')
        
    except ValueError:
        await update.message.reply_text(
            "❌ *Erro:* Digite apenas o número do item",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return REMOVING_ITEM
    
    return ConversationHandler.END


async def clear_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /clear - Limpa a lista com confirmação"""
    chat_id = update.effective_chat.id
    
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {
            'items': [],
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
    
    if not shopping_lists[chat_id]['items']:
        await update.message.reply_text(
            "📋 *A lista já está vazia!*",
            parse_mode='Markdown'
        )
        return
    
    # Criar botões de confirmação
    keyboard = [
        [
            InlineKeyboardButton("✅ Sim, limpar", callback_data='confirm_clear'),
            InlineKeyboardButton("❌ Cancelar", callback_data='cancel_clear')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚠️ *Confirmação*\n\n"
        "Tem certeza que deseja limpar TODA a lista?",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa cliques nos botões do menu"""
    query = update.callback_query
    chat_id = query.message.chat_id
    
    # Processar cliques do menu de boas-vindas
    if query.data == 'cmd_add':
        await query.answer()
        await add_item(query, context)
    
    elif query.data == 'cmd_list':
        await query.answer()
        await show_list(query, context)
    
    elif query.data == 'cmd_remove':
        await query.answer()
        await remove_item(query, context)
    
    elif query.data == 'cmd_clear':
        await query.answer()
        await clear_list(query, context)
    
    elif query.data == 'cmd_help':
        await query.answer()
        await help_command(query, context)
    
    # Processar confirmação de limpeza
    elif query.data == 'confirm_clear':
        shopping_lists[chat_id]['items'] = []
        shopping_lists[chat_id]['updated_at'] = datetime.now()
        
        await query.edit_message_text(
            "🗑️ *Lista limpa com sucesso!*",
            parse_mode='Markdown'
        )
    
    elif query.data == 'cancel_clear':
        await query.edit_message_text(
            "❌ *Operação cancelada*",
            parse_mode='Markdown'
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela a operação atual"""
    await update.message.reply_text(
        "❌ *Operação cancelada*",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


def main() -> None:
    """Inicia o bot"""
    # Ler o token da variável de ambiente
    bot_token = os.getenv('BOT_TOKEN')
    
    # Verificar se o token foi fornecido
    if not bot_token:
        logger.error("❌ ERRO: Variável de ambiente 'BOT_TOKEN' não encontrada!")
        logger.error("Execute: export BOT_TOKEN='seu_token_aqui'")
        return
    
    # Verificar se o token parece válido
    if bot_token == "YOUR_BOT_TOKEN":
        logger.error("❌ ERRO: Você ainda está usando o placeholder 'YOUR_BOT_TOKEN'")
        logger.error("Substitua pelo seu token real do BotFather")
        return
    
    logger.info(f"✅ Token detectado: {bot_token[:20]}...")
    
    # Criar a aplicação
    application = Application.builder().token(bot_token).build()
    
    # Handlers de conversação para add e remove
    add_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_item)],
        states={
            ADDING_ITEM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_item)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    remove_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("remove", remove_item)],
        states={
            REMOVING_ITEM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_removal)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Registrar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", show_list))
    application.add_handler(CommandHandler("clear", clear_list))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(add_conv_handler)
    application.add_handler(remove_conv_handler)
    
    # Configurar comandos do bot
    application.post_init = set_bot_commands
    
    # Iniciar o bot
    logger.info("🤖 Bot iniciado! Pressione Ctrl+C para parar.")
    application.run_polling()


if __name__ == '__main__':
    main()
