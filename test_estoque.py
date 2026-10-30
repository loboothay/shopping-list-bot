#!/usr/bin/env python3
"""
Testes do estoque, ponta a ponta: o bot real roda sobre uma API do Telegram simulada,
e cada teste toca nos botões que o bot realmente desenhou.

Rodar: python -m unittest test_estoque
"""

import json
import os
import re
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

os.environ['DATA_DIR'] = tempfile.mkdtemp()
os.environ.pop('ANTHROPIC_API_KEY', None)

from telegram import Update
from telegram.ext import Application
from telegram.request import BaseRequest

import shopping_list_bot_professional as bot

CHAT = {'id': -100, 'type': 'group', 'title': 'Casa'}
USER = {'id': 7, 'is_bot': False, 'first_name': 'Ana'}
OTHER = {'id': 8, 'is_bot': False, 'first_name': 'Bia'}
BOT_USER = {'id': 1, 'is_bot': True, 'first_name': 'Bot'}


class FakeTelegram(BaseRequest):
    """API do Telegram em memória, com as validações que o Telegram real faz."""

    def __init__(self):
        self.messages = {}
        self.toasts = []
        self.deleted = []
        self.pinned = []
        self.pin_error = None
        self.next_id = 100000

    @property
    def read_timeout(self):
        return None

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    def _error(self, description):
        return 400, json.dumps({'ok': False, 'error_code': 400, 'description': description}).encode()

    def _check(self, params):
        text = params.get('text', '')
        if len(text) > 4096:
            return 'Bad Request: message is too long'
        if re.search(r'&(?!amp;|lt;|gt;|quot;|#)', text):
            return "Bad Request: can't parse entities"
        keyboard = params['reply_markup']['inline_keyboard'] if params.get('reply_markup') else []
        buttons = [b for row in keyboard for b in row]
        if len(buttons) > 100:
            return 'Bad Request: too many buttons'
        if any(len(b['callback_data'].encode()) > 64 for b in buttons):
            return 'Bad Request: BUTTON_DATA_INVALID'
        return None

    def _message(self, message_id, params):
        return {'message_id': message_id, 'date': 0, 'chat': CHAT, 'text': params.get('text', '')}

    async def do_request(self, url, method, request_data=None, **kwargs):
        name = url.rsplit('/', 1)[1]
        params = request_data.parameters if request_data else {}

        if name == 'getMe':
            result = {**BOT_USER, 'username': 'casa_bot', 'can_join_groups': True,
                      'can_read_all_group_messages': True, 'supports_inline_queries': False}
        elif name == 'sendMessage':
            error = self._check(params)
            if error:
                return self._error(error)
            self.next_id += 1
            self.messages[self.next_id] = params
            result = self._message(self.next_id, params)
        elif name == 'editMessageText':
            error = self._check(params)
            if error:
                return self._error(error)
            message_id = params['message_id']
            if message_id not in self.messages:
                return self._error('Bad Request: message to edit not found')
            old = self.messages[message_id]
            if old.get('text') == params.get('text') and old.get('reply_markup') == params.get('reply_markup'):
                return self._error('Bad Request: message is not modified')
            self.messages[message_id] = params
            result = self._message(message_id, params)
        elif name == 'deleteMessage':
            self.messages.pop(params['message_id'], None)
            self.deleted.append(params['message_id'])
            result = True
        elif name == 'pinChatMessage':
            if self.pin_error:
                return self._error(self.pin_error)
            self.pinned.append(params['message_id'])
            result = True
        elif name == 'answerCallbackQuery':
            self.toasts.append(params.get('text'))
            result = True
        else:
            result = True

        return 200, json.dumps({'ok': True, 'result': result}).encode()


class StockTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        for store in (bot.shopping_lists, bot.user_states, bot.messages_to_delete, bot.menu_messages,
                      bot.category_cache, bot.item_frequency, bot.stock, bot.stock_panels, bot.stock_seeded,
                      bot.edit_target,
                      bot.freq_suggestions, bot.market_hide_bought):
            store.clear()
        if os.path.exists(bot.DATA_FILE):
            os.remove(bot.DATA_FILE)

        self.api = FakeTelegram()
        self.app = Application.builder().token('1:abc').request(self.api).get_updates_request(FakeTelegram()).build()
        bot.register_handlers(self.app)
        self.handler_errors = []
        self.app.add_error_handler(self.record_error)
        await self.app.initialize()
        self.update_id = 0

        sleep = patch('asyncio.sleep', AsyncMock())
        sleep.start()
        self.addCleanup(sleep.stop)
        await self.send('/start')

    async def record_error(self, update, context):
        self.handler_errors.append(context.error)

    async def asyncTearDown(self):
        await self.app.shutdown()
        self.assertEqual(self.handler_errors, [])

    @property
    def stock(self):
        return bot.stock.get(CHAT['id'], [])

    @property
    def shopping(self):
        return bot.shopping_lists[CHAT['id']]['items']

    @property
    def panel_id(self):
        return bot.stock_panels.get(CHAT['id'])

    @property
    def menu_id(self):
        return bot.menu_messages.get(CHAT['id'])

    def stocked(self, name):
        return next(it for it in self.stock if bot.same_item(it['name'], name))

    def listed(self, name):
        for it in self.shopping:
            if bot.same_item(it['name'], name) or _normalize_starts(it['name'], name):
                return it
        return None

    async def send(self, text, user=USER):
        self.update_id += 1
        message = {'message_id': self.update_id, 'date': 0, 'chat': CHAT, 'from': user, 'text': text}
        if text.startswith('/'):
            message['entities'] = [{'type': 'bot_command', 'offset': 0, 'length': len(text.split()[0])}]
        await self.app.process_update(Update.de_json({'update_id': self.update_id, 'message': message}, self.app.bot))
        return self.update_id

    async def press_data(self, data, message_id=None, user=USER):
        self.update_id += 1
        query = {
            'id': str(self.update_id), 'from': user, 'chat_instance': 'x', 'data': data,
            'message': {'message_id': message_id or self.menu_id, 'date': 0, 'chat': CHAT, 'text': 'x'},
        }
        await self.app.process_update(Update.de_json({'update_id': self.update_id, 'callback_query': query}, self.app.bot))

    def buttons_of(self, message_id):
        params = self.api.messages.get(message_id)
        if not params or not params.get('reply_markup'):
            return []
        return [b for row in params['reply_markup']['inline_keyboard'] for b in row]

    def find_button(self, label):
        """Procura o botão no painel e no menu, como quem olha para o grupo."""
        for message_id in (self.panel_id, self.menu_id):
            for b in self.buttons_of(message_id):
                if label.lower() in b['text'].lower():
                    return message_id, b['callback_data']
        self.fail(f"Botão {label!r} não está na tela")

    async def press(self, label, user=USER):
        message_id, data = self.find_button(label)
        await self.press_data(data, message_id, user)

    def panel_text(self):
        return self.api.messages[self.panel_id]['text']

    def menu_text(self):
        return self.api.messages[self.menu_id]['text']

    async def register(self, text):
        await self.send('/estoque')
        await self.press('Cadastrar')
        await self.send(text)

    async def open_category(self, label):
        await self.send('/estoque')
        await self.press(label)

    async def take(self, name, category='Mercearia'):
        await self.open_category(category)
        await self.press(f'{name} ·')


def _normalize_starts(listed_name, name):
    """O nome na lista traz a embalagem: 'arroz (5 kg)' é o item 'arroz'."""
    return bot._normalize(listed_name).startswith(bot._normalize(name) + ' (')


class CadastroTest(StockTestCase):
    async def test_cadastro_le_embalagem_atual_minimo_e_repor_ate(self):
        await self.register('Arroz (5 kg) 4/3/4')
        item = self.stocked('arroz')
        self.assertEqual((item['package'], item['quantity'], item['min'], item['ideal']), ('5 kg', 4, 3, 4))
        self.assertEqual(item['category'], 'Mercearia')

    async def test_embalagem_e_opcional(self):
        await self.register('arroz 3/2/5')
        self.assertEqual(self.stocked('arroz')['package'], '')

    async def test_virgula_da_embalagem_nao_separa_itens(self):
        await self.register('Sabão em pó (2,4 kg) 3/2/3, Amaciante (1,5 L) 3/2/3')
        self.assertEqual([it['package'] for it in self.stock], ['2,4 kg', '1,5 L'])

    async def test_cadastro_aceita_varios_por_virgula_e_por_linha(self):
        await self.register('arroz 3/2/5, feijão 1/2/4\nsal 5/1/2')
        self.assertEqual(len(self.stock), 3)

    async def test_linha_de_secao_vale_para_as_seguintes(self):
        await self.register('Limpeza\nÁgua sanitária (2 L) 1/1/2\nHigiene\nProtetor (pacote de 80) 2/1/2')
        self.assertEqual(self.stocked('água sanitária')['category'], 'Limpeza')
        self.assertEqual(self.stocked('protetor')['category'], 'Higiene')

    async def test_secao_corrige_item_ja_cadastrado(self):
        await self.register('Água sanitária (2 L) 1/1/2')
        await self.register('Limpeza\nÁgua sanitária 1')
        self.assertEqual(self.stocked('água sanitária')['category'], 'Limpeza')

    async def test_item_ja_abaixo_do_minimo_entra_na_lista_no_cadastro(self):
        await self.register('feijão 1/2/4')
        self.assertEqual(self.listed('feijão')['quantity'], 3)

    async def test_defaults_minimo_1_e_repor_ate_1_5_vez_o_minimo(self):
        await self.register('sal 5')
        self.assertEqual((self.stocked('sal')['min'], self.stocked('sal')['ideal']), (1, 2))
        await self.register('café 5/4')
        self.assertEqual(self.stocked('café')['ideal'], 6)
        await self.register('chá 5/3')
        self.assertEqual(self.stocked('chá')['ideal'], 5)

    async def test_recadastrar_so_quantidade_preserva_o_resto(self):
        await self.register('Arroz (5 kg) 3/2/5')
        await self.register('arroz 4')
        item = self.stocked('arroz')
        self.assertEqual((item['package'], item['quantity'], item['min'], item['ideal']), ('5 kg', 4, 2, 5))
        self.assertEqual(len(self.stock), 1)

    async def test_ideal_menor_que_minimo_sobe_para_o_minimo(self):
        await self.register('arroz 0/4/1')
        self.assertEqual(self.stocked('arroz')['ideal'], 4)
        self.assertEqual(self.listed('arroz')['quantity'], 4)

    async def test_minimo_zero_nunca_entra_na_lista(self):
        await self.register('sal 0/0/0')
        self.assertIsNone(self.listed('sal'))

    async def test_sem_quantidade_e_ignorado_e_o_resto_e_salvo(self):
        await self.register('arroz, feijão 1/2/4')
        self.assertEqual([it['name'] for it in self.stock], ['feijão'])

    async def test_cadastro_em_massa_nao_estoura_a_mensagem(self):
        await self.register('\n'.join(f'produto {i} 5/1/2' for i in range(150)))
        self.assertEqual(len(self.stock), 150)


class EmbalagemTest(StockTestCase):
    async def test_total_em_kg_e_litros(self):
        await self.register('Arroz (5 kg) 3/1/2\nAmaciante (1,5 L) 3/1/2\nSal (500 g) 3/1/2\nÓleo (900 ml) 6/1/2')
        self.assertEqual(bot.stock_amount(self.stocked('arroz')), '3 (15 kg)')
        self.assertEqual(bot.stock_amount(self.stocked('amaciante')), '3 (4,5 L)')
        self.assertEqual(bot.stock_amount(self.stocked('sal')), '3 (1,5 kg)')
        self.assertEqual(bot.stock_amount(self.stocked('óleo')), '6 (5,4 L)')

    async def test_embalagem_sem_tamanho_mostra_so_a_quantidade(self):
        await self.register('Protetor (pacote de 80) 2/1/2')
        self.assertEqual(bot.stock_amount(self.stocked('protetor')), '2')

    async def test_lista_de_compras_mostra_a_embalagem(self):
        await self.register('Arroz (5 kg) 1/3/4')
        self.assertEqual(self.listed('arroz')['name'], 'Arroz (5 kg)')
        self.assertEqual(self.listed('arroz')['quantity'], 3)

    async def test_toque_tira_uma_embalagem(self):
        await self.register('Arroz (5 kg) 4/3/4')
        await self.take('Arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 3)
        self.assertIn('3 (15 kg)', self.api.toasts[-1])


class BaixaPorBotaoTest(StockTestCase):
    async def test_no_minimo_nao_entra_e_abaixo_entra_com_o_que_falta_para_repor(self):
        await self.register('arroz 3/2/5')
        await self.take('arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 2)
        self.assertIsNone(self.listed('arroz'))
        await self.take('arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 1)
        self.assertEqual(self.listed('arroz')['quantity'], 4)

    async def test_nova_baixa_atualiza_a_quantidade_na_lista(self):
        await self.register('arroz 1/2/5')
        await self.take('arroz')
        self.assertEqual(self.listed('arroz')['quantity'], 5)
        self.assertEqual(len(self.shopping), 1)

    async def test_devolver_desfaz_e_tira_da_lista(self):
        await self.register('arroz 2/2/5')
        await self.take('arroz')
        self.assertIsNotNone(self.listed('arroz'))
        await self.press('Devolver')
        self.assertEqual(self.stocked('arroz')['quantity'], 2)
        self.assertIsNone(self.listed('arroz'))

    async def test_baixa_em_item_zerado_nao_fica_negativo(self):
        await self.register('arroz 0/2/5')
        await self.take('arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 0)
        self.assertIn('zerado', self.api.toasts[-1])

    async def test_aviso_mostra_o_que_comprar(self):
        await self.register('arroz 2/2/5')
        await self.take('arroz')
        self.assertIn('2 → 1', self.api.toasts[-1])
        self.assertIn('comprar 4', self.api.toasts[-1])

    async def test_paginacao_alcanca_todos_os_itens(self):
        nomes = [f'arroz {chr(97 + i // 26)}{chr(97 + i % 26)}' for i in range(70)]
        await self.register(', '.join(f'{n} 5/1/2' for n in nomes))
        await self.open_category('Mercearia')
        vistos = set()
        while True:
            vistos |= {b['text'] for b in self.buttons_of(self.panel_id) if b['callback_data'].startswith('stock_dn')}
            if not any(b['text'] == '▶️' for b in self.buttons_of(self.panel_id)):
                break
            await self.press('▶️')
        self.assertEqual(len(vistos), 70)

    async def test_botao_antigo_de_item_removido_nao_quebra(self):
        await self.register('arroz 3/1/2, feijão 3/1/2')
        await self.open_category('Mercearia')
        _, antigo = self.find_button('arroz ·')
        bot.remove_stock_item(CHAT['id'], self.stocked('arroz'))
        await self.press_data(antigo, self.panel_id)
        self.assertIn('não está mais', self.api.toasts[-1])

    async def test_outra_pessoa_da_baixa_no_mesmo_painel(self):
        await self.register('arroz 5/1/2')
        await self.open_category('Mercearia')
        await self.press('arroz ·', user=OTHER)
        await self.press('arroz ·', user=USER)
        self.assertEqual(self.stocked('arroz')['quantity'], 3)


class BaixaPorMensagemTest(StockTestCase):
    async def test_menos_da_baixa_e_apaga_a_mensagem(self):
        await self.register('arroz 5/1/5')
        message_id = await self.send('-2 arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 3)
        self.assertIn(message_id, self.api.deleted)

    async def test_mais_devolve(self):
        await self.register('arroz 3/1/5')
        await self.send('+2 arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 5)

    async def test_sem_numero_vale_uma_embalagem(self):
        await self.register('arroz 3/1/5')
        await self.send('-arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 2)

    async def test_aceita_varios_itens_sem_acento_e_em_qualquer_caixa(self):
        await self.register('arroz 5/1/5, feijão 5/1/5')
        await self.send('- 2 ARROZ, feijao')
        self.assertEqual(self.stocked('arroz')['quantity'], 3)
        self.assertEqual(self.stocked('feijão')['quantity'], 4)

    async def test_travessao_do_iphone_tambem_vale(self):
        await self.register('arroz 5/1/5')
        await self.send('—2 arroz')
        await self.send('–arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 2)

    async def test_qualquer_pessoa_do_grupo_pode_dar_baixa(self):
        await self.register('arroz 5/1/5')
        await self.send('-arroz', user=OTHER)
        self.assertEqual(self.stocked('arroz')['quantity'], 4)

    async def test_conversa_comum_nao_e_tocada(self):
        await self.register('arroz 5/1/5')
        message_id = await self.send('amanhã eu compro arroz')
        self.assertNotIn(message_id, self.api.deleted)
        self.assertEqual(self.stocked('arroz')['quantity'], 5)

    async def test_mensagem_com_traco_sem_item_conhecido_nao_e_apagada(self):
        await self.register('arroz 5/1/5')
        message_id = await self.send('- bom dia, família')
        self.assertNotIn(message_id, self.api.deleted)
        self.assertEqual(self.stocked('arroz')['quantity'], 5)

    async def test_trecho_de_um_so_item_funciona(self):
        await self.register('Biscoito cream cracker 5/1/5')
        await self.send('-cracker')
        self.assertEqual(self.stocked('biscoito cream cracker')['quantity'], 4)

    async def test_trecho_ambiguo_nao_baixa_nada(self):
        await self.register('arroz branco 5/1/5, arroz integral 5/1/5')
        await self.send('-arroz')
        self.assertEqual([it['quantity'] for it in self.stock], [5, 5])

    async def test_nome_exato_vence_o_trecho(self):
        await self.register('leite 5/1/5, leite condensado 5/1/5')
        await self.send('-leite')
        self.assertEqual(self.stocked('leite')['quantity'], 4)
        self.assertEqual(self.stocked('leite condensado')['quantity'], 5)

    async def test_baixa_acima_do_saldo_para_em_zero(self):
        await self.register('arroz 2/1/5')
        await self.send('-9 arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 0)

    async def test_funciona_para_quem_saiu_do_mercado_sem_finalizar(self):
        await self.register('arroz 5/1/5')
        await self.send('/add')
        await self.send('leite')
        await self.send('/market')
        await self.send('-arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 4)

    async def test_conversa_de_quem_saiu_do_mercado_nao_e_apagada(self):
        await self.send('/add')
        await self.send('leite')
        await self.send('/market')
        message_id = await self.send('já saí do mercado')
        self.assertNotIn(message_id, self.api.deleted)

    async def test_durante_adicionar_o_traco_nao_vira_baixa(self):
        await self.register('arroz 5/1/5')
        await self.send('/add')
        await self.send('-arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 5)

    async def test_comando_baixa_tambem_funciona(self):
        await self.register('arroz 5/1/5, feijão 5/1/5')
        await self.send('/baixa 2 arroz, feijao')
        self.assertEqual(self.stocked('arroz')['quantity'], 3)
        self.assertEqual(self.stocked('feijão')['quantity'], 4)

    async def test_comando_baixa_sem_argumento_abre_o_painel(self):
        await self.send('/baixa')
        self.assertIn('ESTOQUE', self.panel_text())

    async def test_item_desconhecido_nao_quebra(self):
        await self.send('/baixa unicornio')
        await self.send('-unicornio')
        self.assertEqual(self.stock, [])

    async def test_mensagem_atualiza_o_painel(self):
        await self.register('arroz 2/2/5')
        await self.send('-arroz')
        self.assertIn('1 abaixo do mínimo', self.panel_text())

    async def test_mensagem_atualiza_a_lista_na_tela(self):
        await self.register('arroz 2/2/5')
        await self.send('/start')
        await self.send('-arroz')
        self.assertIn('arroz', self.menu_text())

    async def test_mensagem_nao_derruba_a_tela_do_modo_mercado(self):
        await self.register('arroz 2/2/5')
        await self.send('/add')
        await self.send('leite')
        await self.send('/market')
        tela = self.menu_text()
        await self.send('-arroz')
        self.assertEqual(self.menu_text(), tela)


class PainelTest(StockTestCase):
    async def test_painel_e_publicado_e_fixado_sem_notificar(self):
        await self.send('/estoque')
        self.assertEqual(self.api.pinned, [self.panel_id])

    async def test_painel_nao_troca_a_tela_do_mercado(self):
        await self.send('/add')
        await self.send('leite')
        await self.send('/market')
        tela = self.menu_text()
        await self.send('/estoque')
        self.assertEqual(self.menu_text(), tela)
        self.assertNotEqual(self.panel_id, self.menu_id)

    async def test_sem_permissao_para_fixar_o_painel_funciona(self):
        self.api.pin_error = 'Bad Request: not enough rights to manage pinned messages in the chat'
        await self.register('arroz 5/1/5')
        await self.take('arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 4)

    async def test_abrir_de_novo_substitui_o_painel_anterior(self):
        await self.send('/estoque')
        antigo = self.panel_id
        await self.send('/estoque')
        self.assertIn(antigo, self.api.deleted)
        self.assertNotEqual(self.panel_id, antigo)

    async def test_botao_do_menu_abre_o_painel_e_mantem_a_lista(self):
        await self.press('Estoque')
        self.assertIn('ESTOQUE', self.panel_text())
        self.assertIn('LISTA DE MERCADO', self.menu_text())

    async def test_voltar_da_secao_retorna_ao_painel(self):
        await self.register('arroz 5/1/5')
        await self.open_category('Mercearia')
        await self.press('Voltar')
        self.assertIn('ESTOQUE', self.panel_text())

    async def test_voltar_do_cadastro_nao_deixa_o_estado_preso(self):
        await self.send('/estoque')
        await self.press('Cadastrar')
        await self.press('Voltar')
        await self.send('arroz 3/2/5')
        self.assertEqual(self.stock, [])

    async def test_aviso_de_fixacao_do_bot_e_apagado(self):
        self.update_id += 1
        notice = {'message_id': self.update_id, 'date': 0, 'chat': CHAT, 'from': BOT_USER,
                  'pinned_message': {'message_id': 5, 'date': 0, 'chat': CHAT, 'text': 'x'}}
        await self.app.process_update(Update.de_json({'update_id': self.update_id, 'message': notice}, self.app.bot))
        self.assertIn(self.update_id, self.api.deleted)

    async def test_aviso_de_fixacao_de_pessoa_fica(self):
        self.update_id += 1
        notice = {'message_id': self.update_id, 'date': 0, 'chat': CHAT, 'from': USER,
                  'pinned_message': {'message_id': 5, 'date': 0, 'chat': CHAT, 'text': 'x'}}
        await self.app.process_update(Update.de_json({'update_id': self.update_id, 'message': notice}, self.app.bot))
        self.assertNotIn(self.update_id, self.api.deleted)

    async def test_tela_de_tirar_do_estoque_com_nomes_demais_nao_quebra(self):
        await self.register('\n'.join(f'M&M sabor {i} 5/1/2' for i in range(400)))
        await self.send('/estoque')
        await self.press('Tirar do estoque')
        self.assertIn('TIRAR DO ESTOQUE', self.panel_text())


class MercadoTest(StockTestCase):
    async def comprar(self, *nomes):
        await self.send('/market')
        for nome in nomes:
            await self.press(nome)

    async def test_ciclo_completo_baixa_lista_compra_entrada(self):
        await self.register('Arroz (5 kg) 3/3/4')
        await self.send('-arroz')
        self.assertEqual(self.listed('arroz')['quantity'], 2)
        await self.comprar('Arroz')
        await self.press('Finalizar')
        self.assertEqual(self.stocked('arroz')['quantity'], 4)
        self.assertIsNone(self.listed('arroz'))

    async def test_finalizar_atualiza_o_painel(self):
        await self.register('arroz 1/2/5')
        await self.comprar('arroz')
        await self.press('Finalizar')
        self.assertNotIn('abaixo do mínimo', self.panel_text())

    async def test_marcar_sem_finalizar_nao_da_entrada(self):
        await self.register('arroz 1/2/5')
        await self.comprar('arroz')
        self.assertEqual(self.stocked('arroz')['quantity'], 1)

    async def test_finalizar_duas_vezes_nao_soma_duas_vezes(self):
        await self.register('arroz 1/2/5')
        await self.comprar('arroz')
        await self.press_data('market_finish')
        await self.press_data('market_finish')
        self.assertEqual(self.stocked('arroz')['quantity'], 5)

    async def test_compra_parcial_volta_para_a_lista_com_o_restante(self):
        await self.register('arroz 0/2/5')
        self.listed('arroz')['quantity'] = 1
        await self.comprar('arroz')
        await self.press('Finalizar')
        self.assertEqual(self.stocked('arroz')['quantity'], 1)
        self.assertEqual(self.listed('arroz')['quantity'], 4)
        self.assertFalse(self.listed('arroz')['bought'])

    async def test_item_nao_marcado_nao_entra_no_estoque(self):
        await self.register('arroz 1/2/5, feijão 1/2/5')
        await self.comprar('feijão')
        await self.press('Finalizar')
        self.assertEqual(self.stocked('arroz')['quantity'], 1)
        self.assertEqual(self.stocked('feijão')['quantity'], 5)
        self.assertIsNotNone(self.listed('arroz'))

    async def test_item_manual_fora_do_estoque_mantem_o_comportamento_antigo(self):
        await self.send('/add')
        await self.send('vela')
        await self.comprar('vela')
        await self.press('Finalizar')
        self.assertTrue(self.listed('vela')['bought'])

    async def test_cancelar_mercado_nao_da_entrada(self):
        await self.register('arroz 1/2/5')
        await self.comprar('arroz')
        await self.press('Cancelar')
        self.assertEqual(self.stocked('arroz')['quantity'], 1)
        self.assertFalse(self.listed('arroz')['bought'])

    async def test_baixa_enquanto_item_esta_no_carrinho_reconcilia_ao_cancelar(self):
        await self.register('arroz 1/2/5')
        await self.comprar('arroz')
        await self.send('-arroz')
        self.assertEqual(self.listed('arroz')['quantity'], 4)
        await self.press_data('market_cancel')
        self.assertEqual(self.listed('arroz')['quantity'], 5)

    async def test_remover_comprados_tambem_da_entrada(self):
        await self.register('arroz 1/2/5')
        await self.send('/add')
        await self.send('vela')
        await self.comprar('arroz', 'vela')
        await self.press('Remover Comprados')
        self.assertEqual(self.stocked('arroz')['quantity'], 5)
        self.assertEqual(self.shopping, [])

    async def test_teclado_desatualizado_marca_o_item_certo(self):
        await self.register('carne 5/1/2')
        await self.send('/add')
        await self.send('arroz')
        await self.send('/market')
        _, toggle_arroz = self.find_button('arroz')
        # Carne vem antes de arroz na ordenação, então o índice de arroz muda
        await self.send('-5 carne', user=OTHER)
        self.assertEqual(self.shopping[0]['name'], 'carne')
        await self.press_data(toggle_arroz)
        self.assertTrue(self.listed('arroz')['bought'])
        self.assertFalse(self.listed('carne')['bought'])

    async def test_item_comprado_com_baixa_nao_some_da_lista_de_quem_compra(self):
        await self.register('arroz 1/2/5')
        await self.comprar('arroz')
        await self.send('-arroz')
        self.assertTrue(self.listed('arroz')['bought'])


class ListaTest(StockTestCase):
    async def test_item_manual_de_mesmo_nome_e_adotado_sem_reduzir(self):
        await self.send('/add')
        await self.send('9x arroz')
        await self.register('arroz 1/2/3')
        self.assertEqual(self.listed('arroz')['quantity'], 9)
        self.assertEqual(self.listed('arroz')['stock_id'], self.stocked('arroz')['id'])

    async def test_item_da_lista_renomeado_continua_vinculado(self):
        await self.register('arroz 1/2/5')
        self.listed('arroz')['name'] = 'arroz tio joao'
        await self.send('-arroz')
        self.assertEqual(len(self.shopping), 1)
        self.assertEqual(self.shopping[0]['quantity'], 5)

    async def test_tirar_do_estoque_mantem_na_lista_e_desvincula(self):
        await self.register('arroz 1/2/5')
        await self.send('/estoque')
        await self.press('Tirar do estoque')
        await self.send('arroz')
        self.assertEqual(self.stock, [])
        self.assertNotIn('stock_id', self.listed('arroz'))

    async def test_recadastrar_apos_tirar_nao_duplica_na_lista(self):
        await self.register('Arroz (5 kg) 1/2/5')
        bot.remove_stock_item(CHAT['id'], self.stocked('arroz'))
        await self.register('Arroz (5 kg) 1/2/5')
        self.assertEqual(len(self.shopping), 1)

    async def test_nome_com_caractere_especial_nao_quebra_as_telas(self):
        await self.register('M&M 0/1/2')
        await self.send('/list')
        self.assertIn('M&amp;M', self.menu_text())
        await self.open_category('Outros')
        await self.press('M&M ·')

    async def test_fluxos_antigos_da_lista_continuam_funcionando(self):
        await self.send('/add')
        await self.send('2x leite, ovos')
        self.assertEqual(self.listed('leite')['quantity'], 2)
        await self.send('/remove')
        await self.send('1')
        self.assertEqual(len(self.shopping), 1)
        await self.send('/clear')
        await self.press('Sim')
        self.assertEqual(self.shopping, [])


class CargaInicialTest(StockTestCase):
    async def test_carrega_a_lista_real_com_as_compras_aprovadas(self):
        await bot.seed_groups(self.app)
        self.assertEqual(len(self.stock), 62)
        with open(bot.SEED_FILE, encoding='utf-8') as f:
            self.assertEqual(bot.parse_stock_text(f.read())[1], [])
        compras = {it['name']: it['quantity'] for it in self.shopping}
        self.assertEqual(compras, {
            'Pipoca (pacote)': 2, 'Café (pacote)': 5, 'Biscoito cream cracker (350 g)': 1,
            'Biscoito de leite (350 g)': 1, 'Papel higiênico (pacote de 42 rolos)': 2,
            'Shampoo (1 L)': 1, 'Condicionador (1 L)': 1,
        })
        self.assertEqual(self.stocked('Água sanitária grande')['category'], 'Limpeza')

    async def test_publica_e_fixa_o_painel_no_grupo(self):
        await bot.seed_groups(self.app)
        self.assertIn('62 item(ns)', self.panel_text())
        self.assertEqual(self.api.pinned, [self.panel_id])

    async def test_nao_recarrega_no_proximo_deploy(self):
        await bot.seed_groups(self.app)
        await self.send('-arroz')
        bot.stock.clear()
        bot.stock_seeded.clear()
        bot.load_data()
        await bot.seed_groups(self.app)
        self.assertEqual(self.stocked('arroz')['quantity'], 3)

    async def test_nao_recarrega_se_a_familia_esvaziou_o_estoque(self):
        await bot.seed_groups(self.app)
        bot.stock[CHAT['id']].clear()
        await bot.seed_groups(self.app)
        self.assertEqual(self.stock, [])

    async def test_estoque_esvaziado_nao_volta_no_proximo_deploy(self):
        await bot.seed_groups(self.app)
        bot.stock[CHAT['id']].clear()
        bot.save_data()
        bot.stock_seeded.clear()
        bot.load_data()
        await bot.seed_groups(self.app)
        self.assertEqual(self.stock, [])

    async def test_nao_mexe_em_estoque_ja_cadastrado(self):
        await self.register('arroz 9/1/2')
        await bot.seed_groups(self.app)
        self.assertEqual(len(self.stock), 1)
        self.assertEqual(self.stocked('arroz')['quantity'], 9)

    async def test_nao_carrega_em_chat_privado(self):
        bot.shopping_lists[42] = {'items': [], 'created_at': None}
        await bot.seed_groups(self.app)
        self.assertNotIn(42, bot.stock)

    async def test_grupo_sem_acesso_nao_impede_a_subida(self):
        original = self.api.do_request

        async def bloqueia_envio(url, method, request_data=None, **kwargs):
            if url.endswith('/sendMessage'):
                return self.api._error('Forbidden: bot was kicked from the group chat')
            return await original(url, method, request_data, **kwargs)

        self.api.do_request = bloqueia_envio
        await bot.seed_groups(self.app)
        self.assertEqual(len(self.stock), 62)

    async def test_sem_arquivo_nao_quebra(self):
        with patch.object(bot, 'SEED_FILE', '/nao/existe.txt'):
            await bot.seed_groups(self.app)
        self.assertEqual(self.stock, [])

    async def test_comando_manual_carrega_e_mostra_a_lista(self):
        await self.send('/carregarestoque')
        self.assertEqual(len(self.stock), 62)
        self.assertIn('Café', self.menu_text())

    async def test_comando_manual_nao_recarrega(self):
        await self.send('/carregarestoque')
        await self.send('-arroz')
        await self.send('/carregarestoque')
        self.assertEqual(self.stocked('arroz')['quantity'], 3)


class PersistenciaTest(StockTestCase):
    async def test_estoque_vinculo_e_painel_sobrevivem_ao_reinicio(self):
        await self.register('Arroz (5 kg) 1/2/5')
        painel = self.panel_id
        bot.stock.clear()
        bot.shopping_lists.clear()
        bot.stock_panels.clear()
        bot.load_data()
        self.assertEqual(self.stocked('arroz')['package'], '5 kg')
        self.assertEqual(self.listed('arroz')['stock_id'], self.stocked('arroz')['id'])
        self.assertEqual(self.panel_id, painel)

    async def test_botao_do_painel_funciona_depois_do_reinicio(self):
        await self.register('arroz 5/1/2')
        await self.open_category('Mercearia')
        bot.stock.clear()
        bot.load_data()
        await self.press('arroz ·')
        self.assertEqual(self.stocked('arroz')['quantity'], 4)

    async def test_arquivo_antigo_sem_estoque_carrega_a_lista(self):
        with open(bot.DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({'shopping_lists': {str(CHAT['id']): {'items': [{'name': 'leite'}]}}}, f)
        bot.shopping_lists.clear()
        bot.load_data()
        self.assertEqual(self.listed('leite')['quantity'], 1)
        self.assertEqual(self.stock, [])


if __name__ == '__main__':
    unittest.main()
