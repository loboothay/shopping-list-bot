# CLAUDE.md

Orientações para o Claude Code trabalhar neste repositório.

## Visão geral

Bot de **lista de compras para Telegram**, escrito em Python. Todo o código vive num
único arquivo (`shopping_list_bot_professional.py`, ~734 linhas) usando a biblioteca
[`python-telegram-bot`](https://docs.python-telegram-bot.org/) versão `21.8`.

O foco do bot é uma interface limpa via botões inline (com emojis), um **Modo Mercado**
com checkboxes para marcar itens enquanto se faz compras, e *autoclean* das mensagens
temporárias para não poluir o chat. A lista é **categorizada automaticamente** por seção
de supermercado (Hortifrúti, Açougue, Laticínios...) e pode receber/remover **vários
itens de uma vez**, separados por vírgula.

## Como rodar

```bash
# Instalar dependências
pip install -r requirements.txt

# Definir o token (obtido com o @BotFather)
export BOT_TOKEN="seu_token_aqui"

# Rodar
python shopping_list_bot_professional.py
```

O bot usa **long polling** (`application.run_polling()`), não webhooks.

Deploy: o `Procfile` define um worker estilo Heroku:
`worker: python shopping_list_bot_professional.py`.

## Configuração

- **`BOT_TOKEN`** (obrigatório): token do Telegram. Lido via `os.getenv('BOT_TOKEN')`
  em `main()`. Se ausente, o bot loga erro e encerra sem iniciar.
- **`ANTHROPIC_API_KEY`** (opcional): habilita a categorização por IA dos itens que o
  dicionário local não reconhece. Lida sob demanda em `categorize_ai`. **Sem ela o bot
  funciona normalmente** — itens desconhecidos caem em "Outros".
- Para desenvolvimento local pode-se usar um `.env` (já ignorado pelo `.gitignore`),
  mas note que o código **não** chama `python-dotenv` — as variáveis precisam estar no
  ambiente. Exportar manualmente ou adicionar o carregamento do `.env` se for usar.

## Arquitetura

Tudo está em `shopping_list_bot_professional.py`. Pontos principais:

### Estado (em memória, global — NÃO persistente)
- `shopping_lists[chat_id]` → `{'items': [{'name': str, 'bought': bool, 'category': str}], 'created_at': datetime}`
  — uma lista por chat. Cada item tem uma `category` (uma de `CATEGORY_ORDER`).
- `user_states[f"{chat_id}_{user_id}"]` → estado atual do usuário naquele chat.
- `messages_to_delete[f"{chat_id}_{user_id}"]` → ids de mensagens a limpar depois.
- `menu_messages[chat_id]` → id da mensagem-menu única do chat (editada, não recriada).
- `category_cache[nome_normalizado]` → categoria já resolvida, evita reclassificar.

A chave de estado por usuário é gerada por `get_user_state_key(chat_id, user_id)`.

### Máquina de estados
`STATE_NONE` (0), `STATE_ADDING` (1), `STATE_REMOVING` (2), `STATE_MARKET_MODE` (3).
O estado controla como `handle_text_message` interpreta o próximo texto digitado.

### Handlers (registrados em `main()`)
- Comandos: `start`, `show_list` (`/list`), `add_item_command` (`/add`),
  `remove_item_command` (`/remove`), `market_mode_command` (`/market`),
  `clear_list_command` (`/clear`), `cancel_command` (`/cancel`).
- `button_callback` — `CallbackQueryHandler` que trata **todos** os cliques de botão
  inline (despacho por `query.data`: `action_add`, `action_remove`, `action_market_mode`,
  `toggle_<i>`, `market_finish`, `market_cancel`, `market_clear_bought`, `action_clear`,
  `action_cancel`, `confirm_clear`, `cancel_clear`).
- `handle_text_message` — texto comum (não-comando); só age se houver estado ativo
  (`STATE_ADDING` ou `STATE_REMOVING`).
- `set_bot_commands` roda em `application.post_init` e registra o menu de comandos.

### Funcionalidades-chave
- **Modo Mercado**: teclado com um botão por item (`⬜`/`✅`); `toggle_<i>` alterna
  `item['bought']`. Botões "✔️ Finalizar", "❌ Cancelar" e (quando há comprados)
  "🧹 Remover Comprados".
- **Autoclean**: `delete_message_safe`, `track_message` e `cleanup_messages` apagam
  mensagens de comando e mensagens temporárias (após `asyncio.sleep` de 1–2s).
  `update_menu` edita o menu existente em vez de criar um novo.
- **Texto riscado**: itens comprados aparecem com `<s>...</s>` em `get_list_text`.
- **Multi-add / multi-remove**: no ramo `STATE_ADDING`/`STATE_REMOVING` de
  `handle_text_message`, o texto é dividido por vírgula. Adição ignora itens curtos
  (<2) e duplicados; remoção valida o intervalo e remove em ordem decrescente de índice.
- **Categorização híbrida**: ao adicionar, `categorize_items` tenta `categorize_local`
  (dicionário `CATEGORY_KEYWORDS`, normalização sem acento em `_normalize`) e só os
  desconhecidos vão numa **única** chamada `categorize_ai` (Claude API, modelo Haiku,
  `AsyncAnthropic`, JSON + prompt caching). `sort_items_by_category` reordena a lista
  por `CATEGORY_ORDER` após cada adição.

## Convenções importantes

- **Sempre usar HTML, não Markdown**: todas as mensagens passam `parse_mode='HTML'`.
  O texto riscado (`<s>`) só funciona em HTML — não trocar por Markdown.
- **Estado é volátil**: reiniciar o processo zera todas as listas. Não há banco de
  dados nem arquivo de persistência. Se for adicionar persistência, é uma mudança
  estrutural (todos os dicts globais precisariam de um backend).
- **Numeração da lista é global e contínua entre categorias** e, como a lista é mantida
  ordenada por `sort_items_by_category`, o número exibido coincide com o índice na lista
  — é isso que faz a remoção por número funcionar. Se mudar a ordenação, ajuste a remoção.
- **A IA roda via `AsyncAnthropic`** (cliente assíncrono) dentro do handler — nunca usar
  o cliente síncrono, pois bloquearia o long polling. Sempre num `try/except` com
  fallback para "Outros".
- **Idioma**: código, comentários e mensagens ao usuário em **português**. Mantenha
  esse padrão ao editar.
- Edições de mensagem usam `try/except BadRequest` porque o Telegram falha ao editar
  para um conteúdo idêntico — preserve esse padrão.

## Limitações conhecidas

- Sem testes, sem lint configurado, sem CI.
- Sem persistência (dados em memória — inclusive o `category_cache`).
- Arquivo único monolítico — não há separação por módulos.
- O dicionário `CATEGORY_KEYWORDS` é representativo, não exaustivo; itens fora dele
  dependem da IA (ou caem em "Outros" sem `ANTHROPIC_API_KEY`).
