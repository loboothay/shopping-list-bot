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
import zlib
from datetime import datetime
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)
from telegram.error import BadRequest, TelegramError

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
STATE_STOCK_ADD = 6
STATE_STOCK_REMOVE = 7

# Armazenamento (persistido em JSON: shopping_lists, category_cache, item_frequency, stock)
shopping_lists = {}
user_states = {}
messages_to_delete = {}
menu_messages = {}

# Cache de categorias já resolvidas (nome_normalizado -> categoria), evita reclassificar
category_cache = {}

# Frequência de itens: nome_normalizado -> {'count', 'name', 'category'}
item_frequency = {}

# Estoque: chat_id -> [{'id', 'name', 'package', 'category', 'quantity', 'min', 'ideal'}]
# A quantidade é sempre em embalagens fechadas; 'package' descreve a embalagem ("5 kg")
stock = {}
stock_panels = {}  # chat_id -> message_id do painel do estoque, a mensagem fixada no grupo
stock_seeded = set()  # chats que já passaram pela carga inicial: nunca recarregar por cima
STOCK_MAX_QTY = 999
STOCK_PAGE_SIZE = 30

# Estado de UI transitório (não persistido)
edit_target = {}        # state_key -> índice do item em edição
freq_suggestions = {}   # chat_id -> lista de nomes_normalizados sugeridos (mapeia o clique)
market_hide_bought = {} # chat_id -> bool: no modo mercado, ocultar itens já comprados

# Persistência em arquivo (Volume do Railway montado em /data)
DATA_DIR = os.getenv('DATA_DIR', '/data')
DATA_FILE = os.path.join(DATA_DIR, 'shopping_data.json')

# Inventário inicial da casa, no mesmo formato do fluxo de Cadastrar
SEED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'estoque_inicial.txt')

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


def get_stock(chat_id: int) -> list:
    return stock.setdefault(chat_id, [])


def find_stock_items(chat_id: int, text: str) -> list:
    """Itens que casam com o texto: nome exato (ou plural); se não houver, trecho do nome."""
    items = get_stock(chat_id)
    exact = [it for it in items if same_item(it['name'], text)]
    if exact:
        return exact
    norm = _normalize(text)
    return [it for it in items if norm in _normalize(it['name'])]


def is_low(stock_item: dict) -> bool:
    """Abaixo do mínimo? Estar exatamente no mínimo ainda é ok."""
    return stock_item['quantity'] < stock_item['min']


def stock_missing(stock_item: dict) -> int:
    """Quanto comprar para voltar ao ideal."""
    return max(stock_item['ideal'] - stock_item['quantity'], 0)


_PACKAGE_SIZE = re.compile(r'(\d+(?:[.,]\d+)?)\s*(kg|g|l|ml)\b', re.IGNORECASE)


def stock_total(stock_item: dict) -> str | None:
    """Total em kg/L quando a embalagem informa o tamanho ('3 x 5 kg' → '15 kg')."""
    m = _PACKAGE_SIZE.search(stock_item.get('package', ''))
    if not m:
        return None
    size = float(m.group(1).replace(',', '.')) * stock_item['quantity']
    unit = m.group(2).lower()
    if unit in ('g', 'ml') and size >= 1000:
        size, unit = size / 1000, 'kg' if unit == 'g' else 'l'
    number = f"{size:.2f}".rstrip('0').rstrip('.').replace('.', ',')
    return f"{number} {'L' if unit == 'l' else unit}"


def stock_amount(stock_item: dict) -> str:
    """Quantidade para exibir: '3' ou, com tamanho conhecido, '3 (15 kg)'."""
    total = stock_total(stock_item)
    return f"{stock_item['quantity']} ({total})" if total else str(stock_item['quantity'])


def stock_label(stock_item: dict) -> str:
    return f"{stock_item['name']} · {stock_amount(stock_item)} · mín {stock_item['min']}"


def stock_list_name(stock_item: dict) -> str:
    """Nome na lista de compras: quem vai ao mercado precisa saber a embalagem."""
    package = stock_item.get('package')
    return f"{stock_item['name']} ({package})" if package else stock_item['name']


def is_stock_entry(entry: dict, stock_item: dict) -> bool:
    """O item da lista corresponde ao item do estoque, pelo nome com ou sem embalagem?"""
    return (same_item(entry['name'], stock_item['name'])
            or same_item(entry['name'], stock_list_name(stock_item)))


def sync_stock_item(chat_id: int, stock_item: dict) -> None:
    """Reflete um item do estoque na lista de compras.

    Abaixo do mínimo: entra na lista com a quantidade que falta para o ideal. Se voltou
    ao mínimo (ex.: baixa desfeita), sai da lista. O vínculo é o 'stock_id' do item da
    lista, que sobrevive a renomear. Item manual de mesmo nome é adotado sem reduzir a
    quantidade digitada. Item já no carrinho fica como está: é reconciliado ao finalizar.
    """
    init_list(chat_id)
    items = shopping_lists[chat_id]['items']
    entry = next((it for it in items if it.get('stock_id') == stock_item['id']), None)
    if entry is None:
        entry = next((it for it in items if is_stock_entry(it, stock_item)), None)

    if entry is not None and entry.get('bought', False):
        return

    if is_low(stock_item):
        missing = min(stock_missing(stock_item), 99)
        if entry is None:
            items.append({
                'name': stock_list_name(stock_item),
                'bought': False,
                'category': stock_item['category'],
                'quantity': missing,
                'stock_id': stock_item['id'],
            })
        elif 'stock_id' in entry:
            entry['quantity'] = missing
        else:
            entry['quantity'] = max(entry.get('quantity', 1), missing)
            entry['stock_id'] = stock_item['id']
        sort_items_by_category(items)
    elif entry is not None and 'stock_id' in entry:
        items.remove(entry)


def sync_all_stock(chat_id: int) -> None:
    for stock_item in get_stock(chat_id):
        sync_stock_item(chat_id, stock_item)


def change_stock(chat_id: int, stock_item: dict, delta: int) -> None:
    """Soma delta à quantidade (limitada a 0–STOCK_MAX_QTY) e atualiza a lista de compras."""
    stock_item['quantity'] = max(0, min(stock_item['quantity'] + delta, STOCK_MAX_QTY))
    sync_stock_item(chat_id, stock_item)
    save_data()


def restock_bought(chat_id: int) -> list:
    """Dá entrada no estoque do que foi comprado e tira esses itens da lista.

    Por tirar da lista, não soma duas vezes. Quem não está no estoque fica como está.
    Retorna os textos de entrada ('+3 Arroz') para exibir ao usuário.
    """
    init_list(chat_id)
    items = shopping_lists[chat_id]['items']
    stock_items = get_stock(chat_id)
    received = []
    for entry in [it for it in items if it.get('bought', False)]:
        stock_item = next((s for s in stock_items if s['id'] == entry.get('stock_id')), None)
        if stock_item is None:
            stock_item = next((s for s in stock_items if is_stock_entry(entry, s)), None)
        if stock_item is None:
            continue
        qty = entry.get('quantity', 1)
        stock_item['quantity'] = min(stock_item['quantity'] + qty, STOCK_MAX_QTY)
        items.remove(entry)
        received.append(f"+{qty} {stock_item['name']}")
    sync_all_stock(chat_id)
    return received


def get_received_text(received: list) -> str:
    return f"📦 Entrada no estoque: {escape(', '.join(received))}\n" if received else ""


# "arroz (5 kg) 3/2/4" = atual/mínimo/ideal; embalagem, mínimo e ideal são opcionais
_STOCK_ENTRY = re.compile(r'^(.+?)\s*(?:\(([^)]*)\))?\s+(\d{1,3})(?:/(\d{1,3}))?(?:/(\d{1,3}))?$')


def parse_stock_entry(text: str) -> tuple | None:
    """Extrai (nome, embalagem, atual, mínimo, ideal). O que faltar vem None."""
    m = _STOCK_ENTRY.match(text.strip())
    if not m:
        return None
    name, package, qty, min_qty, ideal = m.groups()
    return (
        name.strip(),
        package.strip() if package else None,
        int(qty),
        int(min_qty) if min_qty is not None else None,
        int(ideal) if ideal is not None else None,
    )


def split_stock_lines(text: str) -> list:
    """Separa por linha ou vírgula, sem cortar a vírgula da embalagem ('(2,4 kg)')."""
    return [p.strip() for p in re.split(r',(?![^(]*\))|\n', text) if p.strip()]


def category_from_line(line: str) -> str | None:
    """A linha é só o nome de uma seção? Vale para as linhas seguintes do cadastro."""
    norm = _normalize(line).rstrip(':')
    return next((cat for cat in CATEGORY_ORDER if _normalize(cat) == norm), None)


def parse_stock_text(text: str) -> tuple:
    """Lê um texto de cadastro. Retorna (entradas, linhas ignoradas).

    Cada entrada é (nome, embalagem, atual, mínimo, ideal, seção escolhida ou None).
    """
    entries = []
    ignored = []
    section = None
    for line in split_stock_lines(text):
        header = category_from_line(line)
        if header:
            section = header
            continue
        entry = parse_stock_entry(line)
        if entry is None or len(entry[0]) < 2:
            ignored.append(line)
        else:
            entries.append((*entry, section))
    return entries, ignored


def upsert_stock_item(chat_id: int, name: str, package: str | None, category: str, qty: int,
                      min_qty: int | None, ideal: int | None) -> dict:
    """Cadastra o item ou, se já existe, atualiza só o que foi informado.

    Item novo sem mínimo usa 1; sem ideal usa 1,5 vez o mínimo, arredondado para cima
    (mínimo de 2 meses, repor até 3). Ideal nunca fica abaixo do mínimo, senão o item
    entraria na lista com quantidade zero.
    """
    items = get_stock(chat_id)
    stock_item = next((it for it in items if same_item(it['name'], name)), None)
    if stock_item is None:
        min_value = 1 if min_qty is None else min_qty
        stock_item = {
            'id': max((it['id'] for it in items), default=0) + 1,
            'name': name,
            'package': package or '',
            'category': category,
            'quantity': qty,
            'min': min_value,
            'ideal': (min_value * 3 + 1) // 2 if ideal is None else ideal,
        }
        items.append(stock_item)
    else:
        stock_item['quantity'] = qty
        if package is not None:
            stock_item['package'] = package
        if min_qty is not None:
            stock_item['min'] = min_qty
        if ideal is not None:
            stock_item['ideal'] = ideal
    stock_item['ideal'] = max(stock_item['ideal'], stock_item['min'])
    sync_stock_item(chat_id, stock_item)
    return stock_item


def remove_stock_item(chat_id: int, stock_item: dict) -> None:
    """Tira do estoque. Na lista o item continua, mas vira um item manual comum."""
    init_list(chat_id)
    for entry in shopping_lists[chat_id]['items']:
        if entry.get('stock_id') == stock_item['id']:
            entry.pop('stock_id')
    get_stock(chat_id).remove(stock_item)


def load_seed(chat_id: int) -> bool:
    """Carrega o inventário inicial, uma única vez e só em chat com estoque vazio."""
    if chat_id in stock_seeded:
        return False
    stock_seeded.add(chat_id)
    save_data()
    if get_stock(chat_id) or not os.path.exists(SEED_FILE):
        return False

    with open(SEED_FILE, 'r', encoding='utf-8') as f:
        entries, _ = parse_stock_text(f.read())
    for name, package, qty, min_qty, ideal, section in entries:
        upsert_stock_item(chat_id, name, package, section or 'Outros', qty, min_qty, ideal)
    save_data()
    logger.info(f"✅ Estoque inicial carregado no chat {chat_id}: {len(entries)} item(ns).")
    return True


def move_stock_by_text(chat_id: int, text: str, sign: int) -> tuple:
    """Aplica '2 arroz, feijão' ao estoque: sign -1 dá baixa, +1 dá entrada.

    Só mexe quando o texto aponta para um único item. Retorna (linhas de resposta em
    HTML, se algum item foi movimentado).
    """
    linhas = []
    moved = False
    for part in [p.strip() for p in text.split(',') if p.strip()]:
        qty, name = parse_quantity(part)
        matches = find_stock_items(chat_id, name) if len(name) >= 2 else []

        if not matches:
            linhas.append(f"❓ {escape(name)}: não está no estoque")
        elif len(matches) > 1:
            opcoes = ', '.join(escape(it['name']) for it in matches[:6])
            linhas.append(f"❓ {escape(name)}: qual? {opcoes}")
        else:
            stock_item = matches[0]
            before = stock_item['quantity']
            change_stock(chat_id, stock_item, sign * qty)
            moved = True
            linha = f"{'➖' if sign < 0 else '➕'} {escape(stock_item['name'])}: {before} → {escape(stock_amount(stock_item))}"
            if is_low(stock_item):
                linha += f" | 🛒 comprar {stock_missing(stock_item)}"
            linhas.append(linha)
    return linhas, moved


def save_data() -> None:
    """Salva lista, cache de categorias, frequências e estoque em JSON (Volume do Railway)."""
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
            'stock': {str(chat_id): items for chat_id, items in stock.items()},
            'stock_panels': {str(chat_id): msg_id for chat_id, msg_id in stock_panels.items()},
            'stock_seeded': sorted(stock_seeded),
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
        for chat_id_str, items in payload.get('stock', {}).items():
            stock[int(chat_id_str)] = items
        for chat_id_str, msg_id in payload.get('stock_panels', {}).items():
            stock_panels[int(chat_id_str)] = msg_id
        stock_seeded.update(payload.get('stock_seeded', []))
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
            name = escape(item_label(item))
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


def item_tag(item: dict) -> str:
    """Identifica o item no botão do modo mercado.

    Baixas no estoque podem mudar a lista enquanto alguém está no mercado. Com o índice
    sozinho, um teclado desatualizado marcaria o item errado.
    """
    return f"{zlib.crc32(_normalize(item['name']).encode()):x}"


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
        InlineKeyboardButton("📦 Estoque", callback_data='stock_open')
    ])

    keyboard.append([
        InlineKeyboardButton("🗑️ Limpar Tudo", callback_data='action_clear')
    ])

    return InlineKeyboardMarkup(keyboard)


def get_stock_menu_text(chat_id: int) -> str:
    """Texto da tela principal do estoque (HTML)."""
    items = get_stock(chat_id)
    header = "📦 <b>ESTOQUE</b>\n━━━━━━━━━━━━━━━\n"
    if not items:
        return header + "📋 Nada cadastrado ainda.\n\nToque em ➕ Cadastrar para começar."

    low = sum(1 for item in items if is_low(item))
    status = f"📊 <b>{len(items)} item(ns)</b>"
    if low:
        status += f" | 🔴 {low} abaixo do mínimo"
    return (
        header + f"{status}\n\nEscolha a seção para dar baixa, ou mande no grupo:\n"
        "<code>-2 arroz</code> para tirar, <code>+1 arroz</code> para devolver."
    )


def get_stock_menu_keyboard(chat_id: int):
    """Teclado do estoque: uma entrada por categoria que tem itens."""
    items = get_stock(chat_id)
    keyboard = []
    row = []
    for cat_idx, category in enumerate(CATEGORY_ORDER):
        group = [item for item in items if item['category'] == category]
        if not group:
            continue
        low = sum(1 for item in group if is_low(item))
        label = f"{CATEGORY_EMOJI.get(category, '📦')} {category} ({len(group)})"
        if low:
            label += f" 🔴{low}"
        row.append(InlineKeyboardButton(label, callback_data=f'stock_cat_{cat_idx}_0'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("➕ Cadastrar / Atualizar", callback_data='stock_add')])
    if items:
        keyboard.append([InlineKeyboardButton("🗑️ Tirar do estoque", callback_data='stock_del')])
    return InlineKeyboardMarkup(keyboard)


def get_stock_category_text(cat_idx: int) -> str:
    """Cabeçalho da tela de baixa de uma categoria."""
    category = CATEGORY_ORDER[cat_idx]
    return (
        f"{CATEGORY_EMOJI.get(category, '📦')} <b>{category}</b>\n━━━━━━━━━━━━━━━\n"
        "Toque no item para dar baixa de 1 embalagem.\n🔴 = abaixo do mínimo"
    )


def get_stock_category_keyboard(chat_id: int, cat_idx: int, page: int = 0, undo_item: dict = None):
    """Um botão por item (toque = baixa de 1), paginado para respeitar o limite do Telegram.

    Os botões usam o 'id' do item, não o índice: um teclado desatualizado continua
    apontando para o item certo. undo_item mostra o botão de devolver o que acabou de
    ser mexido.
    """
    category = CATEGORY_ORDER[cat_idx]
    group = sorted(
        (item for item in get_stock(chat_id) if item['category'] == category),
        key=lambda item: _normalize(item['name']),
    )
    last_page = max(len(group) - 1, 0) // STOCK_PAGE_SIZE
    page = max(0, min(page, last_page))
    start = page * STOCK_PAGE_SIZE

    keyboard = []
    if undo_item is not None:
        keyboard.append([InlineKeyboardButton(
            f"↩️ Devolver 1 {undo_item['name']}",
            callback_data=f"stock_up_{undo_item['id']}_{cat_idx}_{page}",
        )])

    for item in group[start:start + STOCK_PAGE_SIZE]:
        mark = '🔴' if is_low(item) else '➖'
        keyboard.append([InlineKeyboardButton(
            f"{mark} {stock_label(item)}",
            callback_data=f"stock_dn_{item['id']}_{cat_idx}_{page}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f'stock_cat_{cat_idx}_{page - 1}'))
    if page < last_page:
        nav.append(InlineKeyboardButton("▶️", callback_data=f'stock_cat_{cat_idx}_{page + 1}'))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data='stock_menu')])
    return InlineKeyboardMarkup(keyboard)


def get_stock_names_text(chat_id: int, limit: int = 3500) -> str:
    """Nomes do estoque em HTML, cortados em um nome inteiro para caber na mensagem."""
    text = ''
    for name in sorted(escape(item['name']) for item in get_stock(chat_id)):
        if len(text) + len(name) > limit:
            return text + ', …'
        text += f', {name}' if text else name
    return text


def get_stock_back_keyboard():
    """Teclado das telas que esperam texto do usuário."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data='stock_menu')]])


def get_cancel_keyboard():
    """Teclado de cancelar"""
    keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data='action_cancel')]]
    return InlineKeyboardMarkup(keyboard)


def get_market_header_text(items: list) -> str:
    """Cabeçalho do modo mercado, com o total pendente/no carrinho atualizado."""
    pending = sum(1 for item in items if not item.get('bought', False))
    bought = sum(1 for item in items if item.get('bought', False))
    total = len(items)

    status = f"📦 <b>{pending} pendente(s)</b>"
    if bought:
        status += f" | ✅ {bought}/{total} no carrinho"

    return (
        "🛒 <b>MODO MERCADO</b>\n━━━━━━━━━━━━━━━\n"
        f"Toque nos itens para marcar:\n\n{status}"
    )


def get_market_mode_keyboard(items: list, hide_bought: bool = False):
    """Teclado do modo mercado com checkboxes, agrupado por categoria.

    Mantém a mesma organização por seção da lista (get_list_text): antes de cada
    bloco entra um cabeçalho não-clicável (callback 'noop') com o total de itens
    pendentes na seção. O índice usado no toggle_<i> é o índice real do item na
    lista, preservando a marcação correta mesmo com cabeçalhos no meio.

    hide_bought=True esconde os itens já comprados (e as seções que ficarem vazias),
    para "limpar" a tela conforme as compras avançam.
    """
    keyboard = []

    for category in CATEGORY_ORDER:
        group = [(i, item) for i, item in enumerate(items)
                 if item.get('category', 'Outros') == category]
        if not group:
            continue

        visible = group if not hide_bought else [
            (i, it) for i, it in group if not it.get('bought', False)
        ]
        if not visible:
            continue

        pending_in_group = sum(1 for _, it in group if not it.get('bought', False))
        emoji = CATEGORY_EMOJI.get(category, '📦')
        keyboard.append([
            InlineKeyboardButton(
                f"➖ {emoji} {category} ({pending_in_group}) ➖",
                callback_data='noop',
            )
        ])

        for i, item in visible:
            name = item_label(item)
            bought = item.get('bought', False)

            if bought:
                btn_text = f"✅ {name}"
            else:
                btn_text = f"⬜ {name}"

            keyboard.append([
                InlineKeyboardButton(btn_text, callback_data=f'toggle_{i}_{item_tag(item)}')
            ])

    has_bought = any(item.get('bought', False) for item in items)
    if has_bought:
        if hide_bought:
            keyboard.append([
                InlineKeyboardButton("👁 Mostrar comprados", callback_data='market_toggle_hide')
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("🙈 Ocultar comprados", callback_data='market_toggle_hide')
            ])

    keyboard.append([
        InlineKeyboardButton("✔️ Finalizar", callback_data='market_finish'),
        InlineKeyboardButton("❌ Cancelar", callback_data='market_cancel')
    ])

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


async def edit_stock_panel(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    """Atualiza o painel do estoque. Retorna False se ele não existe mais."""
    if chat_id not in stock_panels:
        return False
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=stock_panels[chat_id],
            text=get_stock_menu_text(chat_id),
            parse_mode='HTML',
            reply_markup=get_stock_menu_keyboard(chat_id)
        )
    except BadRequest as e:
        return 'not modified' in str(e).lower()
    return True


async def send_stock_panel(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Publica o painel no fim do chat e fixa, para ficar a um toque de distância.

    É uma mensagem separada do menu da lista: mexer no estoque não troca a tela de quem
    está no modo mercado. Sem permissão para fixar, o painel funciona do mesmo jeito.
    """
    if chat_id in stock_panels:
        await delete_message_safe(context, chat_id, stock_panels[chat_id])

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=get_stock_menu_text(chat_id),
        parse_mode='HTML',
        reply_markup=get_stock_menu_keyboard(chat_id)
    )
    stock_panels[chat_id] = msg.message_id
    save_data()

    try:
        await context.bot.pin_chat_message(
            chat_id=chat_id, message_id=msg.message_id, disable_notification=True
        )
    except TelegramError as e:
        logger.warning(f"⚠️ Não consegui fixar o painel do estoque: {e}")


async def refresh_list_menu(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Atualiza a lista depois de um movimento. Não toca na tela do modo mercado."""
    if chat_id not in menu_messages or chat_id in market_hide_bought:
        return
    items = shopping_lists[chat_id]['items']
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=menu_messages[chat_id],
            text=get_main_menu_text(items),
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(len(items) > 0, has_frequent_items(chat_id))
        )
    except BadRequest:
        pass


async def refresh_views(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    await edit_stock_panel(context, chat_id)
    await refresh_list_menu(context, chat_id)


async def delete_own_pin_notice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Apaga o aviso 'fixou uma mensagem' que o próprio bot gera ao fixar o painel."""
    if update.effective_user and update.effective_user.id == context.bot.id:
        await delete_message_safe(context, update.effective_chat.id, update.message.message_id)


async def seed_groups(application: Application) -> None:
    """Na subida, carrega o inventário nos grupos que já usam o bot e publica o painel.

    Um grupo de onde o bot saiu não pode impedir o bot de iniciar.
    """
    for chat_id in [chat_id for chat_id in shopping_lists if chat_id < 0]:
        if load_seed(chat_id):
            try:
                await send_stock_panel(application, chat_id)
            except TelegramError as e:
                logger.warning(f"⚠️ Não consegui publicar o painel no chat {chat_id}: {e}")


async def on_startup(application: Application) -> None:
    await set_bot_commands(application)
    await seed_groups(application)


async def set_bot_commands(application: Application) -> None:
    """Define os comandos do bot"""
    commands = [
        BotCommand("start", "Menu principal"),
        BotCommand("add", "Adicionar item"),
        BotCommand("list", "Ver lista"),
        BotCommand("remove", "Remover item"),
        BotCommand("market", "Modo mercado"),
        BotCommand("estoque", "Abrir o painel do estoque"),
        BotCommand("baixa", "Dar baixa (ex.: /baixa 2 arroz)"),
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
    market_hide_bought[chat_id] = False

    if chat_id in menu_messages:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=menu_messages[chat_id],
                text=get_market_header_text(items),
                parse_mode='HTML',
                reply_markup=get_market_mode_keyboard(items, market_hide_bought[chat_id])
            )
            return
        except BadRequest:
            pass

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=get_market_header_text(items),
        parse_mode='HTML',
        reply_markup=get_market_mode_keyboard(items, market_hide_bought[chat_id])
    )
    menu_messages[chat_id] = msg.message_id


async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /estoque: republica e fixa o painel do estoque"""
    chat_id = update.effective_chat.id
    user_states[get_user_state_key(chat_id, update.effective_user.id)] = STATE_NONE

    await delete_message_safe(context, chat_id, update.message.message_id)
    await send_stock_panel(context, chat_id)


async def seed_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /carregarestoque: carga manual, para um grupo que a subida não encontrou."""
    chat_id = update.effective_chat.id
    await delete_message_safe(context, chat_id, update.message.message_id)

    if load_seed(chat_id):
        await send_stock_panel(context, chat_id)
        await refresh_list_menu(context, chat_id)
        return

    msg = await context.bot.send_message(chat_id=chat_id, text="ℹ️ <b>O estoque deste chat já foi carregado.</b>", parse_mode='HTML')
    await asyncio.sleep(3)
    await delete_message_safe(context, chat_id, msg.message_id)


async def stock_out_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /baixa: '/baixa 2 arroz, feijão'. Sem argumentos, abre o estoque.

    Alternativa à mensagem '-2 arroz', e funciona mesmo sem o bot ler as mensagens do grupo.
    """
    if not context.args:
        await stock_command(update, context)
        return

    chat_id = update.effective_chat.id
    await delete_message_safe(context, chat_id, update.message.message_id)

    linhas, moved = move_stock_by_text(chat_id, ' '.join(context.args), -1)
    await show_stock_moves(context, chat_id, linhas, moved)


async def show_stock_moves(context: ContextTypes.DEFAULT_TYPE, chat_id: int, linhas: list, moved: bool) -> None:
    """Mostra o resultado de um movimento por texto e atualiza as telas."""
    if moved:
        await refresh_views(context, chat_id)
    msg = await context.bot.send_message(chat_id=chat_id, text="\n".join(linhas) or "⚠️ <b>Nada para fazer.</b>", parse_mode='HTML')
    await asyncio.sleep(3)
    await delete_message_safe(context, chat_id, msg.message_id)


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


# "-2 arroz" tira, "+1 arroz" devolve. O iPhone pode trocar o hífen por travessão.
_STOCK_MOVE = re.compile(r'^([-–—−+])\s*(\S.*)$', re.DOTALL)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa mensagens de texto"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    text = update.message.text.strip()
    user_name = update.effective_user.first_name
    
    state_key = get_user_state_key(chat_id, user_id)
    current_state = user_states.get(state_key, STATE_NONE)

    # Nos estados sem digitação, o texto é conversa do grupo, exceto "-2 arroz" e "+1 arroz".
    # Quem saiu do modo mercado sem finalizar continua em STATE_MARKET_MODE.
    if current_state in (STATE_NONE, STATE_MARKET_MODE):
        m = _STOCK_MOVE.match(text)
        if m:
            sign = 1 if m.group(1) == '+' else -1
            linhas, moved = move_stock_by_text(chat_id, m.group(2), sign)
            # Sem nenhum item reconhecido, pode ser conversa: a mensagem da pessoa fica
            if moved:
                await delete_message_safe(context, chat_id, update.message.message_id)
            await show_stock_moves(context, chat_id, linhas, moved)
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

    # ESTOQUE: cadastrar/atualizar ("arroz 3/2/5"), separados por vírgula ou por linha
    elif current_state == STATE_STOCK_ADD:
        user_states[state_key] = STATE_NONE

        entries, ignored = parse_stock_text(text)

        organizing = await context.bot.send_message(chat_id=chat_id, text="🧠 <b>Organizando...</b>", parse_mode='HTML')

        new_names = [
            entry[0] for entry in entries
            if entry[5] is None and not any(same_item(it['name'], entry[0]) for it in get_stock(chat_id))
        ]
        categories = await categorize_items(new_names) if new_names else {}

        saved = []
        for name, package, qty, min_qty, ideal, entry_section in entries:
            category = entry_section or categories.get(name, 'Outros')
            saved.append(upsert_stock_item(chat_id, name, package, category, qty, min_qty, ideal))
            if entry_section:
                saved[-1]['category'] = entry_section
        save_data()

        await delete_message_safe(context, chat_id, organizing.message_id)

        if len(saved) <= 15:
            linhas = [
                f"✅ {escape(it['name'])}: {it['quantity']} (mín {it['min']}, ideal {it['ideal']})"
                for it in saved
            ]
        else:
            linhas = [f"✅ <b>{len(saved)} itens salvos</b>"]
        to_buy = sum(1 for it in saved if is_low(it))
        if to_buy:
            linhas.append(f"🛒 {to_buy} foi(ram) para a lista de compras")
        if ignored:
            linhas.append(f"⚠️ Ignorado(s), faltou a quantidade: {escape(', '.join(ignored[:10]))}")

        msg = await context.bot.send_message(chat_id=chat_id, text="\n".join(linhas) or "⚠️ <b>Nada para salvar.</b>", parse_mode='HTML')
        await asyncio.sleep(2.5)
        await delete_message_safe(context, chat_id, msg.message_id)
        await refresh_views(context, chat_id)

    # ESTOQUE: tirar itens (por nome, separados por vírgula)
    elif current_state == STATE_STOCK_REMOVE:
        user_states[state_key] = STATE_NONE

        removed, not_found = [], []
        for part in [p.strip() for p in text.split(',') if p.strip()]:
            matches = [it for it in get_stock(chat_id) if same_item(it['name'], part)]
            if matches:
                remove_stock_item(chat_id, matches[0])
                removed.append(matches[0]['name'])
            else:
                not_found.append(part)
        save_data()

        linhas = []
        if removed:
            linhas.append(f"✅ Fora do estoque: {escape(', '.join(removed))}")
        if not_found:
            linhas.append(f"❓ Não encontrado(s): {escape(', '.join(not_found))}")
        msg = await context.bot.send_message(chat_id=chat_id, text="\n".join(linhas) or "⚠️ <b>Nada para tirar.</b>", parse_mode='HTML')
        await asyncio.sleep(2)
        await delete_message_safe(context, chat_id, msg.message_id)
        await refresh_views(context, chat_id)


async def handle_stock_button(query, context: ContextTypes.DEFAULT_TYPE, state_key: str) -> None:
    """Processa os botões 'stock_*'. Responde o clique aqui para poder mostrar o aviso."""
    chat_id = query.message.chat_id
    parts = query.data.split('_')
    action = parts[1]

    # Botão do menu da lista: publica o painel
    if action == 'open':
        await query.answer()
        await send_stock_panel(context, chat_id)

    # Tela principal do estoque
    elif action == 'menu':
        user_states[state_key] = STATE_NONE
        await query.answer()
        try:
            await query.edit_message_text(
                get_stock_menu_text(chat_id),
                parse_mode='HTML',
                reply_markup=get_stock_menu_keyboard(chat_id)
            )
        except BadRequest:
            pass

    # Cadastrar / atualizar: pede o texto
    elif action == 'add':
        user_states[state_key] = STATE_STOCK_ADD
        await query.answer()
        await query.edit_message_text(
            "➕ <b>CADASTRAR / ATUALIZAR</b>\n━━━━━━━━━━━━━━━\n"
            "Digite <b>nome (embalagem) tem/mínimo/repor até</b>, um por linha:\n\n"
            "<code>Arroz (5 kg) 4/3/4</code>\n"
            "<code>Feijão (1 kg) 3/1/2</code>\n\n"
            "• As quantidades são em embalagens fechadas.\n"
            "• Abaixo do mínimo, vai para a lista com o que falta para repor.\n"
            "• Sem \"repor até\", uso 1,5 vez o mínimo. Sem mínimo, uso 1.\n"
            "• Uma linha com o nome da seção (<code>Limpeza</code>) vale para as seguintes.\n"
            "• Item já cadastrado: <code>arroz 4</code> só corrige a quantidade.",
            parse_mode='HTML',
            reply_markup=get_stock_back_keyboard()
        )

    # Tirar do estoque: pede os nomes
    elif action == 'del':
        user_states[state_key] = STATE_STOCK_REMOVE
        await query.answer()
        await query.edit_message_text(
            f"🗑️ <b>TIRAR DO ESTOQUE</b>\n━━━━━━━━━━━━━━━\n{get_stock_names_text(chat_id)}\n\n"
            "Digite o(s) nome(s), separando por vírgula:",
            parse_mode='HTML',
            reply_markup=get_stock_back_keyboard()
        )

    # Abrir uma categoria
    elif action == 'cat':
        cat_idx, page = int(parts[2]), int(parts[3])
        user_states[state_key] = STATE_NONE
        await query.answer()
        try:
            await query.edit_message_text(
                get_stock_category_text(cat_idx),
                parse_mode='HTML',
                reply_markup=get_stock_category_keyboard(chat_id, cat_idx, page)
            )
        except BadRequest:
            pass

    # Baixa ou devolução de 1 unidade
    elif action in ('dn', 'up'):
        item_id, cat_idx, page = int(parts[2]), int(parts[3]), int(parts[4])
        stock_item = next((it for it in get_stock(chat_id) if it['id'] == item_id), None)

        if stock_item is None:
            await query.answer("Esse item não está mais no estoque.")
            try:
                await query.edit_message_text(
                    get_stock_category_text(cat_idx),
                    parse_mode='HTML',
                    reply_markup=get_stock_category_keyboard(chat_id, cat_idx, page)
                )
            except BadRequest:
                pass
            return

        if action == 'dn' and stock_item['quantity'] == 0:
            await query.answer(f"{stock_item['name']} já está zerado.")
            return

        before = stock_item['quantity']
        change_stock(chat_id, stock_item, -1 if action == 'dn' else 1)

        aviso = f"{stock_item['name']}: {before} → {stock_amount(stock_item)}"
        if is_low(stock_item):
            aviso += f" | 🛒 comprar {stock_missing(stock_item)}"
        await query.answer(aviso)

        try:
            await query.edit_message_text(
                get_stock_category_text(cat_idx),
                parse_mode='HTML',
                reply_markup=get_stock_category_keyboard(chat_id, cat_idx, page, undo_item=stock_item)
            )
        except BadRequest:
            pass

        # O painel é a mensagem tocada; só a lista precisa ser atualizada
        await refresh_list_menu(context, chat_id)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa cliques nos botões"""
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    user_name = query.from_user.first_name

    if query.data.startswith('stock_'):
        await handle_stock_button(query, context, get_user_state_key(chat_id, user_id))
        return

    await query.answer()

    state_key = get_user_state_key(chat_id, user_id)
    init_list(chat_id)

    # NOOP (cabeçalho de categoria no modo mercado — não faz nada)
    if query.data == 'noop':
        return

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
        market_hide_bought[chat_id] = False

        await query.edit_message_text(
            get_market_header_text(items),
            parse_mode='HTML',
            reply_markup=get_market_mode_keyboard(items, market_hide_bought.get(chat_id, False))
        )

    # OCULTAR/MOSTRAR COMPRADOS (modo mercado)
    elif query.data == 'market_toggle_hide':
        items = shopping_lists[chat_id]['items']
        market_hide_bought[chat_id] = not market_hide_bought.get(chat_id, False)

        try:
            await query.edit_message_text(
                get_market_header_text(items),
                parse_mode='HTML',
                reply_markup=get_market_mode_keyboard(items, market_hide_bought[chat_id])
            )
        except BadRequest:
            pass

    # TOGGLE ITEM
    elif query.data.startswith('toggle_'):
        parts = query.data.split('_')
        index = int(parts[1])
        items = shopping_lists[chat_id]['items']

        # A lista pode ter mudado desde que o teclado foi desenhado: o tag acha o item certo
        if len(parts) > 2:
            index = next((i for i, it in enumerate(items) if item_tag(it) == parts[2]), -1)

        if 0 <= index < len(items):
            items[index]['bought'] = not items[index].get('bought', False)
            save_data()

        try:
            await query.edit_message_text(
                get_market_header_text(items),
                parse_mode='HTML',
                reply_markup=get_market_mode_keyboard(items, market_hide_bought.get(chat_id, False))
            )
        except BadRequest:
            pass

    # FINALIZAR MODO MERCADO
    elif query.data == 'market_finish':
        user_states[state_key] = STATE_NONE
        market_hide_bought.pop(chat_id, None)
        items = shopping_lists[chat_id]['items']

        bought_count = sum(1 for item in items if item.get('bought', False))
        received = restock_bought(chat_id)
        save_data()

        menu_text = get_main_menu_text(items)
        has_items = len(items) > 0

        await query.edit_message_text(
            f"✅ <b>Compras finalizadas!</b>\n{bought_count} item(ns) marcado(s)\n{get_received_text(received)}\n{menu_text}",
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(has_items, has_frequent_items(chat_id))
        )
        await edit_stock_panel(context, chat_id)

    # CANCELAR MODO MERCADO
    elif query.data == 'market_cancel':
        user_states[state_key] = STATE_NONE
        market_hide_bought.pop(chat_id, None)

        items = shopping_lists[chat_id]['items']
        for item in items:
            item['bought'] = False
        sync_all_stock(chat_id)
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
        received = restock_bought(chat_id)
        shopping_lists[chat_id]['items'] = [item for item in items if not item.get('bought', False)]
        save_data()
        market_hide_bought[chat_id] = False

        items = shopping_lists[chat_id]['items']
        received_text = get_received_text(received)

        if items:
            await query.edit_message_text(
                f"🧹 <b>{removed_count} item(ns) removido(s)!</b>\n{received_text}\n{get_market_header_text(items)}",
                parse_mode='HTML',
                reply_markup=get_market_mode_keyboard(items, market_hide_bought[chat_id])
            )
            await edit_stock_panel(context, chat_id)
        else:
            user_states[state_key] = STATE_NONE
            market_hide_bought.pop(chat_id, None)
            menu_text = get_main_menu_text([])
            await query.edit_message_text(
                f"🧹 <b>{removed_count} item(ns) removido(s)!</b>\n{received_text}\n{menu_text}",
                parse_mode='HTML',
                reply_markup=get_main_menu_keyboard(False, has_frequent_items(chat_id))
            )
            await edit_stock_panel(context, chat_id)
    
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


def register_handlers(application: Application) -> None:
    """Registra comandos, botões e texto na aplicação"""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", show_list))
    application.add_handler(CommandHandler("add", add_item_command))
    application.add_handler(CommandHandler("remove", remove_item_command))
    application.add_handler(CommandHandler("market", market_mode_command))
    application.add_handler(CommandHandler("estoque", stock_command))
    application.add_handler(CommandHandler("baixa", stock_out_command))
    application.add_handler(CommandHandler("carregarestoque", seed_command))
    application.add_handler(CommandHandler("clear", clear_list_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.PINNED_MESSAGE, delete_own_pin_notice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))


def main() -> None:
    """Inicia o bot"""
    bot_token = os.getenv('BOT_TOKEN')
    
    if not bot_token:
        logger.error("❌ ERRO: BOT_TOKEN não encontrado!")
        return
    
    logger.info(f"✅ Token: {bot_token[:20]}...")

    load_data()

    application = Application.builder().token(bot_token).build()
    register_handlers(application)

    application.post_init = on_startup
    
    logger.info("🤖 Bot iniciado!")
    application.run_polling()


if __name__ == '__main__':
    main()
