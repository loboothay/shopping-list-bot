#!/usr/bin/env python3
"""
Bot de Lista de Mercado para Telegram - Com Modo Mercado (HTML)
Usa HTML para texto riscado funcionar corretamente.
"""

from __future__ import annotations

import logging
import os
import re
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
STATE_EDIT_RENAME = 4
STATE_EDIT_QTY = 5

# Armazenamento (persistido em JSON: shopping_lists, category_cache, item_frequency)
shopping_lists = {}
user_states = {}
messages_to_delete = {}
menu_messages = {}

# Cache de categorias já resolvidas (nome_normalizado -> categoria), evita reclassificar
category_cache = {}

# Frequência de itens: nome_normalizado -> {'count', 'name', 'category'}
item_frequency = {}

# Estado de UI transitório (não persistido)
edit_target = {}        # state_key -> índice do item em edição
freq_suggestions = {}   # chat_id -> lista de nomes_normalizados sugeridos (mapeia o clique)

# Persistência em arquivo (Volume do Railway montado em /data)
DATA_DIR = os.getenv('DATA_DIR', '/data')
DATA_FILE = os.path.join(DATA_DIR, 'shopping_data.json')

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


def same_item(a: str, b: str) -> bool:
    """Mesmo item? Compara sem acento/maiúscula e tolera plural simples (+s/+es).

    Conservador: só funde quando um nome é exatamente o outro + 's'/'es'. Assim,
    'ovo'/'ovos' e 'banana'/'bananas' fundem, mas 'pão'/'pães' (irregular) e
    'leite'/'leite condensado' (nomes distintos) NÃO fundem.
    """
    na, nb = _normalize(a), _normalize(b)
    if na == nb:
        return True
    short, long = sorted((na, nb), key=len)
    return long == short + 's' or long == short + 'es'


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


# Captura quantidade no começo ("2x leite", "2 leite") ou no fim ("leite x2", "leite 2")
_QTY_PREFIX = re.compile(r'^(\d{1,2})\s*x?\s+(.+)$', re.IGNORECASE)
_QTY_SUFFIX = re.compile(r'^(.+?)\s+x?(\d{1,2})$', re.IGNORECASE)


def parse_quantity(text: str) -> tuple:
    """Extrai (quantidade, nome) de um texto. Sem número → quantidade 1. Limita 1–99."""
    text = text.strip()
    m = _QTY_PREFIX.match(text)
    if m:
        qty, name = int(m.group(1)), m.group(2).strip()
    else:
        m = _QTY_SUFFIX.match(text)
        if m:
            name, qty = m.group(1).strip(), int(m.group(2))
        else:
            return 1, text
    qty = max(1, min(qty, 99))
    return (qty, name) if name else (1, text)


def register_frequency(name: str, category: str) -> None:
    """Incrementa a frequência de um item (usado para sugerir os mais comprados)."""
    key = _normalize(name)
    if not key:
        return
    entry = item_frequency.get(key, {'count': 0, 'name': name, 'category': category})
    entry['count'] += 1
    entry['name'] = name
    entry['category'] = category
    item_frequency[key] = entry


def save_data() -> None:
    """Salva lista, cache de categorias e frequências em JSON (Volume do Railway)."""
    try:
        lists_serial = {}
        for chat_id, data in shopping_lists.items():
            created = data.get('created_at')
            lists_serial[str(chat_id)] = {
                'items': data.get('items', []),
                'created_at': created.isoformat() if isinstance(created, datetime) else created,
            }
        payload = {
            'shopping_lists': lists_serial,
            'category_cache': category_cache,
            'item_frequency': item_frequency,
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = DATA_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, DATA_FILE)
    except Exception as e:
        logger.warning(f"⚠️ Falha ao salvar dados: {e}")


def load_data() -> None:
    """Carrega os dados persistidos no startup (se o arquivo existir)."""
    try:
        if not os.path.exists(DATA_FILE):
            logger.info("ℹ️ Nenhum dado salvo ainda (primeira execução).")
            return
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            payload = json.load(f)

        for chat_id_str, data in payload.get('shopping_lists', {}).items():
            items = data.get('items', [])
            for item in items:
                # Migração suave de dados antigos
                item.setdefault('quantity', 1)
                item.setdefault('bought', False)
                item.setdefault('category', 'Outros')
            shopping_lists[int(chat_id_str)] = {
                'items': items,
                'created_at': data.get('created_at') or datetime.now().isoformat(),
            }

        category_cache.update(payload.get('category_cache', {}))
        item_frequency.update(payload.get('item_frequency', {}))
        logger.info(f"✅ Dados carregados: {len(shopping_lists)} lista(s).")
    except Exception as e:
        logger.warning(f"⚠️ Falha ao carregar dados: {e}")


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
            name = item_label(item)
            bought = item.get('bought', False)

            if show_status and bought:
                # Usa <s> para texto riscado em HTML
                lines.append(f"{counter}. <s>{name}</s> ✅")
            else:
                lines.append(f"{counter}. {name}")

    return "\n".join(lines).strip()


def item_label(item: dict) -> str:
    """Nome do item para exibição, com a quantidade na frente quando > 1."""
    name = item['name']
    qty = item.get('quantity', 1)
    return f"{qty}x {name}" if qty > 1 else name


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


def get_main_menu_keyboard(has_items: bool = False, has_frequent: bool = False):
    """Teclado do menu principal"""
    keyboard = [
        [
            InlineKeyboardButton("➕ Adicionar", callback_data='action_add'),
            InlineKeyboardButton("➖ Remover", callback_data='action_remove')
        ]
    ]

    if has_items:
        keyboard.append([
            InlineKeyboardButton("✏️ Editar", callback_data='action_edit'),
            InlineKeyboardButton("🛒 Modo Mercado", callback_data='action_market_mode')
        ])

    if has_frequent:
        keyboard.append([
            InlineKeyboardButton("⭐ Frequentes", callback_data='action_frequent')
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
        name = item_label(item)
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


def get_edit_list_keyboard(items: list):
    """Lista de itens para escolher qual editar (um botão por item)."""
    keyboard = [
        [InlineKeyboardButton(item_label(item), callback_data=f'edit_{i}')]
        for i, item in enumerate(items)
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data='action_cancel')])
    return InlineKeyboardMarkup(keyboard)


def get_edit_item_keyboard(index: int):
    """Submenu de edição de um item específico."""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Renomear", callback_data=f'editname_{index}'),
            InlineKeyboardButton("🔢 Quantidade", callback_data=f'editqty_{index}'),
        ],
        [
            InlineKeyboardButton("📂 Categoria", callback_data=f'editcat_{index}'),
            InlineKeyboardButton("🗑️ Remover", callback_data=f'editdel_{index}'),
        ],
        [InlineKeyboardButton("⬅️ Voltar", callback_data='action_edit')],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_edit_category_keyboard(index: int):
    """Botões de categoria para reclassificar um item manualmente."""
    keyboard = []
    row = []
    for cat_idx, category in enumerate(CATEGORY_ORDER):
        emoji = CATEGORY_EMOJI.get(category, '📦')
        row.append(InlineKeyboardButton(f"{emoji} {category}", callback_data=f'setcat_{index}_{cat_idx}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f'edit_{index}')])
    return InlineKeyboardMarkup(keyboard)


def has_frequent_items(chat_id: int) -> bool:
    """Há itens frequentes que ainda não estão na lista atual?"""
    return len(build_frequent_suggestions(chat_id)) > 0


def build_frequent_suggestions(chat_id: int, limit: int = 12) -> list:
    """Top itens por frequência que ainda não estão na lista. Retorna lista de chaves."""
    init_list(chat_id)
    in_list = {_normalize(it['name']) for it in shopping_lists[chat_id]['items']}
    ranked = sorted(item_frequency.items(), key=lambda kv: kv[1].get('count', 0), reverse=True)
    return [key for key, _ in ranked if key not in in_list][:limit]


def get_frequent_keyboard(chat_id: int):
    """Teclado de sugestões de itens frequentes. Guarda o mapeamento de índices."""
    keys = build_frequent_suggestions(chat_id)
    freq_suggestions[chat_id] = keys
    keyboard = []
    for i, key in enumerate(keys):
        entry = item_frequency.get(key, {})
        name = entry.get('name', key)
        count = entry.get('count', 0)
        keyboard.append([
            InlineKeyboardButton(f"➕ {name}  ·  {count}x", callback_data=f'addfreq_{i}')
        ])
    keyboard.append([InlineKeyboardButton("✔️ Pronto", callback_data='action_cancel')])
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
                reply_markup=get_main_menu_keyboard(has_items, has_frequent_items(chat_id))
            )
            return
        except BadRequest:
            pass
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=menu_text,
        parse_mode='HTML',
        reply_markup=get_main_menu_keyboard(has_items, has_frequent_items(chat_id))
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
        reply_markup=get_main_menu_keyboard(has_items, has_frequent_items(chat_id))
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
    
    # ADICIONANDO (um ou vários itens separados por vírgula; aceita quantidade "2x leite")
    if current_state == STATE_ADDING:
        init_list(chat_id)
        items = shopping_lists[chat_id]['items']

        # Separa por vírgula, extrai quantidade e funde duplicados do próprio lote
        # (incl. plural/singular via same_item). pending = [[qty, nome_exibido], ...]
        pending = []
        ignored = []
        for part in [p.strip() for p in text.split(',') if p.strip()]:
            qty, name = parse_quantity(part)
            if len(name) < 2:
                ignored.append(part)
                continue
            existing = next((p for p in pending if same_item(p[1], name)), None)
            if existing:
                existing[0] += qty
            else:
                pending.append([qty, name])

        user_states[state_key] = STATE_NONE

        if not pending:
            msg = await context.bot.send_message(chat_id=chat_id, text="⚠️ <b>Nada para adicionar.</b>", parse_mode='HTML')
            await asyncio.sleep(1.5)
            await delete_message_safe(context, chat_id, msg.message_id)
            await update_menu(context, chat_id)
            return

        # Mensagem transitória enquanto organiza (a categorização pode chamar a IA)
        organizing = await context.bot.send_message(chat_id=chat_id, text="🧠 <b>Organizando...</b>", parse_mode='HTML')

        # Casa cada pendente com um item já existente (plural/singular incluso)
        matches = [next((it for it in items if same_item(it['name'], name)), None) for qty, name in pending]
        new_names = [name for (qty, name), m in zip(pending, matches) if m is None]
        categories = await categorize_items(new_names) if new_names else {}

        added, updated = [], []
        for (qty, name), item in zip(pending, matches):
            if item is not None:
                # Item já existe (mesmo nome ou plural/singular): soma a quantidade
                item['quantity'] = min(item.get('quantity', 1) + qty, 99)
                updated.append(item_label(item))
                register_frequency(item['name'], item.get('category', 'Outros'))
            else:
                category = categories.get(name, 'Outros')
                items.append({'name': name, 'bought': False, 'category': category, 'quantity': qty})
                added.append(f"{qty}x {name}" if qty > 1 else name)
                register_frequency(name, category)

        sort_items_by_category(items)
        save_data()

        await delete_message_safe(context, chat_id, organizing.message_id)

        linhas = []
        if added:
            linhas.append("✅ " + ", ".join(f"+{n}" for n in added))
        if updated:
            linhas.append("🔁 " + ", ".join(updated))
        if ignored:
            linhas.append(f"⚠️ Ignorado(s): {', '.join(ignored)}")
        msg = await context.bot.send_message(chat_id=chat_id, text="<b>" + "\n".join(linhas) + "</b>", parse_mode='HTML')
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
        save_data()

        resumo = ", ".join(f"-{n}" for n in removed)
        texto = f"✅ <b>{resumo}</b>"
        if invalid:
            texto += f"\n⚠️ Inválido(s): {', '.join(invalid)}"
        msg = await context.bot.send_message(chat_id=chat_id, text=texto, parse_mode='HTML')
        await asyncio.sleep(1.2)
        await delete_message_safe(context, chat_id, msg.message_id)
        await update_menu(context, chat_id)

    # EDITANDO: renomear item
    elif current_state == STATE_EDIT_RENAME:
        init_list(chat_id)
        items = shopping_lists[chat_id]['items']
        index = edit_target.get(state_key)

        user_states[state_key] = STATE_NONE
        edit_target.pop(state_key, None)

        new_name = parse_quantity(text)[1].strip()
        if index is None or not (0 <= index < len(items)) or len(new_name) < 2:
            msg = await context.bot.send_message(chat_id=chat_id, text="❌ <b>Não consegui renomear.</b>", parse_mode='HTML')
            await asyncio.sleep(1.5)
            await delete_message_safe(context, chat_id, msg.message_id)
            await update_menu(context, chat_id)
            return

        organizing = await context.bot.send_message(chat_id=chat_id, text="🧠 <b>Organizando...</b>", parse_mode='HTML')
        category = (await categorize_items([new_name])).get(new_name, 'Outros')
        items[index]['name'] = new_name
        items[index]['category'] = category
        sort_items_by_category(items)
        save_data()
        await delete_message_safe(context, chat_id, organizing.message_id)
        await update_menu(context, chat_id)

    # EDITANDO: nova quantidade
    elif current_state == STATE_EDIT_QTY:
        init_list(chat_id)
        items = shopping_lists[chat_id]['items']
        index = edit_target.get(state_key)

        user_states[state_key] = STATE_NONE
        edit_target.pop(state_key, None)

        # Aceita "3" ou "3x" ou "x3"
        digits = re.findall(r'\d{1,2}', text)
        if index is None or not (0 <= index < len(items)) or not digits:
            msg = await context.bot.send_message(chat_id=chat_id, text="❌ <b>Digite um número (ex.: 3).</b>", parse_mode='HTML')
            await asyncio.sleep(1.5)
            await delete_message_safe(context, chat_id, msg.message_id)
            await update_menu(context, chat_id)
            return

        items[index]['quantity'] = max(1, min(int(digits[0]), 99))
        save_data()
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
                reply_markup=get_main_menu_keyboard(False, has_frequent_items(chat_id))
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
                reply_markup=get_main_menu_keyboard(False, has_frequent_items(chat_id))
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
            save_data()

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
        save_data()

        bought_count = sum(1 for item in items if item.get('bought', False))
        
        menu_text = get_main_menu_text(items)
        has_items = len(items) > 0
        
        await query.edit_message_text(
            f"✅ <b>Compras finalizadas!</b>\n{bought_count} item(ns) marcado(s)\n\n{menu_text}",
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(has_items, has_frequent_items(chat_id))
        )
    
    # CANCELAR MODO MERCADO
    elif query.data == 'market_cancel':
        user_states[state_key] = STATE_NONE
        
        items = shopping_lists[chat_id]['items']
        for item in items:
            item['bought'] = False
        save_data()

        menu_text = get_main_menu_text(items)
        has_items = len(items) > 0

        await query.edit_message_text(
            menu_text,
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(has_items, has_frequent_items(chat_id))
        )

    # REMOVER COMPRADOS
    elif query.data == 'market_clear_bought':
        items = shopping_lists[chat_id]['items']

        removed_count = sum(1 for item in items if item.get('bought', False))
        shopping_lists[chat_id]['items'] = [item for item in items if not item.get('bought', False)]
        save_data()

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
                reply_markup=get_main_menu_keyboard(False, has_frequent_items(chat_id))
            )
    
    # LIMPAR TUDO
    elif query.data == 'action_clear':
        if not shopping_lists[chat_id]['items']:
            await query.edit_message_text(
                "📋 <b>Lista já está vazia!</b>",
                parse_mode='HTML',
                reply_markup=get_main_menu_keyboard(False, has_frequent_items(chat_id))
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
            reply_markup=get_main_menu_keyboard(has_items, has_frequent_items(chat_id))
        )
    
    # CONFIRMAR LIMPEZA
    elif query.data == 'confirm_clear':
        shopping_lists[chat_id]['items'] = []
        save_data()

        menu_text = get_main_menu_text([])
        await query.edit_message_text(
            menu_text,
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(False, has_frequent_items(chat_id))
        )

    # CANCELAR LIMPEZA
    elif query.data == 'cancel_clear':
        items = shopping_lists[chat_id]['items']
        menu_text = get_main_menu_text(items)
        has_items = len(items) > 0

        await query.edit_message_text(
            menu_text,
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(has_items, has_frequent_items(chat_id))
        )

    # ===== EDITAR =====
    # Mostra a lista para escolher qual item editar
    elif query.data == 'action_edit':
        user_states[state_key] = STATE_NONE
        edit_target.pop(state_key, None)
        items = shopping_lists[chat_id]['items']

        if not items:
            await query.edit_message_text(
                "📋 <b>Lista vazia!</b>",
                parse_mode='HTML',
                reply_markup=get_main_menu_keyboard(False, has_frequent_items(chat_id))
            )
            return

        await query.edit_message_text(
            "✏️ <b>EDITAR</b>\n━━━━━━━━━━━━━━━\nEscolha o item:",
            parse_mode='HTML',
            reply_markup=get_edit_list_keyboard(items)
        )

    # Submenu de um item
    elif query.data.startswith('edit_'):
        index = int(query.data.split('_')[1])
        items = shopping_lists[chat_id]['items']

        if not (0 <= index < len(items)):
            await query.edit_message_text(
                "❌ <b>Item não encontrado.</b>",
                parse_mode='HTML',
                reply_markup=get_main_menu_keyboard(len(items) > 0, has_frequent_items(chat_id))
            )
            return

        emoji = CATEGORY_EMOJI.get(items[index].get('category', 'Outros'), '📦')
        await query.edit_message_text(
            f"✏️ <b>{item_label(items[index])}</b>\n{emoji} {items[index].get('category', 'Outros')}\n\nO que deseja fazer?",
            parse_mode='HTML',
            reply_markup=get_edit_item_keyboard(index)
        )

    # Renomear: pede o novo nome
    elif query.data.startswith('editname_'):
        index = int(query.data.split('_')[1])
        user_states[state_key] = STATE_EDIT_RENAME
        edit_target[state_key] = index
        await query.edit_message_text(
            f"✏️ <b>{user_name}</b>, digite o novo nome:",
            parse_mode='HTML',
            reply_markup=get_cancel_keyboard()
        )

    # Quantidade: pede o novo número
    elif query.data.startswith('editqty_'):
        index = int(query.data.split('_')[1])
        user_states[state_key] = STATE_EDIT_QTY
        edit_target[state_key] = index
        await query.edit_message_text(
            f"🔢 <b>{user_name}</b>, digite a nova quantidade (ex.: 3):",
            parse_mode='HTML',
            reply_markup=get_cancel_keyboard()
        )

    # Categoria: mostra os botões de categoria
    elif query.data.startswith('editcat_'):
        index = int(query.data.split('_')[1])
        items = shopping_lists[chat_id]['items']
        if not (0 <= index < len(items)):
            await query.edit_message_text(
                "❌ <b>Item não encontrado.</b>",
                parse_mode='HTML',
                reply_markup=get_main_menu_keyboard(len(items) > 0, has_frequent_items(chat_id))
            )
            return
        await query.edit_message_text(
            f"📂 <b>{item_label(items[index])}</b>\nEscolha a categoria:",
            parse_mode='HTML',
            reply_markup=get_edit_category_keyboard(index)
        )

    # Define a categoria escolhida
    elif query.data.startswith('setcat_'):
        _, idx_str, cat_str = query.data.split('_')
        index, cat_idx = int(idx_str), int(cat_str)
        items = shopping_lists[chat_id]['items']
        if 0 <= index < len(items) and 0 <= cat_idx < len(CATEGORY_ORDER):
            new_cat = CATEGORY_ORDER[cat_idx]
            items[index]['category'] = new_cat
            category_cache[_normalize(items[index]['name'])] = new_cat
            sort_items_by_category(items)
            save_data()
        menu_text = get_main_menu_text(items)
        await query.edit_message_text(
            menu_text,
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(len(items) > 0, has_frequent_items(chat_id))
        )

    # Remover item pelo editor
    elif query.data.startswith('editdel_'):
        index = int(query.data.split('_')[1])
        items = shopping_lists[chat_id]['items']
        if 0 <= index < len(items):
            items.pop(index)
            save_data()
        menu_text = get_main_menu_text(items)
        await query.edit_message_text(
            menu_text,
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(len(items) > 0, has_frequent_items(chat_id))
        )

    # ===== FREQUENTES =====
    elif query.data == 'action_frequent':
        user_states[state_key] = STATE_NONE
        if not has_frequent_items(chat_id):
            items = shopping_lists[chat_id]['items']
            await query.edit_message_text(
                "⭐ <b>Sem sugestões no momento.</b>\nAdicione itens e eu passo a sugerir os mais comprados.",
                parse_mode='HTML',
                reply_markup=get_main_menu_keyboard(len(items) > 0, False)
            )
            return
        await query.edit_message_text(
            "⭐ <b>FREQUENTES</b>\n━━━━━━━━━━━━━━━\nToque para adicionar à lista:",
            parse_mode='HTML',
            reply_markup=get_frequent_keyboard(chat_id)
        )

    # Adiciona um item frequente à lista
    elif query.data.startswith('addfreq_'):
        i = int(query.data.split('_')[1])
        keys = freq_suggestions.get(chat_id, [])
        items = shopping_lists[chat_id]['items']

        if 0 <= i < len(keys):
            entry = item_frequency.get(keys[i])
            if entry and not any(same_item(it['name'], entry['name']) for it in items):
                category = entry.get('category', 'Outros')
                items.append({'name': entry['name'], 'bought': False, 'category': category, 'quantity': 1})
                register_frequency(entry['name'], category)
                sort_items_by_category(items)
                save_data()

        # Re-renderiza as sugestões (ou volta ao menu se acabaram)
        if has_frequent_items(chat_id):
            await query.edit_message_text(
                "⭐ <b>FREQUENTES</b>\n━━━━━━━━━━━━━━━\nToque para adicionar à lista:",
                parse_mode='HTML',
                reply_markup=get_frequent_keyboard(chat_id)
            )
        else:
            menu_text = get_main_menu_text(items)
            await query.edit_message_text(
                menu_text,
                parse_mode='HTML',
                reply_markup=get_main_menu_keyboard(len(items) > 0, False)
            )


def main() -> None:
    """Inicia o bot"""
    bot_token = os.getenv('BOT_TOKEN')
    
    if not bot_token:
        logger.error("❌ ERRO: BOT_TOKEN não encontrado!")
        return
    
    logger.info(f"✅ Token: {bot_token[:20]}...")

    load_data()

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
