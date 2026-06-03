# CLAUDE.md

Orientações para o Claude Code trabalhar neste repositório.

## Visão geral

Bot de **lista de compras para Telegram**, escrito em Python. Todo o código vive num
único arquivo (`shopping_list_bot_professional.py`) usando a biblioteca
[`python-telegram-bot`](https://docs.python-telegram-bot.org/) versão `21.8` e a
[`anthropic`](https://docs.anthropic.com/) (opcional, para a categorização por IA).

O foco do bot é uma interface limpa via botões inline (com emojis), um **Modo Mercado**
com checkboxes para marcar itens enquanto se faz compras, e *autoclean* das mensagens
temporárias para não poluir o chat. A lista é **categorizada automaticamente** por seção
de supermercado (Hortifrúti, Açougue, Laticínios...), pode receber/remover **vários
itens de uma vez** (separados por vírgula), suporta **quantidade** por item (`2x leite`),
tem fluxo de **edição** (renomear / quantidade / categoria / remover), sugere os itens
mais comprados (**frequentes**) e **persiste tudo em disco** para não perder a lista nos
deploys/reinícios.

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
- **`DATA_DIR`** (opcional, default `/data`): pasta onde o JSON de persistência é salvo
  (`DATA_FILE = $DATA_DIR/shopping_data.json`). **No Railway, crie um Volume montado em
  `/data`** — sem o Volume, o arquivo some no redeploy (FS do container é efêmero). Em
  dev local, use `DATA_DIR=./data`.
- Para desenvolvimento local pode-se usar um `.env` (já ignorado pelo `.gitignore`),
  mas note que o código **não** chama `python-dotenv` — as variáveis precisam estar no
  ambiente. Exportar manualmente ou adicionar o carregamento do `.env` se for usar.

## Arquitetura

Tudo está em `shopping_list_bot_professional.py`. Pontos principais:

### Estado global (persistido em JSON; UI transitório fica só em memória)
- `shopping_lists[chat_id]` → `{'items': [{'name': str, 'bought': bool, 'category': str, 'quantity': int}], 'created_at': ...}`
  — uma lista por chat. **Persistido.**
- `category_cache[nome_normalizado]` → categoria já resolvida, evita reclassificar. **Persistido.**
- `item_frequency[nome_normalizado]` → `{'count', 'name', 'category'}`, quantas vezes o
  item foi adicionado (base das sugestões). **Persistido.**
- `user_states[f"{chat_id}_{user_id}"]` → estado atual do usuário. (memória)
- `messages_to_delete`, `menu_messages` → controle de mensagens/menu. (memória)
- `edit_target[state_key]` → índice do item em edição; `freq_suggestions[chat_id]` →
  mapeia o botão de frequente clicado. **Só memória (UI transitória).**

A chave de estado por usuário é gerada por `get_user_state_key(chat_id, user_id)`.

### Persistência (`save_data` / `load_data`)
- `load_data()` é chamada no início de `main()`; reidrata `shopping_lists`,
  `category_cache` e `item_frequency` de `DATA_FILE`. Aplica migração suave (itens antigos
  sem `quantity` recebem 1) e reconverte as chaves `chat_id` para `int`.
- `save_data()` grava o JSON de forma atômica (`*.tmp` + `os.replace`), sempre em
  `try/except` (falha de IO não derruba o bot). **Chamar após cada mutação** (add, remove,
  toggle, finalizar/cancelar mercado, limpar, editar, addfreq). Ao adicionar um ramo
  novo que altere a lista, lembre de chamar `save_data()`.

### Máquina de estados
`STATE_NONE` (0), `STATE_ADDING` (1), `STATE_REMOVING` (2), `STATE_MARKET_MODE` (3),
`STATE_EDIT_RENAME` (4), `STATE_EDIT_QTY` (5). O estado controla como `handle_text_message`
interpreta o próximo texto digitado.

### Handlers (registrados em `main()`)
- Comandos: `start`, `show_list` (`/list`), `add_item_command` (`/add`),
  `remove_item_command` (`/remove`), `market_mode_command` (`/market`),
  `clear_list_command` (`/clear`), `cancel_command` (`/cancel`).
- `button_callback` — `CallbackQueryHandler` que trata **todos** os cliques de botão
  inline (despacho por `query.data`): `action_add`, `action_remove`, `action_market_mode`,
  `toggle_<i>`, `market_finish`, `market_cancel`, `market_clear_bought`, `action_clear`,
  `action_cancel`, `confirm_clear`, `cancel_clear`, e os novos `action_edit`, `edit_<i>`,
  `editname_<i>`, `editqty_<i>`, `editcat_<i>`, `setcat_<i>_<catidx>`, `editdel_<i>`,
  `action_frequent`, `addfreq_<i>`.
- `handle_text_message` — texto comum (não-comando); age nos estados `STATE_ADDING`,
  `STATE_REMOVING`, `STATE_EDIT_RENAME` e `STATE_EDIT_QTY`.
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
  `handle_text_message`, o texto é dividido por vírgula. Adição ignora itens curtos (<2);
  remoção valida o intervalo e remove em ordem decrescente de índice.
- **Quantidade**: `parse_quantity` extrai a quantidade de `2x leite`, `2 leite`,
  `leite x2`, `leite 2` (1–99; sem número → 1). `item_label(item)` mostra `Nx Nome` só
  quando `quantity > 1`. **Adicionar um item que já existe SOMA a quantidade** (não
  ignora mais o duplicado).
- **Categorização híbrida**: `categorize_items` tenta `categorize_local` (dicionário
  `CATEGORY_KEYWORDS`, normalização sem acento em `_normalize`) e só os desconhecidos vão
  numa **única** chamada `categorize_ai` (Claude API, modelo Haiku, `AsyncAnthropic`,
  JSON + prompt caching). `sort_items_by_category` reordena por `CATEGORY_ORDER`.
- **Editar** (fluxo por botões): `action_edit` lista os itens → `edit_<i>` abre o submenu
  (renomear → `STATE_EDIT_RENAME`; quantidade → `STATE_EDIT_QTY`; categoria → botões
  `setcat_<i>_<catidx>`; remover → `editdel_<i>`). Renomear re-categoriza e reordena.
- **Frequentes**: `register_frequency` conta cada adição em `item_frequency`.
  `build_frequent_suggestions` retorna os mais comprados que ainda **não** estão na lista;
  `get_frequent_keyboard` monta os botões e guarda o mapeamento em `freq_suggestions`;
  `addfreq_<i>` adiciona com um toque e re-renderiza.

## Convenções importantes

- **Sempre usar HTML, não Markdown**: todas as mensagens passam `parse_mode='HTML'`.
  O texto riscado (`<s>`) só funciona em HTML — não trocar por Markdown.
- **Persistência em JSON num Volume**: `save_data`/`load_data` mantêm a lista entre
  deploys/reinícios. Ao criar qualquer ramo que altere `shopping_lists`/`item_frequency`,
  **chame `save_data()`**. No Railway o Volume precisa estar montado em `/data` (ou ajuste
  `DATA_DIR`), senão o arquivo é efêmero.
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

- Sem testes automatizados, sem lint configurado, sem CI.
- Persistência é um único JSON local (sem banco). Depende de um Volume montado em
  `/data` no Railway; sem o Volume, os dados somem no redeploy.
- `save_data()` grava o arquivo inteiro a cada mutação — simples e suficiente para uso
  pessoal, mas não pensado para alta concorrência/muitos chats.
- Arquivo único monolítico — não há separação por módulos.
- O dicionário `CATEGORY_KEYWORDS` é representativo, não exaustivo; itens fora dele
  dependem da IA (ou caem em "Outros" sem `ANTHROPIC_API_KEY`).
