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
deploys/reinícios. Tem também um **estoque** da casa, usado no grupo da família: dar baixa
desconta do estoque, o que fica abaixo do mínimo entra sozinho na lista, e finalizar a
compra dá entrada no estoque.

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

Testes (não usam rede nem token, o bot roda sobre uma API do Telegram simulada):

```bash
python -m unittest test_estoque
```

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
- `stock[chat_id]` → `[{'id', 'name', 'package', 'category', 'quantity', 'min', 'ideal'}]`,
  o estoque do chat, em embalagens fechadas. **Persistido.** Itens da lista criados ou
  adotados pelo estoque têm `stock_id`.
- `stock_panels[chat_id]` → id da mensagem do painel do estoque. **Persistido.**
- `stock_seeded` → chats que já passaram pela carga inicial. **Persistido.**
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
`STATE_EDIT_RENAME` (4), `STATE_EDIT_QTY` (5), `STATE_STOCK_ADD` (6),
`STATE_STOCK_REMOVE` (7). O estado controla como `handle_text_message`
interpreta o próximo texto digitado.

### Handlers (registrados em `main()`)
- Comandos: `start`, `show_list` (`/list`), `add_item_command` (`/add`),
  `remove_item_command` (`/remove`), `market_mode_command` (`/market`),
  `clear_list_command` (`/clear`), `cancel_command` (`/cancel`), `stock_command`
  (`/estoque`), `stock_out_command` (`/baixa`).
- `button_callback` — `CallbackQueryHandler` que trata **todos** os cliques de botão
  inline (despacho por `query.data`): `action_add`, `action_remove`, `action_market_mode`,
  `toggle_<i>`, `market_finish`, `market_cancel`, `market_clear_bought`, `action_clear`,
  `action_cancel`, `confirm_clear`, `cancel_clear`, e os novos `action_edit`, `edit_<i>`,
  `editname_<i>`, `editqty_<i>`, `editcat_<i>`, `setcat_<i>_<catidx>`, `editdel_<i>`,
  `action_frequent`, `addfreq_<i>`. Os botões `stock_*` são desviados para
  `handle_stock_button` **antes** do `query.answer()`, porque um clique só pode ser
  respondido uma vez e a baixa responde com um aviso.
- `handle_text_message` — texto comum (não-comando); age nos estados `STATE_ADDING`,
  `STATE_REMOVING`, `STATE_EDIT_RENAME`, `STATE_EDIT_QTY`, `STATE_STOCK_ADD` e
  `STATE_STOCK_REMOVE`.
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
- **Duplicados (incl. plural/singular)**: `same_item(a, b)` decide se dois nomes são o
  mesmo item — compara via `_normalize` (sem acento/maiúscula) e tolera plural simples
  (um é o outro + `s`/`es`). É conservador: `ovo`/`ovos` e `banana`/`bananas` fundem, mas
  `leite`/`leite condensado` e plurais irregulares (`pão`/`pães`, `sal`/`sais`) **não**.
  Usado na deduplicação do `STATE_ADDING` (dentro do lote e contra a lista) e no `addfreq`.
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
- **Estoque**:
  - **Embalagem é a unidade**: `quantity`, `min` e `ideal` contam embalagens fechadas, e a
    baixa vale quando a embalagem sai da despensa. `package` é um texto livre ("5 kg",
    "engradado de 12"). Se trouxer tamanho, `stock_total` calcula o total em kg/L.
  - **Regra de compra**: mínimo = consumo de 2 meses, `ideal` = consumo de 3. Estar no
    mínimo ainda é ok; abaixo dele, o item entra na lista com `ideal - quantity`.
  - **Cadastro**: `Arroz (5 kg) 4/3/4` = tem/mínimo/repor até, por linha ou vírgula
    (`split_stock_lines` preserva a vírgula de `(2,4 kg)`). Linha só com o nome de uma seção
    vale para as seguintes (`category_from_line`), e sem ela a categorização é a automática.
    Sem mínimo usa 1; sem ideal usa 1,5 vez o mínimo. Item já cadastrado só atualiza o que
    foi informado (`arroz 4` só corrige a quantidade).
  - **Baixa**: mensagem `-2 arroz` e `+1 arroz` (`_STOCK_MOVE`, aceita travessão do iPhone),
    `/baixa 2 arroz` ou um toque no painel, com botão de devolver. `find_stock_items` casa
    nome exato ou plural, senão trecho do nome; ambíguo não mexe em nada. Mensagem sem item
    reconhecido pode ser conversa: não é apagada. Só vale em `STATE_NONE` e
    `STATE_MARKET_MODE`.
  - **Painel**: mensagem própria, fixada no grupo (`send_stock_panel`), separada do menu da
    lista para não trocar a tela de quem está no Modo Mercado. A navegação é compartilhada
    pelo grupo. `/estoque` e o botão 📦 publicam o painel no fim do chat e fixam. "Voltar
    ao menu" publica a lista (`send_list_menu`, sem tocar na tela do mercado) e apaga o
    painel, o que também tira a fixação. Baixa por mensagem não depende do painel. Sem
    permissão de fixar, tudo funciona igual.
  - **Ligação com a lista**: `sync_stock_item` é o único ponto que liga estoque e lista. Se
    o item voltar ao mínimo, sai da lista. Item manual de mesmo nome é adotado sem reduzir a
    quantidade. Item marcado como comprado não é tocado.
  - **Entrada**: `restock_bought` roda em `market_finish` e `market_clear_bought`: soma ao
    estoque o que foi comprado e **tira o item da lista** (é o que evita somar duas
    vezes), e no fim reconcilia tudo com `sync_all_stock`. Itens fora do estoque continuam
    com o comportamento antigo (ficam marcados na lista).
  - Os botões de estoque usam o `id` do item, e os do Modo Mercado levam um `item_tag`.
    Baixas mudam a lista enquanto alguém está no mercado: só com o índice, um teclado
    desatualizado marcaria o item errado.

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
- **Carga inicial**: `estoque_inicial.txt` tem o inventário da casa, no formato do
  Cadastrar, e é público por decisão da dona do bot. `seed_groups` carrega o arquivo na
  subida, nos grupos que já têm lista salva; `/carregarestoque` faz o mesmo no chat atual.
  `stock_seeded` garante uma única carga por chat. O estoque vivo fica no Volume: editar o
  arquivo não altera um chat já carregado.
- **Toda alteração de quantidade do estoque passa por `sync_stock_item`** (`change_stock`
  já faz isso), senão a lista de compras fica defasada.
- **Idioma**: código, comentários e mensagens ao usuário em **português**. Mantenha
  esse padrão ao editar.
- Edições de mensagem usam `try/except BadRequest` porque o Telegram falha ao editar
  para um conteúdo idêntico — preserve esse padrão.

## Limitações conhecidas

- Testes só em `test_estoque.py` (estoque e fluxos básicos da lista). Sem lint, sem CI.
- Persistência é um único JSON local (sem banco). Depende de um Volume montado em
  `/data` no Railway; sem o Volume, os dados somem no redeploy.
- `save_data()` grava o arquivo inteiro a cada mutação — simples e suficiente para uso
  pessoal, mas não pensado para alta concorrência/muitos chats.
- A mensagem do menu é uma só por chat: `/add` ou `/list` enquanto alguém está no Modo
  Mercado troca a tela dessa pessoa (o que já foi marcado não se perde). Fluxos de edição
  da lista e remoção por número ainda usam índice, e podem errar de item se a lista mudar
  no meio do fluxo.
- `-2 arroz` exige que o bot leia as mensagens do grupo (admin, ou privacy mode desligado
  no BotFather). `/baixa 2 arroz` funciona sempre.
- Item tirado da lista à mão continua abaixo do mínimo e volta na próxima movimentação ou
  ao finalizar uma compra.
- Arquivo único monolítico — não há separação por módulos.
- O dicionário `CATEGORY_KEYWORDS` é representativo, não exaustivo; itens fora dele
  dependem da IA (ou caem em "Outros" sem `ANTHROPIC_API_KEY`).
