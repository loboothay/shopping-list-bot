#!/usr/bin/env python3
"""
Bot de Lista de Mercado para Telegram - Com Modo Mercado (HTML)
Usa HTML para texto riscado funcionar corretamente.
"""

from __future__ import annotations

import logging
import os
import json
import asyncio
import unicodedata
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

# Cache de categorias já resolvidas (nome_lower -> categoria), evita reclassificar
category_cache = {}

# Categorias de supermercado, na ordem em que aparecem na lista
CATEGORY_ORDER = [
    'Hortifrúti',
    'Açougue',
    'Laticínios',
    'Padaria',
    'Mercearia',
    'Congelados',
    'Bebidas',
    'Limpeza',
    'Higiene',
    'Doces',
    'Pet',
    'Outros',
]

CATEGORY_EMOJI = {
    'Hortifrúti': '🥬',
    'Açougue': '🥩',
    'Laticínios': '🥛',
    'Padaria': '🍞',
    'Mercearia': '🥫',
    'Congelados': '🧊',
    'Bebidas': '🥤',
    'Limpeza': '🧴',
    'Higiene': '🧼',
    'Doces': '🍫',
    'Pet': '🐶',
    'Outros': '📦',
}

# Palavras-chave por categoria (representativo, não exaustivo). "Outros" é o fallback.
CATEGORY_KEYWORDS = {
    'Hortifrúti': [
        'alface', 'tomate', 'cebola', 'batata', 'cenoura', 'alho', 'banana', 'maca',
        'maça', 'laranja', 'limao', 'mamao', 'manga', 'uva', 'abacaxi', 'melancia',
        'morango', 'pera', 'abacate', 'brocolis', 'couve', 'espinafre', 'pepino',
        'pimentao', 'abobrinha', 'abobora', 'mandioca', 'beterraba', 'rucula',
        'salsinha', 'cheiro verde', 'coentro', 'gengibre', 'verdura', 'legume', 'fruta',
    ],
    'Açougue': [
        'carne', 'frango', 'file', 'bife', 'picanha', 'alcatra', 'costela', 'linguica',
        'salsicha', 'bacon', 'peixe', 'tilapia', 'salmao', 'camarao', 'porco', 'pernil',
        'coxa', 'sobrecoxa', 'asa', 'moida', 'patinho', 'maminha', 'fraldinha', 'cupim',
    ],
    'Laticínios': [
        'leite', 'queijo', 'iogurte', 'manteiga', 'requeijao', 'creme de leite', 'nata',
        'mussarela', 'muçarela', 'parmesao', 'ricota', 'cream cheese', 'leite condensado',
        'margarina', 'danone', 'coalhada',
    ],
    'Padaria': [
        'pao', 'paes', 'paozinho', 'bisnaga', 'baguete', 'bolo', 'biscoito', 'bolacha',
        'torrada', 'croissant', 'rosca', 'sonho', 'broa',
    ],
    'Mercearia': [
        'arroz', 'feijao', 'macarrao', 'massa', 'acucar', 'sal', 'oleo', 'azeite',
        'cafe', 'farinha', 'fuba', 'molho', 'extrato', 'milho', 'ervilha', 'atum',
        'sardinha', 'tempero', 'vinagre', 'fermento', 'aveia', 'granola', 'cereal',
        'achocolatado', 'leite em po', 'lentilha', 'grao de bico', 'amido', 'gelatina',
        'ovo', 'ovos',
    ],
    'Congelados': [
        'sorvete', 'pizza', 'hamburguer', 'nuggets', 'lasanha', 'congelado', 'polpa',
        'batata frita', 'pao de queijo', 'empanado', 'gelo',
    ],
    'Bebidas': [
        'refrigerante', 'coca', 'guarana', 'suco', 'agua', 'cerveja', 'vinho', 'energetico',
        'cha', 'isotonico', 'whisky', 'vodka', 'champagne', 'refresco',
    ],
    'Limpeza': [
        'detergente', 'sabao', 'amaciante', 'desinfetante', 'agua sanitaria', 'cloro',
        'multiuso', 'limpa vidro', 'esponja', 'saco de lixo', 'alvejante', 'lustra movel',
        'vassoura', 'rodo', 'pano', 'cera',
    ],
    'Higiene': [
        'shampoo', 'condicionador', 'sabonete', 'papel higienico', 'pasta de dente',
        'creme dental', 'escova de dente', 'desodorante', 'absorvente', 'fralda',
        'algodao', 'cotonete', 'fio dental', 'lenço', 'lamina', 'barbear', 'hidratante',
    ],
    'Doces': [
        'chocolate', 'bombom', 'bala', 'chiclete', 'pirulito', 'salgadinho', 'doce',
        'paçoca', 'pacoca', 'brigadeiro', 'goma', 'pipoca', 'amendoim',
    ],
    'Pet': [
        'racao', 'petisco', 'areia', 'sache', 'osso', 'antipulga',
    ],
}


def get_user_state_key(chat_id, user_id):
    return f"{chat_id}_{user_id}"


def _normalize(text: str) -> str:
    """Minúsculas e sem acentos, para casar palavras-chave"""
    text = text.lower().strip()
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def categorize_local(name: str) -> str | None:
    """Tenta categorizar pelo dicionário local. Retorna a categoria ou None."""
    norm = _normalize(name)
    if norm in category_cache:
        return category_cache[norm]

    words = norm.split()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            kw_norm = _normalize(kw)
            if ' ' in kw_norm:
                # keyword composta (ex.: "creme de leite"): casa como substring
                match = kw_norm in norm
            else:
                # keyword simples: casa palavra inteira, com plural simples (+s/+es)
                match = any(
                    w == kw_norm or w == kw_norm + 's' or w == kw_norm + 'es'
                    for w in words
                )
            if match:
                category_cache[norm] = category
                return category
    return None


async def categorize_ai(names: list) -> dict:
    """Classifica itens desconhecidos via Claude API, em uma única chamada (batch).

    Degrada para 'Outros' se ANTHROPIC_API_KEY não estiver setada ou a chamada falhar.
    """
    if not names:
        return {}

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return {name: 'Outros' for name in names}

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        categorias = ', '.join(CATEGORY_ORDER)
        system_prompt = (
            "Você classifica itens de compras de supermercado em categorias. "
            f"Categorias permitidas (use EXATAMENTE estes nomes): {categorias}. "
            "Responda APENAS com um objeto JSON mapeando cada item recebido à sua categoria, "
            "sem texto extra. Se não souber, use 'Outros'."
        )

        message = await client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1024,
            system=[
                {
                    'type': 'text',
                    'text': system_prompt,
                    'cache_control': {'type': 'ephemeral'},
                }
            ],
            messages=[
                {
                    'role': 'user',
                    'content': 'Classifique estes itens: ' + json.dumps(names, ensure_ascii=False),
                }
            ],
        )

        raw = message.content[0].text.strip()
        # Remove cercas de código se vierem
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        result = {}
        for name in names:
            category = parsed.get(name, 'Outros')
            if category not in CATEGORY_ORDER:
                category = 'Outros'
            result[name] = category
            category_cache[_normalize(name)] = category
        return result

    except Exception as e:
        logger.warning(f"⚠️ Falha ao categorizar com IA: {e}")
        return {name: 'Outros' for name in names}


async def categorize_items(names: list) -> dict:
    """Categorização híbrida: dicionário local primeiro, IA só para os desconhecidos."""
    result = {}
    unknown = []
    for name in names:
        local = categorize_local(name)
        if local:
            result[name] = local
        else:
            unknown.append(name)

    if unknown:
        ai_result = await categorize_ai(unknown)
        result.update(ai_result)

    return result


def sort_items_by_category(items: list) -> None:
    """Ordena a lista in-place por CATEGORY_ORDER (stable: preserva ordem de inserção)."""
    order = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}
    items.sort(key=lambda item: order.get(item.get('category', 'Outros'), len(CATEGORY_ORDER)))


def init_list(chat_id):
    """Inicializa lista se não existir"""
    if chat_id not in shopping_lists:
        shopping_lists[chat_id] = {'items': [], 'created_at': datetime.now()}


def get_list_text(items: list, show_status: bool = True) -> str:
    """Formata a lista de compras agrupada por categoria, usando HTML.

    A numeração é sequencial e contínua entre os grupos. Como a lista é mantida
    ordenada por categoria (sort_items_by_category), o número exibido coincide com
    o índice do item na lista, o que mantém a remoção por número funcionando.
    """
    if not items:
        return "📋 Lista vazia"

    lines = []
    counter = 0
    for category in CATEGORY_ORDER:
        group = [item for item in items if item.get('category', 'Outros') == category]
        if not group:
            continue

        emoji = CATEGORY_EMOJI.get(category, '📦')
        lines.append(f"\n{emoji} <b>{category}</b>")

        for item in group:
            counter += 1
            name = item['name']
            bought = item.get('bought', False)

            if show_status and bought:
                # Usa <s> para texto riscado em HTML
                lines.append(f"{counter}. <s>{name}</s> ✅")
            else:
                lines.append(f"{counter}. {name}")

    return "\n".join(lines).strip()


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
                text=f"📝 <b>{user_name}</b>, digite o(s) item(ns) — separe vários por vírgula:",
                parse_mode='HTML',
                reply_markup=get_cancel_keyboard()
            )
            return
        except BadRequest:
            pass
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"📝 <b>{user_name}</b>, digite o(s) item(ns) — separe vários por vírgula:",
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
                text=f"📋 <b>Lista:</b>\n{list_text}\n\n🗑️ <b>{user_name}</b>, digite o(s) número(s) — separe vários por vírgula:",
                parse_mode='HTML',
                reply_markup=get_cancel_keyboard()
            )
            return
        except BadRequest:
            pass
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"📋 <b>Lista:</b>\n{list_text}\n\n🗑️ <b>{user_name}</b>, digite o(s) número(s) — separe vários por vírgula:",
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
    
    # ADICIONANDO (um ou vários itens separados por vírgula)
    if current_state == STATE_ADDING:
        init_list(chat_id)

        # Separa por vírgula e limpa
        parts = [p.strip() for p in text.split(',') if p.strip()]

        items_names = [item['name'].lower() for item in shopping_lists[chat_id]['items']]
        to_add = []      # nomes válidos e novos
        ignored = []     # nomes ignorados (curtos ou duplicados)

        for part in parts:
            if len(part) < 2:
                ignored.append(part)
                continue
            lower = part.lower()
            if lower in items_names or lower in [n.lower() for n in to_add]:
                ignored.append(part)
                continue
            to_add.append(part)

        user_states[state_key] = STATE_NONE

        if not to_add:
            msg = await context.bot.send_message(chat_id=chat_id, text="⚠️ <b>Nada novo para adicionar.</b>", parse_mode='HTML')
            await asyncio.sleep(1.5)
            await delete_message_safe(context, chat_id, msg.message_id)
            await update_menu(context, chat_id)
            return

        # Mensagem transitória enquanto organiza (a categorização pode chamar a IA)
        organizing = await context.bot.send_message(chat_id=chat_id, text="🧠 <b>Organizando...</b>", parse_mode='HTML')

        categories = await categorize_items(to_add)

        for name in to_add:
            shopping_lists[chat_id]['items'].append({
                'name': name,
                'bought': False,
                'category': categories.get(name, 'Outros'),
            })
        sort_items_by_category(shopping_lists[chat_id]['items'])

        await delete_message_safe(context, chat_id, organizing.message_id)

        resumo = ", ".join(f"+{n}" for n in to_add)
        texto = f"✅ <b>{resumo}</b>"
        if ignored:
            texto += f"\n⚠️ Ignorado(s): {', '.join(ignored)}"
        msg = await context.bot.send_message(chat_id=chat_id, text=texto, parse_mode='HTML')
        await asyncio.sleep(1.2)
        await delete_message_safe(context, chat_id, msg.message_id)
        await update_menu(context, chat_id)
    
    # REMOVENDO (um ou vários números separados por vírgula)
    elif current_state == STATE_REMOVING:
        init_list(chat_id)
        items = shopping_lists[chat_id]['items']

        parts = [p.strip() for p in text.split(',') if p.strip()]

        indices = set()      # índices válidos (0-based)
        invalid = []         # entradas inválidas (não número ou fora do intervalo)

        for part in parts:
            try:
                num = int(part)
            except ValueError:
                invalid.append(part)
                continue
            if num < 1 or num > len(items):
                invalid.append(part)
                continue
            indices.add(num - 1)

        if not indices:
            msg = await context.bot.send_message(chat_id=chat_id, text=f"❌ <b>Digite número(s) de 1 a {len(items)}, separados por vírgula!</b>", parse_mode='HTML')
            await asyncio.sleep(2)
            await delete_message_safe(context, chat_id, msg.message_id)
            return

        # Remove em ordem decrescente para não bagunçar os índices
        removed = []
        for index in sorted(indices, reverse=True):
            removed.append(items.pop(index)['name'])
        removed.reverse()

        user_states[state_key] = STATE_NONE

        resumo = ", ".join(f"-{n}" for n in removed)
        texto = f"✅ <b>{resumo}</b>"
        if invalid:
            texto += f"\n⚠️ Inválido(s): {', '.join(invalid)}"
        msg = await context.bot.send_message(chat_id=chat_id, text=texto, parse_mode='HTML')
        await asyncio.sleep(1.2)
        await delete_message_safe(context, chat_id, msg.message_id)
        await update_menu(context, chat_id)


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
            f"📝 <b>{user_name}</b>, digite o(s) item(ns) — separe vários por vírgula:",
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
            f"📋 <b>Lista:</b>\n{list_text}\n\n🗑️ <b>{user_name}</b>, digite o(s) número(s) — separe vários por vírgula:",
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
