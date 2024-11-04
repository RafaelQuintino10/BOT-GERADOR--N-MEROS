from datetime import datetime, timedelta, timezone
from io import BytesIO
import io
import json
import time
import matplotlib.pyplot as plt
import qrcode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, CallbackContext,  MessageHandler, filters
import requests
import mercadopago
import asyncio
import sqlite3
import pandas as pd


# Insira sua chave de API do sms-activate.io e o token do bot do Telegram
SMS_ACTIVATE_API_KEY = '3924d657fb95cebf09d6d5704A190eb2'
TELEGRAM_BOT_TOKEN = '7894225433:AAEknYuQrHlFuXj_E5oR12g_DUbO_q8hwH8'
MP_ACCESS_TOKEN = 'APP_USR-3659660205672870-103020-e757331755777413d8214c1a1f9c11ce-1990304411'
PIX_KEY = '123456789'  # Insira aqui sua chave PIX

# Inicializa o cliente do Mercado Pago
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

user_payments = {}

async def conexao_banco():
    conexao = sqlite3.connect('bot_sms.db')
    return conexao

async def registrar_pagamento(user_id, valor, nome):
    conexao = await conexao_banco()  # Certifique-se de que a conexão seja awaitable
    cursor = conexao.cursor()
    try:
       
        cursor.execute('''
        INSERT INTO usuarios 
        (user_id, saldo, nome) VALUES (?, ?, ?) 
        ON CONFLICT (user_id) DO UPDATE SET saldo = usuarios.saldo + ?, nome = ?         
        ''', (user_id, valor, nome, valor, nome))


        # Registra a transação
        cursor.execute('''
            INSERT INTO transacoes
            (user_id, valor, tipo) VALUES (?, ?, 'Pagamento')
        ''', (user_id, valor))

        conexao.commit()
        print(f"Pagamento de R${valor} registrado e saldo atualizado para o usuário {user_id}.")
    except Exception as e:
        print(f"Erro ao registrar o pagamento: {e}")
    finally:
        conexao.close()  # Não esqueça de fechar a conexão

async def valor_digitado(update: Update, context: CallbackContext):
    await update.callback_query.message.reply_text("Digite o valor da Recarga: R$ ")

async def message_handler(update:Update, context:CallbackContext):
    valor = float(update.message.text)
    await pay(update, context, valor)

async def consultar_saldo(user_id, context, update: Update):
    await update.callback_query.message.reply_text("Consultando seu saldo...")
    conexao = await conexao_banco()  # Use await para a conexão assíncrona
    cursor = conexao.cursor()
    try:
        cursor.execute('''SELECT saldo FROM usuarios WHERE user_id = ?''', (user_id,))
        resultado = cursor.fetchone()

        if resultado is not None:
            saldo = resultado[0]
        else:
            saldo = 0.0

        await context.bot.send_message(chat_id=user_id, text=f"SEU SALDO ATUAL É DE R${saldo}!")
        


    except Exception as e:
        print(f"ERRO AO CONSULTAR O SALDO: {e}")
        await context.bot.send_message(chat_id=user_id, text="Erro ao consultar saldo.")

    finally:
        conexao.close()  # Fecha a conexão



async def imprimir_dados_no_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ADMIN_ID = 7450049318
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Você não tem permissão para acessar esta função.")
        return
    
    await update.message.reply_text("Consultando o banco de dados...")
    conexao = sqlite3.connect('bot_sms.db')
    cursor = conexao.cursor()
    
    try:
        # Obtém a lista de tabelas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tabelas = cursor.fetchall()

        if not tabelas:
            await update.message.reply_text("Nenhuma tabela encontrada no banco de dados.")
            return

        for (tabela,) in tabelas:
            # Obtém os dados da tabela
            cursor.execute(f"SELECT * FROM {tabela};")
            dados = cursor.fetchall()

            if dados:
                # Obtém os nomes das colunas
                colunas = [descricao[0] for descricao in cursor.description]
                df = pd.DataFrame(dados, columns=colunas)

                # Cria uma tabela e salva como imagem
                fig, ax = plt.subplots(figsize=(10, len(df) * 0.5))  # Ajusta o tamanho da figura

                # Estilização
                ax.axis('tight')
                ax.axis('off')

                # Título
                plt.title(f'Tabela: {tabela}', fontsize=14, fontweight='bold', color='#0088cc')  # Cor do Telegram

                # Cria a tabela
                table = ax.table(cellText=df.values, colLabels=df.columns, cellLoc='center', loc='center')
                table.auto_set_font_size(False)
                table.set_fontsize(10)
                table.scale(1.2, 1.2)

                # Estilizando as cores da tabela
                for (i, j), cell in table.get_celld().items():
                    if i == 0:  # Cabeçalho
                        cell.set_text_props(fontweight='bold', color='white')
                        cell.set_facecolor('#0088cc')  # Cor do Telegram
                    else:
                        cell.set_facecolor('#e8f8fa') if j % 2 == 0 else cell.set_facecolor('white')

                # Salva a tabela como imagem
                plt.savefig('tabela.png', bbox_inches='tight', dpi=300)
                plt.close()

                # Envia a imagem no bot
                with open('tabela.png', 'rb') as f:
                    await update.message.reply_photo(photo=f)
            else:
                await update.message.reply_text(f"Tabela: {tabela} - Nenhum dado encontrado.")

    except Exception as e:
        await update.message.reply_text(f"Erro ao acessar o banco de dados: {e}")
    finally:
        conexao.close()
    
    


# Função para alugar um número temporário
async def rent_number(update: Update, context: ContextTypes.DEFAULT_TYPE, service: str):
    balance_response = requests.get(f'https://sms-activate.org/stubs/handler_api.php?api_key={SMS_ACTIVATE_API_KEY}&action=getBalance')
    if balance_response.status_code == 200:
        balance = float(balance_response.text.split(':')[1])
        if balance <= 0:
            await update.callback_query.message.reply_text('Saldo insuficiente. Por favor, adicione saldo via PIX.')
            return

    params = {
        'api_key': SMS_ACTIVATE_API_KEY,
        'action': 'getNumber',
        'service': service,
        'country': 0  # 0 é para aluguel global
    }
    response = requests.get('https://sms-activate.org/stubs/handler_api.php', params=params)
    if 'ACCESS_NUMBER' in response.text:
        _, id_activation, number = response.text.split(':')
        await update.callback_query.message.reply_text(f'Número alugado para {service}: {number}\nID de ativação: {id_activation}')
    else:
        await update.callback_query.message.reply_text('Erro ao alugar número: Não há números disponíveis.')

# Função para receber o SMS de um número alugado
async def get_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.callback_query.message.reply_text('Use: /getsms <id_ativacao>')
        return
    id_activation = context.args[0]
    response = requests.get(f'https://sms-activate.org/stubs/handler_api.php?api_key={SMS_ACTIVATE_API_KEY}&action=getStatus&id={id_activation}')
    if 'STATUS_OK' in response.text:
        sms = response.text.split(':')[1]
        await update.callback_query.message.reply_text(f'SMS recebido: {sms}')
    else:
        await update.callback_query.message.reply_text(f'Nenhum SMS recebido ainda ou erro: {response.text}')
        

async def pay(update: Update, context: CallbackContext, valor) -> None:
    user_id = update.effective_user.id

    # Verifica se o usuário já tem um pagamento em andamento (opcional)
    if user_id in user_payments:
        await update.callback_query.message.reply_text("Você já tem um pagamento em andamento. Tente novamente mais tarde.")
        return
    
    await update.message.reply_text("Gerando pagamento...")

    # Data de expiração: 30 minutos a partir de agora em UTC-4
    expiration_time = datetime.now(timezone.utc) + timedelta(minutes=30)
    expiration_time_utc_minus_4 = expiration_time.astimezone(timezone(timedelta(hours=-4)))
    date_of_expiration = expiration_time_utc_minus_4.strftime("%Y-%m-%dT%H:%M:%S.000-04:00")

    # Dados do pagamento
    payment_data = {
        "transaction_amount": valor,  # Valor fixo para o exemplo
        "payment_method_id": "pix",
        "date_of_expiration": date_of_expiration,
        "payer": {
            "email": f"user{user_id}@example.com",  # Pode personalizar com o e-mail do usuário
        }
    }

    # Cria o pagamento
    payment_response = sdk.payment().create(payment_data)

    if payment_response['status'] == 400:
        await update.message.reply_text("Erro ao criar o pagamento.")
        return

    payment = payment_response["response"]
    resposta = json.dumps(payment, indent=4)
    payment_id = payment.get("id")
    print(payment_id)
    print(resposta)
    

    # Recupera o QR code
    qr_code = payment.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code")

    if qr_code:
        img = qrcode.make(qr_code)
        buf = io.BytesIO()
        img.save(buf)
        buf.seek(0)

        # Armazena informações do pagamento para o usuário
        user_payments[user_id] = {
            "date_of_expiration": date_of_expiration,
            "qr_code": qr_code,
            "id": payment_id
        }

        await context.bot.send_photo(chat_id=user_id, photo=buf)
        await update.message.reply_text(qr_code)
        asyncio.create_task(check_payment_status(user_id, payment_id, context,update))


    else:
        await update.callback_query.message.reply_text("QR code não encontrado na resposta.")

async def check_payment_status(user_id, payment_id, context: CallbackContext, update: Update):
    while True:
        # Atraso antes de verificar o status novamente
        time.sleep(2)  # Verifica a cada 10 segundos

        # Consulta o status do pagamento
        payment_info = sdk.payment().get(payment_id)
        payment_status = payment_info['response']['status']
        print(payment_status)
        if payment_status in ['approved', 'pending', 'rejected']:
            if payment_status == 'approved':
               await context.bot.send_message(chat_id=user_id, text="PAGAMENTO APROVADO! ✅💰")
               nome = update.effective_user.first_name
               valor_pago = payment_info['response']['transaction_amount']  # Valor pago
               await registrar_pagamento(user_id, valor_pago, nome)  # Registra o pagamento no banco de dados
            elif payment_status == 'rejected':
                await context.bot.send_message(chat_id=user_id, text="PAGAMENTO REPROVADO! ❗️❗️❗️")
            else:  # Pending
                continue  # Continue a verificar se ainda está pendente

            break  # Sai do loop após o status ser determinado


        
# Função para exibir o menu principal com botões
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Ver Saldo", callback_data='check_balance'),
            # InlineKeyboardButton("Adicionar Saldo via PIX", callback_data='pix_payment'),
        ],
        [
            InlineKeyboardButton("Alugar Número WhatsApp", callback_data='rent_whatsapp'),
            InlineKeyboardButton("Alugar Número Telegram", callback_data='rent_telegram'),
        ],
        [
            InlineKeyboardButton("Alugar Número Discord", callback_data='rent_discord'),
            InlineKeyboardButton("Alugar Número Facebook", callback_data='rent_facebook'),
        ],
        [
            InlineKeyboardButton("Alugar Número Instagram", callback_data='rent_instagram'),
            InlineKeyboardButton("Alugar Número Gmail", callback_data='rent_gmail'),
        ],
        [
            InlineKeyboardButton("Alugar Número Outlook", callback_data='rent_outlook'),
            InlineKeyboardButton("Alugar Número Uber", callback_data='rent_uber'),
        ],
        [
            InlineKeyboardButton("Alugar Número 99", callback_data='rent_99'),
            InlineKeyboardButton("Alugar Número InDriver", callback_data='rent_indriver'),
        ],
        [
            InlineKeyboardButton("Receber SMS", callback_data='get_sms'),
        ],
        [
            InlineKeyboardButton("Pagar com Mercado Pago", callback_data='mercado_pago'),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Escolha uma opção:', reply_markup=reply_markup)

# Função para lidar com os botões
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'check_balance':
        await consultar_saldo(update.effective_user.id, context,update)  # Passa o user_id diretamente

    elif query.data == 'mercado_pago':
        await valor_digitado(update, context)  # Ajuste o valor conforme necessário
    else:
        service_mapping = {
            'rent_whatsapp': 'whatsapp',
            'rent_telegram': 'telegram',
            'rent_discord': 'discord',
            'rent_facebook': 'facebook',
            'rent_instagram': 'instagram',
            'rent_gmail': 'gmail',
            'rent_outlook': 'outlook',
            'rent_uber': 'uber',
            'rent_99': '99',
            'rent_indriver': 'indriver',
        }
        service = service_mapping.get(query.data)
        if service:
            await rent_number(update, context, service)

# Inicializa o bot e os comandos
def main():
    conexao_Api = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conexao_Api.add_handler(CommandHandler('start', start))
    conexao_Api.add_handler(CallbackQueryHandler(button_handler))
    conexao_Api.add_handler(CommandHandler('admin', imprimir_dados_no_bot))
    conexao_Api.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))


    conexao_Api.run_polling()

if __name__ == '__main__':
    main()
