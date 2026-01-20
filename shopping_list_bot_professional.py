#!/usr/bin/env python3
"""
Bot de Lista de Mercado para Telegram - Versão Profissional
Permite que membros do grupo gerenciem uma lista de compras compartilhada com interface elegante.
"""

import logging
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
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
EDITING_ITEM = 3

# Dicionário para armazenar listas por grupo com metadados
shopping_lists = {}


def get_list_text(items: list, show_count: bool = True) -> str:
    """Formata a lista de compras para exibição com estilo profissional"""
    if not items:
        return "📋 *Lista de Compras Vazia*\n\n_Comece adicionando itens com /add_"
    
    text = "📋 *LISTA DE COMPRAS*\n"
    text += "━" * 40 + "\n\n"
    
    for i, item in enumerate(items, 1):
        text += f"  {i}. ✓ {item}\n"
    
    text += "\n" + "━" * 40
    
    if show_count:
        text += f"\n\n📊 *Total:* {len(items)} item(ns)"
        text += f"\n⏰ *Atualizado em:* {datetime.now().strftime('%H:%M')}"
    
    return text


def get_welcome_message() -> str:
    """Retorna mensagem de boas-vindas formatada profissionalmente"""
    return (
        "👋 *Bem-vindo ao Bot de Lista de Mercado!*\n\n"
        "Este bot ajuda sua família a gerenciar uma lista de compras compartilhada de forma simples e eficiente.\n\n"
        "━" * 40 + "\n"
        "*📌 COMANDOS DISPONÍVEIS:*\n\n"
        "🛒 */add* - Adicionar item à lista\n"
        "❌ */remove* - Remover item da lista\n"
        "📋 */list* - Ver lista completa\n"
        "🗑️ */clear* - Limpar toda a lista\n"
        "❓ */help* - Ver ajuda detalhada\n"
        "ℹ️ */info* - Informações sobre o bot\n\n"
        "━" * 40 + "\n"
        "💡 *Dica:* Use /add para começar!"
    )


def get_help_message() -> str:
    """Retorna mensagem de ajuda detalhada"""
    return (
        "📚 *GUIA DE USO - Bot de Lista de Mercado*\n\n"
        "━" * 40 + "\n\n"
        "*🛒 Adicionando Itens*\n"
        "Digite: /add\n"
        "O bot pedirá o nome do item\n"
        "Exemplo: Leite, Pão, Ovos\n\n"
        "*❌ Removendo Itens*\n"
        "Digite: /remove\n"
        "O bot mostrará a lista com números\n"
        "Digite o número do item a remover\n\n"
        "*📋 Visualizando a Lista*\n"
        "Digite: /list\n"
        "Mostra todos os itens com números\n\n"
        "*🗑️ Limpando a Lista*\n"
        "Digite: /clear\n"
        "Remove TODOS os itens (cuidado!)\n\n"
        "━" * 40 + "\n\n"
        "*💡 Dicas Úteis:*\n"
        "• Qualquer membro pode adicionar/remover itens\n"
        "• A lista é compartilhada com todos\n"
        "• Use /list para ver o estado atual\n"
        "• Não há limite de itens\n"
        "• Os itens não podem ser duplicados\n"
    )


def get_info_message() -> str:
    """Retorna informações sobre o bot"""
    return (
        "ℹ️ *INFORMAÇÕES DO BOT*\n\n"
        "━" * 40 + "\n\n"
        "*Versão:* 2.0 Professional\n"
        "*Função:* Gerenciador de Lista de Compras\n"
        "*Desenvolvido por:* Manus AI\n\n"
        "*Recursos:*\n"
        "✅ Interface profissional e intuitiva\n"
        "✅ Suporte a múltiplos grupos\n"
        "✅ Sem limite de itens\n"
        "✅ Validação de duplicatas\n"
        "✅ Formatação elegante\n\n"
        "━" * 40 + "\n\n"
        "*Dúvidas?* Use /help para mais informações"
    )


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
    
    welcome_text = get_welcome_message()
    await update.message.reply_text(welcome_text, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /help - Mostra ajuda detalhada"""
    help_text = get_help_message()
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /info - Mostra informações do bot"""
    info_text = get_info_message()
    await update.message.reply_text(info_text, parse_mode='Markdown')


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
        "📝 *Qual item você quer adicionar?*\n\n"
        "_Digite o nome do item ou clique em Cancelar_",
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
            "❌ *Erro:* O nome do item deve ter pelo menos 2 caracteres",
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
        f"✅ *Sucesso!*\n\n'{item_name}' foi adicionado à lista!\n\n{list_text}",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    
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
            "📋 *A lista está vazia!*\n\n_Não há nada para remover_",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    list_text = get_list_text(items)
    reply_keyboard = [["❌ Cancelar"]]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"{list_text}\n\n"
        "🗑️ *Digite o número do item que deseja remover:*\n"
        "_(ou clique em Cancelar)_",
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
                f"❌ *Erro:* Número inválido!\n\n"
                f"_Use um número de 1 a {len(items)}_",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        removed_item = items.pop(index)
        shopping_lists[chat_id]['updated_at'] = datetime.now()
        
        list_text = get_list_text(items)
        await update.message.reply_text(
            f"✅ *Sucesso!*\n\n'{removed_item}' foi removido da lista!\n\n{list_text}",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        
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
        "Você tem certeza que deseja limpar TODA a lista?\n"
        "_Esta ação não pode ser desfeita!_",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback para confirmação de limpeza"""
    query = update.callback_query
    chat_id = query.message.chat_id
    
    if query.data == 'confirm_clear':
        shopping_lists[chat_id]['items'] = []
        shopping_lists[chat_id]['updated_at'] = datetime.now()
        
        await query.edit_message_text(
            "🗑️ *Lista limpa com sucesso!*\n\n"
            "_Use /add para adicionar novos itens_",
            parse_mode='Markdown'
        )
    else:
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
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("list", show_list))
    application.add_handler(CommandHandler("clear", clear_list))
    application.add_handler(CallbackQueryHandler(clear_callback))
    application.add_handler(add_conv_handler)
    application.add_handler(remove_conv_handler)
    
    # Iniciar o bot
    logger.info("🤖 Bot iniciado! Pressione Ctrl+C para parar.")
    application.run_polling()


if __name__ == '__main__':
    main()
